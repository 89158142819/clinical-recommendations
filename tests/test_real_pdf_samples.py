import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from download_batch import (
    OUTPUT_DIR,
    check_results,
    create_json,
    extract_text,
    load_catalog,
    run_parser,
)


SAMPLES = {
    "750_2": "batch0",
    "1087_1": "batch0",
    "1090_1": "batch0",
    "1086_1": "batch10",
    "1061_1": "batch40",
    "1066_1": "batch40",
    "1052_1": "batch40",
    "1054_1": "batch40",
    "1021_1": "batch90",
}

PAGE_LABEL_RE = re.compile(
    r"(?im)^\s*\[?\s*(?:страница|стр\.?|page)\s*\d+\s*\]?\s*$"
)


def main():
    catalog = {
        str(item["id"]): item
        for item in load_catalog()
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = []
    failures = []

    for document_id, batch_name in SAMPLES.items():
        print("=" * 72)
        print(f"РЕАЛЬНЫЙ PDF: {document_id} ({batch_name})")
        print("=" * 72)

        pdf_path = (
            ROOT
            / "samples"
            / batch_name
            / "output"
            / f"{document_id}.pdf"
        )

        if not pdf_path.is_file():
            failures.append(f"{document_id}: PDF не найден: {pdf_path}")
            continue

        document = catalog.get(document_id)
        if document is None:
            failures.append(f"{document_id}: ID отсутствует в catalog.json")
            continue

        try:
            pdf_content = pdf_path.read_bytes()

            if not pdf_content.startswith(b"%PDF"):
                raise RuntimeError("Файл не имеет сигнатуру PDF")

            reader, full_text, pages_with_text, empty_pages = (
                extract_text(pdf_content)
            )

            if document_id == "1021_1" and len(reader.pages) != 44:
                raise RuntimeError(
                    "Контрольный документ с римской нумерацией должен содержать 44 страницы"
                )

            if document_id in {"1061_1", "1066_1"} and len(reader.pages) > 25:
                raise RuntimeError(
                    "Контрольный компактный документ неожиданно превышает 25 страниц"
                )

            if not full_text.strip():
                raise RuntimeError("После извлечения и очистки текст пуст")

            if PAGE_LABEL_RE.search(full_text):
                raise RuntimeError("В очищенном тексте остались метки страниц")

            input_data = create_json(
                document=document,
                pdf_url=f"archived GitHub Actions artifact: {pdf_path.name}",
                reader=reader,
                full_text=full_text,
                pages_with_text=pages_with_text,
                empty_pages=empty_pages,
            )

            input_path = OUTPUT_DIR / f"{document_id}.json"
            with input_path.open("w", encoding="utf-8") as file:
                json.dump(input_data, file, ensure_ascii=False, indent=2)

            run_parser(input_path)

            status, report, method, details = check_results(document_id)

            result = {
                "id": document_id,
                "title": document["title"],
                "pdf": pdf_path.name,
                "pages_total": len(reader.pages),
                "pages_with_text": pages_with_text,
                "empty_pages": empty_pages,
                "text_length_after_cleaning": len(full_text),
                "extraction_method": method,
                "quality_check": report.get("quality_check"),
                "status": status,
                "validation_details": details,
            }
            summary.append(result)

            print(
                f"ИТОГ {document_id}: {status}; "
                f"страниц={len(reader.pages)}; "
                f"символов={len(full_text)}; "
                f"метод={method}"
            )

            if document_id == "1021_1" and method != "roman_numeral_chapters_v1":
                failures.append(
                    "1021_1: не выбран профиль roman_numeral_chapters_v1"
                )

            if status != "passed":
                failures.append(
                    f"{document_id}: качество парсинга не passed: "
                    f"{json.dumps(details, ensure_ascii=False)}"
                )

        except Exception as error:
            failures.append(f"{document_id}: {type(error).__name__}: {error}")
            print(f"ОШИБКА {document_id}: {error}", file=sys.stderr)

    summary_path = OUTPUT_DIR / "real_pdf_test_summary.json"
    with summary_path.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "samples": summary,
                "passed": sum(item["status"] == "passed" for item in summary),
                "failed": len(failures),
                "failures": failures,
            },
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("=" * 72)
    print(f"Проверено документов: {len(summary)}")
    print(f"Ошибок: {len(failures)}")
    print(f"Сводка: {summary_path}")
    print("=" * 72)

    if failures:
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
