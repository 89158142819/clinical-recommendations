
import argparse
import json
import logging
import subprocess
import sys
import time

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import requests
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
CATALOG_FILE = ROOT / "catalog.json"
REGISTRY_FILE = ROOT / "processing_registry.json"
PARSER_FILE = ROOT / "extract_sections_v2.py"

MAX_ATTEMPTS = 5
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 300

USER_AGENT = "ClinicalRecommendationsCatalog/1.0"

SECTION_KEYS = [
    "definition",
    "icd10",
    "laboratory_diagnostics",
    "instrumental_diagnostics",
    "other_diagnostics",
    "treatment",
]


def now():
    return datetime.now(timezone.utc).isoformat()


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_catalog():
    if not CATALOG_FILE.exists():
        raise FileNotFoundError(
            f"Не найден каталог: {CATALOG_FILE}"
        )

    with CATALOG_FILE.open("r", encoding="utf-8") as file:
        catalog = json.load(file)

    recommendations = catalog.get("recommendations")

    if not isinstance(recommendations, list):
        raise ValueError(
            "В catalog.json отсутствует список recommendations"
        )

    declared_total = catalog.get("total")

    if declared_total is not None:
        if declared_total != len(recommendations):
            raise ValueError(
                f"Несоответствие каталога: total={declared_total}, "
                f"фактически={len(recommendations)}"
            )

    logging.info(
        "Каталог загружен. Рекомендаций: %s",
        len(recommendations),
    )

    return recommendations


def load_registry():
    if not REGISTRY_FILE.exists():
        return {
            "updated_at": None,
            "total_processed": 0,
            "results": {},
        }

    with REGISTRY_FILE.open("r", encoding="utf-8") as file:
        registry = json.load(file)

    if not isinstance(registry, dict):
        raise ValueError("Некорректный формат реестра")

    if not isinstance(registry.get("results"), dict):
        raise ValueError("В реестре отсутствует results")

    return registry


def save_registry(registry):
    registry["updated_at"] = now()

    registry["total_processed"] = len(
        registry["results"]
    )

    temporary_file = REGISTRY_FILE.with_suffix(".tmp")

    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(
            registry,
            file,
            ensure_ascii=False,
            indent=2,
        )

    temporary_file.replace(REGISTRY_FILE)


def document_paths(document_id):
    return {
        "pdf": OUTPUT_DIR / f"{document_id}.pdf",
        "input": OUTPUT_DIR / f"{document_id}.json",
        "sections": OUTPUT_DIR / f"{document_id}_sections_v2.json",
        "report": OUTPUT_DIR / f"{document_id}_quality_report_v2.json",
    }


def download_pdf(document_id):
    pdf_url = (
        "https://apicr.minzdrav.gov.ru/api.ashx"
        f"?id={document_id}&op=GetClinrecPdf"
    )

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/pdf,*/*",
    }

    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            logging.info(
                "Скачивание %s. Попытка %s/%s",
                document_id,
                attempt,
                MAX_ATTEMPTS,
            )

            response = requests.get(
                pdf_url,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                headers=headers,
            )

            response.raise_for_status()

            content = response.content

            if not content.startswith(b"%PDF"):
                raise RuntimeError(
                    "Источник не вернул PDF. "
                    f"Content-Type: "
                    f"{response.headers.get('Content-Type')}"
                )

            return content, pdf_url

        except Exception as error:
            last_error = error

            logging.warning(
                "Ошибка скачивания %s: %s",
                document_id,
                error,
            )

            if attempt < MAX_ATTEMPTS:
                delay = min(10 * attempt, 60)
                logging.info(
                    "Повтор через %s секунд",
                    delay,
                )
                time.sleep(delay)

    raise RuntimeError(
        f"Не удалось скачать {document_id}: {last_error}"
    )


def extract_pdf_text(pdf_content):
    reader = PdfReader(BytesIO(pdf_content))

    if reader.is_encrypted:
        raise RuntimeError("PDF защищён паролем")

    pages = []

    for number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""

        pages.append({
            "page": number,
            "text": page_text,
        })

    full_text = "\n\n".join(
        f"[Страница {page['page']}]\n{page['text']}"
        for page in pages
    )

    if not full_text.strip():
        raise RuntimeError(
            "Не удалось извлечь текст из PDF"
        )

    return reader, pages, full_text


def create_input_json(
    document,
    pdf_url,
    reader,
    full_text,
):
    document_id = str(document["id"])
    title = str(document["title"])

    source_url = (
        f"https://cr.minzdrav.gov.ru/view-cr/{document_id}"
    )

    return {
        "id": document_id,
        "title": title,
        "source_url": source_url,
        "pdf_url": pdf_url,
        "pages_count": len(reader.pages),
        "extracted_at": now(),
        "extraction_status": "text_extracted",
        "sections": {
            key: ""
            for key in SECTION_KEYS
        },
        "full_text": full_text,
    }


def validate_parser_outputs(document_id):
    paths = document_paths(document_id)

    for key in ("sections", "report"):
        if not paths[key].exists():
            raise RuntimeError(
                f"Парсер не создал файл: {paths[key]}"
            )

        if paths[key].stat().st_size == 0:
            raise RuntimeError(
                f"Создан пустой файл: {paths[key]}"
            )

    with paths["report"].open(
        "r",
        encoding="utf-8",
    ) as file:
        report = json.load(file)

    quality = report.get("quality_check")
    missing = report.get("missing_sections", [])
    warnings = report.get("warnings", [])

    if (
        quality == "passed"
        and not missing
        and not warnings
    ):
        return "passed", report

    return "review_required", report


def is_already_processed(document_id, registry):
    record = registry["results"].get(document_id)

    if not record or record.get("status") != "passed":
        return False

    paths = document_paths(document_id)

    required_files = (
        paths["pdf"],
        paths["input"],
        paths["sections"],
        paths["report"],
    )

    if not all(path.exists() and path.stat().st_size > 0
               for path in required_files):
        return False

    try:
        with paths["report"].open(
            "r",
            encoding="utf-8",
        ) as file:
            report = json.load(file)

        return (
            report.get("quality_check") == "passed"
            and not report.get("missing_sections", [])
            and not report.get("warnings", [])
        )

    except Exception:
        return False


def process_document(document, registry):
    document_id = str(document["id"])
    title = str(document["title"])

    paths = document_paths(document_id)

    logging.info("=" * 70)
    logging.info("ОБРАБОТКА: %s — %s", document_id, title)
    logging.info("=" * 70)

    record = {
        "id": document_id,
        "title": title,
        "status": "processing",
        "started_at": now(),
        "finished_at": None,
        "error": None,
        "pages_count": None,
        "text_length": None,
    }

    registry["results"][document_id] = record
    save_registry(registry)

    try:
        pdf_content, pdf_url = download_pdf(document_id)

        OUTPUT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        paths["pdf"].write_bytes(pdf_content)

        reader, pages, full_text = extract_pdf_text(
            pdf_content
        )

        input_data = create_input_json(
            document,
            pdf_url,
            reader,
            full_text,
        )

        with paths["input"].open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                input_data,
                file,
                ensure_ascii=False,
                indent=2,
            )

        logging.info(
            "PDF страниц: %s",
            len(reader.pages),
        )

        logging.info(
            "Извлечено символов: %s",
            len(full_text),
        )

        logging.info("Запуск парсера v6")

        result = subprocess.run(
            [
                sys.executable,
                str(PARSER_FILE),
                "--input",
                str(paths["input"]),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if result.stdout:
            print(result.stdout, flush=True)

        if result.stderr:
            print(result.stderr, file=sys.stderr, flush=True)

        if result.returncode != 0:
            raise RuntimeError(
                f"Парсер завершился с кодом "
                f"{result.returncode}"
            )

        status, report = validate_parser_outputs(
            document_id
        )

        record.update({
            "status": status,
            "finished_at": now(),
            "pages_count": len(reader.pages),
            "text_length": len(full_text),
            "quality_check": report.get("quality_check"),
            "missing_sections": report.get(
                "missing_sections", []
            ),
            "warnings": report.get("warnings", []),
            "pdf_file": str(paths["pdf"].relative_to(ROOT)),
            "input_file": str(paths["input"].relative_to(ROOT)),
            "sections_file": str(paths["sections"].relative_to(ROOT)),
            "report_file": str(paths["report"].relative_to(ROOT)),
        })

        if status == "passed":
            logging.info(
                "PASSED: %s — %s",
                document_id,
                title,
            )
        else:
            logging.warning(
                "REVIEW_REQUIRED: %s",
                document_id,
            )

    except Exception as error:
        record.update({
            "status": "failed",
            "finished_at": now(),
            "error": str(error),
        })

        logging.exception(
            "Ошибка обработки %s",
            document_id,
        )

    finally:
        save_registry(registry)

    return record["status"]


def main():
    setup_logging()

    parser = argparse.ArgumentParser(
        description="Массовая загрузка клинических рекомендаций"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Количество рекомендаций в партии",
    )

    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="С какой записи начинать обработку",
    )

    parser.add_argument(
        "--ids",
        nargs="*",
        help="Обработать конкретные ID",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Повторно обработать даже успешные документы",
    )

    args = parser.parse_args()

    if args.limit < 1 or args.offset < 0:
        parser.error("Некорректные limit или offset")

    if not PARSER_FILE.exists():
        raise FileNotFoundError(
            f"Не найден парсер: {PARSER_FILE}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    recommendations = load_catalog()
    registry = load_registry()

    if args.ids:
        requested_ids = set(args.ids)

        selected = [
            item for item in recommendations
            if str(item["id"]) in requested_ids
        ]

        found_ids = {
            str(item["id"])
            for item in selected
        }

        not_found = requested_ids - found_ids

        if not_found:
            logging.warning(
                "ID отсутствуют в каталоге: %s",
                sorted(not_found),
            )

    else:
        selected = recommendations[
            args.offset:args.offset + args.limit
        ]

    if not selected:
        logging.warning("Нет рекомендаций для обработки")
        return 0

    logging.info("=" * 70)
    logging.info("МАССОВАЯ ОБРАБОТКА")
    logging.info("Размер партии: %s", len(selected))
    logging.info("Всего в каталоге: %s", len(recommendations))
    logging.info("=" * 70)

    counts = {
        "passed": 0,
        "review_required": 0,
        "failed": 0,
        "skipped": 0,
    }

    for index, document in enumerate(selected, start=1):
        document_id = str(document["id"])

        logging.info(
            "\nПРОГРЕСС: %s/%s",
            index,
            len(selected),
        )

        if (
            not args.force
            and is_already_processed(document_id, registry)
        ):
            logging.info(
                "ПРОПУСК: %s уже успешно обработан",
                document_id,
            )

            counts["skipped"] += 1
            continue

        status = process_document(
            document,
            registry,
        )

        counts[status] += 1

    logging.info("\n" + "=" * 70)
    logging.info("ИТОГИ ПАРТИИ")
    logging.info("=" * 70)

    for status, count in counts.items():
        logging.info("%s: %s", status, count)

    logging.info(
        "Всего обработано или пропущено: %s",
        sum(counts.values()),
    )

    logging.info(
        "Реестр сохранён: %s",
        REGISTRY_FILE,
    )

    if counts["failed"] > 0:
        logging.error(
            "В партии есть документы с ошибками"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
