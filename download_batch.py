
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


# ============================================================
# НАСТРОЙКИ
# ============================================================

ROOT = Path(__file__).resolve().parent

OUTPUT_DIR = ROOT / "output"
CATALOG_FILE = ROOT / "catalog.json"
REGISTRY_FILE = ROOT / "processing_registry.json"
PARSER_FILE = ROOT / "extract_sections_v2.py"

MAX_ATTEMPTS = 5

CONNECT_TIMEOUT = 30
READ_TIMEOUT = 300

USER_AGENT = "ClinicalRecommendationsCatalog/1.0"

PARSER_METHOD = "universal_structural_headings_v7"


# ============================================================
# СТРУКТУРА РАЗДЕЛОВ
# ============================================================

REQUIRED_SECTION_KEYS = [
    "terms",
    "definition",
    "etiology_pathogenesis",
    "epidemiology",
    "icd10",
    "classification",
    "clinical_picture",
    "diagnostics",
    "complaints_anamnesis",
    "physical_examination",
    "laboratory_diagnostics",
    "instrumental_diagnostics",
    "other_diagnostics",
    "treatment",
    "rehabilitation",
]

OPTIONAL_SECTION_KEYS = {
    "other_diagnostics",
}


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def now():
    return datetime.now(timezone.utc).isoformat()


def setup_logging():

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def load_catalog():

    with CATALOG_FILE.open(
        "r",
        encoding="utf-8"
    ) as f:

        catalog = json.load(f)

    recommendations = catalog.get("recommendations")

    if not isinstance(recommendations, list):

        raise ValueError(
            "Некорректный catalog.json"
        )

    if catalog.get("total") != len(recommendations):

        raise ValueError(
            "Количество записей каталога не совпадает"
        )

    ids = [
        str(item["id"])
        for item in recommendations
    ]

    if len(ids) != len(set(ids)):

        raise ValueError(
            "В каталоге обнаружены повторяющиеся ID"
        )

    return recommendations


def load_registry():

    if not REGISTRY_FILE.exists():

        return {
            "updated_at": None,
            "total_processed": 0,
            "results": {},
        }

    with REGISTRY_FILE.open(
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)

    if not isinstance(data.get("results"), dict):

        raise ValueError(
            "Некорректный реестр processing_registry.json"
        )

    return data


def save_registry(registry):

    registry["updated_at"] = now()

    registry["total_processed"] = len(
        registry["results"]
    )

    temp = REGISTRY_FILE.with_suffix(".tmp")

    with temp.open(
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            registry,
            f,
            ensure_ascii=False,
            indent=2,
        )

    temp.replace(REGISTRY_FILE)


def paths_for(document_id):

    return {
        "pdf": OUTPUT_DIR / f"{document_id}.pdf",

        "input": OUTPUT_DIR / f"{document_id}.json",

        "sections": (
            OUTPUT_DIR /
            f"{document_id}_sections_v2.json"
        ),

        "report": (
            OUTPUT_DIR /
            f"{document_id}_quality_report_v2.json"
        ),
    }


# ============================================================
# ПРОВЕРКА ПОВТОРНОЙ ОБРАБОТКИ
# ============================================================

def is_already_processed(document_id, registry):

    record = registry["results"].get(document_id)

    if not record:
        return False

    if record.get("status") != "passed":
        return False

    if record.get("quality_check") != "passed":
        return False

    if record.get("extraction_method") != PARSER_METHOD:
        return False

    if record.get("missing_sections"):
        return False

    if record.get("warnings"):
        return False

    return True


# ============================================================
# СКАЧИВАНИЕ PDF
# ============================================================

def download_pdf(document_id):

    url = (
        "https://apicr.minzdrav.gov.ru/api.ashx"
        f"?id={document_id}&op=GetClinrecPdf"
    )

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/pdf,*/*",
    }

    last_error = None

    for attempt in range(
        1,
        MAX_ATTEMPTS + 1
    ):

        try:

            logging.info(
                "Скачивание %s: попытка %s/%s",
                document_id,
                attempt,
                MAX_ATTEMPTS,
            )

            response = requests.get(
                url,
                timeout=(
                    CONNECT_TIMEOUT,
                    READ_TIMEOUT
                ),
                headers=headers,
            )

            response.raise_for_status()

            if not response.content.startswith(b"%PDF"):

                raise RuntimeError(
                    "Получен ответ, не являющийся PDF"
                )

            return response.content, url

        except Exception as error:

            last_error = error

            logging.warning(
                "Ошибка скачивания %s: %s",
                document_id,
                error,
            )

            if attempt < MAX_ATTEMPTS:

                time.sleep(
                    min(attempt * 10, 60)
                )

    raise RuntimeError(
        f"Не удалось скачать документ: {last_error}"
    )


# ============================================================
# ИЗВЛЕЧЕНИЕ ТЕКСТА
# ============================================================

def extract_text(pdf_content):

    reader = PdfReader(
        BytesIO(pdf_content)
    )

    if reader.is_encrypted:

        try:

            result = reader.decrypt("")

            if not result:

                raise RuntimeError(
                    "PDF защищён паролем"
                )

        except Exception as error:

            raise RuntimeError(
                f"Не удалось открыть PDF: {error}"
            )

    pages = []

    for number, page in enumerate(
        reader.pages,
        start=1
    ):

        try:

            page_text = page.extract_text() or ""

        except Exception as error:

            logging.warning(
                "Ошибка извлечения страницы %s: %s",
                number,
                error,
            )

            page_text = ""

        pages.append({
            "page": number,
            "text": page_text,
        })

    full_text = "\n\n".join(
        f"[Страница {p['page']}]\n{p['text']}"
        for p in pages
    )

    if not full_text.strip():

        raise RuntimeError(
            "PDF не содержит извлекаемого текста"
        )

    pages_with_text = sum(
        1
        for page in pages
        if page["text"].strip()
    )

    empty_pages = [
        page["page"]
        for page in pages
        if not page["text"].strip()
    ]

    return (
        reader,
        full_text,
        pages_with_text,
        empty_pages,
    )


# ============================================================
# ФОРМИРОВАНИЕ ИСХОДНОГО JSON
# ============================================================

def create_json(
    document,
    pdf_url,
    reader,
    full_text,
    pages_with_text,
    empty_pages,
):

    document_id = str(document["id"])

    return {

        "id": document_id,

        "title": str(document["title"]),

        "source_url": (
            f"https://cr.minzdrav.gov.ru/view-cr/{document_id}"
        ),

        "pdf_url": pdf_url,

        "pages_count": len(reader.pages),

        "extracted_at": now(),

        "extraction_status": "text_extracted",

        "sections": {
            key: ""
            for key in REQUIRED_SECTION_KEYS
        },

        "full_text": full_text,

        "extraction_info": {
            "pages_total": len(reader.pages),
            "pages_with_text": pages_with_text,
            "empty_pages": empty_pages,
            "text_length": len(full_text),
            "method": "pypdf",
        },
    }


# ============================================================
# ЗАПУСК ПАРСЕРА
# ============================================================

def run_parser(input_file):

    command = [
        sys.executable,
        str(PARSER_FILE),
        "--input",
        str(input_file),
    ]

    logging.info(
        "Запуск парсера: %s",
        " ".join(command),
    )

    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.stdout:

        print(
            result.stdout,
            flush=True
        )

    if result.stderr:

        print(
            result.stderr,
            file=sys.stderr,
            flush=True,
        )

    if result.returncode != 0:

        raise RuntimeError(
            f"Ошибка парсера. Код: {result.returncode}"
        )


# ============================================================
# ПРОВЕРКА РЕЗУЛЬТАТОВ ПАРСЕРА
# ============================================================

def check_results(document_id):

    paths = paths_for(document_id)

    for key in (
        "sections",
        "report"
    ):

        path = paths[key]

        if (
            not path.exists()
            or path.stat().st_size == 0
        ):

            raise RuntimeError(
                f"Не создан ожидаемый файл: {path.name}"
            )

    with paths["sections"].open(
        "r",
        encoding="utf-8"
    ) as f:

        sections_data = json.load(f)

    with paths["report"].open(
        "r",
        encoding="utf-8"
    ) as f:

        report = json.load(f)

    # --------------------------------------------------------
    # Проверка метода
    # --------------------------------------------------------

    extraction_method = sections_data.get(
        "extraction_method"
    )

    if extraction_method != PARSER_METHOD:

        raise RuntimeError(
            "Неверный метод извлечения: "
            f"{extraction_method!r}. "
            f"Ожидался {PARSER_METHOD!r}"
        )

    # --------------------------------------------------------
    # Проверка структуры sections
    # --------------------------------------------------------

    sections = sections_data.get("sections")

    if not isinstance(sections, dict):

        raise RuntimeError(
            "Отсутствует корректный объект sections"
        )

    missing_keys = [
        key
        for key in REQUIRED_SECTION_KEYS
        if key not in sections
    ]

    empty_required_sections = [
        key
        for key in REQUIRED_SECTION_KEYS
        if key not in OPTIONAL_SECTION_KEYS
        and key in sections
        and not str(sections[key]).strip()
    ]

    # --------------------------------------------------------
    # Проверка качества
    # --------------------------------------------------------

    parser_quality = sections_data.get(
        "quality_check"
    )

    report_quality = report.get(
        "quality_check"
    )

    allowed_quality_values = {
        "passed",
        "review_required",
    }

    if parser_quality not in allowed_quality_values:

        raise RuntimeError(
            "Неизвестный статус качества в JSON парсера: "
            f"{parser_quality!r}"
        )

    if report_quality not in allowed_quality_values:

        raise RuntimeError(
            "Неизвестный статус качества в отчёте: "
            f"{report_quality!r}"
        )

    missing_sections = report.get(
        "missing_sections",
        []
    )

    warnings = report.get(
        "warnings",
        []
    )

    optional_sections_not_found = report.get(
        "optional_sections_not_found",
        []
    )

    if not isinstance(missing_sections, list):
        missing_sections = [str(missing_sections)]

    if not isinstance(warnings, list):
        warnings = [str(warnings)]

    if not isinstance(optional_sections_not_found, list):
        optional_sections_not_found = [
            str(optional_sections_not_found)
        ]

    # --------------------------------------------------------
    # Определение итогового статуса
    # --------------------------------------------------------

    quality_passed = (
        parser_quality == "passed"
        and report_quality == "passed"
        and not missing_sections
        and not warnings
        and not missing_keys
        and not empty_required_sections
    )

    if quality_passed:

        status = "passed"

    else:

        status = "review_required"

    details = {
        "missing_keys": missing_keys,
        "empty_required_sections": empty_required_sections,
        "missing_sections": missing_sections,
        "warnings": warnings,
        "optional_sections_not_found": (
            optional_sections_not_found
        ),
        "parser_quality": parser_quality,
        "report_quality": report_quality,
    }

    return (
        status,
        report,
        extraction_method,
        details,
    )


# ============================================================
# ОБРАБОТКА ОДНОГО ДОКУМЕНТА
# ============================================================

def process_document(document, registry):

    document_id = str(document["id"])

    title = str(document["title"])

    paths = paths_for(document_id)

    record = {

        "id": document_id,

        "title": title,

        "status": "processing",

        "started_at": now(),

        "finished_at": None,

        "error": None,

        "quality_check": None,

        "extraction_method": None,

        "missing_sections": [],

        "warnings": [],

    }

    registry["results"][document_id] = record

    save_registry(registry)

    logging.info("=" * 70)

    logging.info(
        "ОБРАБОТКА %s: %s",
        document_id,
        title,
    )

    logging.info("=" * 70)

    try:

        # ----------------------------------------------------
        # Скачивание PDF
        # ----------------------------------------------------

        pdf_content, pdf_url = download_pdf(
            document_id
        )

        OUTPUT_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        paths["pdf"].write_bytes(
            pdf_content
        )

        # ----------------------------------------------------
        # Извлечение текста
        # ----------------------------------------------------

        (
            reader,
            full_text,
            pages_with_text,
            empty_pages,
        ) = extract_text(pdf_content)

        input_data = create_json(
            document,
            pdf_url,
            reader,
            full_text,
            pages_with_text,
            empty_pages,
        )

        with paths["input"].open(
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                input_data,
                f,
                ensure_ascii=False,
                indent=2,
            )

        logging.info(
            "Страниц: %s",
            len(reader.pages),
        )

        logging.info(
            "Страниц с текстом: %s",
            pages_with_text,
        )

        logging.info(
            "Пустых страниц: %s",
            len(empty_pages),
        )

        logging.info(
            "Символов: %s",
            len(full_text),
        )

        # ----------------------------------------------------
        # Удаление старых результатов
        # ----------------------------------------------------

        for key in (
            "sections",
            "report"
        ):

            if paths[key].exists():

                paths[key].unlink()

        # ----------------------------------------------------
        # Запуск парсера
        # ----------------------------------------------------

        run_parser(
            paths["input"]
        )

        # ----------------------------------------------------
        # Проверка результатов
        # ----------------------------------------------------

        (
            status,
            report,
            extraction_method,
            details,
        ) = check_results(document_id)

        record.update({

            "status": status,

            "finished_at": now(),

            "quality_check": report.get(
                "quality_check"
            ),

            "extraction_method": extraction_method,

            "missing_sections": report.get(
                "missing_sections",
                []
            ),

            "warnings": report.get(
                "warnings",
                []
            ),

            "optional_sections_not_found": (
                report.get(
                    "optional_sections_not_found",
                    []
                )
            ),

            "validation_details": details,

            "pages_count": len(reader.pages),

            "pages_with_text": pages_with_text,

            "empty_pages": empty_pages,

            "text_length": len(full_text),

            "pdf_file": str(
                paths["pdf"].relative_to(ROOT)
            ),

            "input_file": str(
                paths["input"].relative_to(ROOT)
            ),

            "sections_file": str(
                paths["sections"].relative_to(ROOT)
            ),

            "report_file": str(
                paths["report"].relative_to(ROOT)
            ),

        })

        logging.info(
            "РЕЗУЛЬТАТ %s: %s",
            document_id,
            status,
        )

        if status == "review_required":

            logging.warning(
                "Документ требует проверки: %s",
                details,
            )

        if details["optional_sections_not_found"]:

            logging.info(
                "Отсутствуют необязательные разделы: %s",
                details["optional_sections_not_found"],
            )

    except Exception as error:

        record.update({

            "status": "failed",

            "finished_at": now(),

            "error": str(error),

        })

        logging.exception(
            "Ошибка документа %s",
            document_id,
        )

    finally:

        save_registry(registry)

    return record["status"]


# ============================================================
# ИТОГОВАЯ СТАТИСТИКА
# ============================================================

def print_summary(counts, registry):

    logging.info("\n" + "=" * 70)

    logging.info(
        "ИТОГИ МАССОВОЙ ЗАГРУЗКИ"
    )

    logging.info("=" * 70)

    for status in (
        "passed",
        "review_required",
        "failed",
        "skipped",
    ):

        logging.info(
            "%s: %s",
            status,
            counts[status],
        )

    logging.info("-" * 70)

    logging.info(
        "Всего записей в реестре: %s",
        registry["total_processed"],
    )

    logging.info("=" * 70)


# ============================================================
# ОСНОВНОЙ ЗАПУСК
# ============================================================

def main():

    setup_logging()

    parser = argparse.ArgumentParser(
        description=(
            "Массовая загрузка и обработка "
            "клинических рекомендаций."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Количество документов в партии",
    )

    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Начальная позиция в каталоге",
    )

    parser.add_argument(
        "--ids",
        nargs="*",
        help="Обработка конкретных ID",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Повторно обработать даже успешные документы",
    )

    parser.add_argument(
        "--fail-on-document-errors",
        action="store_true",
        help=(
            "Завершить workflow с ошибкой, "
            "если есть документы со статусом failed"
        ),
    )

    args = parser.parse_args()

    if args.limit < 1 or args.offset < 0:

        parser.error(
            "Некорректные параметры партии"
        )

    if not CATALOG_FILE.exists():

        raise FileNotFoundError(
            "Не найден catalog.json"
        )

    if not PARSER_FILE.exists():

        raise FileNotFoundError(
            "Не найден extract_sections_v2.py"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    recommendations = load_catalog()

    registry = load_registry()

    # --------------------------------------------------------
    # Выбор документов
    # --------------------------------------------------------

    if args.ids:

        requested = set(args.ids)

        selected = [
            item
            for item in recommendations
            if str(item["id"]) in requested
        ]

        found = {
            str(item["id"])
            for item in selected
        }

        missing = requested - found

        if missing:

            logging.warning(
                "Не найдены ID: %s",
                sorted(missing),
            )

    else:

        selected = recommendations[
            args.offset:
            args.offset + args.limit
        ]

    if not selected:

        logging.warning(
            "Нет документов для обработки"
        )

        return 0

    # --------------------------------------------------------
    # Счётчики
    # --------------------------------------------------------

    counts = {

        "passed": 0,

        "review_required": 0,

        "failed": 0,

        "skipped": 0,

    }

    logging.info(
        "Всего в каталоге: %s",
        len(recommendations),
    )

    logging.info(
        "Размер текущей партии: %s",
        len(selected),
    )

    logging.info(
        "Начальная позиция: %s",
        args.offset,
    )

    logging.info(
        "Метод парсера: %s",
        PARSER_METHOD,
    )

    logging.info(
        "Принудительная обработка: %s",
        args.force,
    )

    # --------------------------------------------------------
    # Последовательная обработка партии
    # --------------------------------------------------------

    for index, document in enumerate(
        selected,
        start=1
    ):

        document_id = str(
            document["id"]
        )

        logging.info(
            "\nПРОГРЕСС: %s/%s",
            index,
            len(selected),
        )

        if (
            not args.force
            and is_already_processed(
                document_id,
                registry
            )
        ):

            logging.info(
                "ПРОПУСК %s: уже успешно обработан",
                document_id,
            )

            counts["skipped"] += 1

            continue

        status = process_document(
            document,
            registry
        )

        counts[status] += 1

    # --------------------------------------------------------
    # Сохранение реестра
    # --------------------------------------------------------

    save_registry(registry)

    # --------------------------------------------------------
    # Итог
    # --------------------------------------------------------

    print_summary(
        counts,
        registry
    )

    # --------------------------------------------------------
    # Код завершения
    # --------------------------------------------------------

    if (
        args.fail_on_document_errors
        and counts["failed"] > 0
    ):

        logging.error(
            "Обнаружены технически неуспешные документы."
        )

        return 1

    logging.info(
        "Обработка партии завершена."
    )

    return 0


if __name__ == "__main__":

    sys.exit(main())
