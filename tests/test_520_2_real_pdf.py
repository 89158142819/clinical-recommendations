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
    download_pdf,
    extract_text,
    load_catalog,
    paths_for,
    run_parser,
)


DOCUMENT_ID = "520_2"
ARCHIVED_PDF = ROOT / "samples" / "batch0" / "output" / f"{DOCUMENT_ID}.pdf"


def normalize(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    catalog = {
        str(item["id"]): item
        for item in load_catalog()
    }

    document = catalog.get(DOCUMENT_ID)
    require(document is not None, f"{DOCUMENT_ID}: нет записи в catalog.json")

    print("=" * 72)
    print("СКВОЗНАЯ ПРОВЕРКА ОЧИСТКИ PDF: 520_2")
    print(document["title"])
    print("=" * 72)

    # Используем ранее загруженный официальный PDF из контрольного
    # GitHub Actions artifact. Это исключает зависимость теста от
    # доступности API Минздрава во время каждого запуска.
    if ARCHIVED_PDF.is_file():
        pdf_content = ARCHIVED_PDF.read_bytes()
        pdf_url = (
            "archived GitHub Actions artifact: "
            "clinical-recommendations-batch-0/output/520_2.pdf"
        )
        print(f"Источник PDF: архивный файл {ARCHIVED_PDF}")
    else:
        print("Архивный PDF не найден; пробуем скачать PDF с Минздрава.")
        pdf_content, pdf_url = download_pdf(DOCUMENT_ID)

    reader, full_text, pages_with_text, empty_pages = extract_text(pdf_content)

    print(f"PDF: {len(reader.pages)} страниц")
    print(f"Страниц с текстом: {pages_with_text}")
    print(f"Символов после очистки: {len(full_text)}")

    normalized_full_text = normalize(full_text)

    required_phrases = (
        "перед каждым курсом терапии бисфосфонатами",
        "перед началом терапии бисфосфонатами",
        "каждые 3 месяца",
        "ионизированного кальция в",
        "паратиреоидного гормона в",
        "рентгенографии пораженной части костного скелета",
        "рентгеноденситометрии пациентам",
        "на фоне антирезорбтивной терапии",
    )

    for phrase in required_phrases:
        require(
            phrase in normalized_full_text,
            f"После очистки PDF отсутствует фраза: {phrase}",
        )
        print(f"[OK] Найдено: {phrase}")

    forbidden_joined = (
        "терапиибисфосфонатами",
        "ионизированногокальцияв",
        "паратиреоидногогормонав",
        "рентген оденситометр",
        "фонеантирезорбтивной",
    )

    for phrase in forbidden_joined:
        require(
            phrase not in normalized_full_text,
            f"После очистки осталось склеенное сочетание: {phrase}",
        )

    paths = paths_for(DOCUMENT_ID)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    input_data = create_json(
        document=document,
        pdf_url=pdf_url,
        reader=reader,
        full_text=full_text,
        pages_with_text=pages_with_text,
        empty_pages=empty_pages,
    )

    with paths["input"].open("w", encoding="utf-8") as file:
        json.dump(input_data, file, ensure_ascii=False, indent=2)

    # Запускаем настоящий парсер поверх уже очищенного текста.
    # Это дополнительно проверяет повторную очистку внутри extract_sections_v2.py.
    run_parser(paths["input"])

    status, report, method, details = check_results(DOCUMENT_ID)

    with paths["sections"].open("r", encoding="utf-8") as file:
        parsed = json.load(file)

    summary = parsed.get("diagnostic_summary", {})
    lab_items = summary.get("laboratory", [])

    instrumental_text = str(
        parsed.get("sections", {}).get("instrumental_diagnostics", "")
    )
    normalized_instrumental = normalize(instrumental_text)
    for phrase in (
        "рентгенографии пораженной части костного скелета",
        "рентгеноденситометрии пациентам",
        "на фоне антирезорбтивной терапии",
    ):
        require(
            phrase in normalized_instrumental,
            f"В инструментальной диагностике после парсинга отсутствует фраза: {phrase}",
        )

    require(
        len(lab_items) == 5,
        f"В diagnostic_summary ожидалось 5 лабораторных блоков, получено {len(lab_items)}",
    )

    combined_lab = normalize(
        " ".join(item.get("text", "") for item in lab_items)
    )

    require(
        "перед каждым курсом терапии бисфосфонатами" in combined_lab,
        "После повторной очистки/парсинга потеряно условие "
        "«перед каждым курсом терапии бисфосфонатами»",
    )

    require(
        "перед началом терапии бисфосфонатами" in combined_lab,
        "После повторной очистки/парсинга потеряно условие "
        "«перед началом терапии бисфосфонатами»",
    )

    require(
        not any(
            item.get("boundary_status") == "incomplete"
            for item in lab_items
        ),
        "В лабораторной диагностике остались незавершённые блоки",
    )

    print()
    print(f"Метод парсера: {method}")
    print(f"Качество структуры: {parsed.get('quality_check')}")
    print(f"Статус проверки структуры: {status}")
    print(f"Лабораторных блоков: {len(lab_items)}")
    print("[OK] Условия контроля сохранены после полного цикла")
    print("[OK] Склеенные медицинские термины восстановлены")
    print("[OK] Повторная очистка не разрушила текст")
    print()
    print("СКВОЗНОЙ ТЕСТ 520_2 ПРОЙДЕН")


if __name__ == "__main__":
    main()
