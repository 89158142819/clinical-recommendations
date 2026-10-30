import argparse
import json
import re
from pathlib import Path


# Названия разделов могут немного отличаться в разных клинических рекомендациях.
# Номера подразделов намеренно не зашиты в правила поиска.
HEADING_ALIASES = {
    "definition": [
        "Определение заболевания или состояния",
        "Определение заболевания",
        "Определение состояния",
    ],
    "icd10": [
        "Особенности кодирования заболевания",
        "Кодирование заболевания",
        "Код по МКБ-10",
        "МКБ-10",
    ],
    "laboratory_diagnostics": [
        "Лабораторные диагностические исследования",
        "Лабораторная диагностика",
    ],
    "instrumental_diagnostics": [
        "Инструментальные диагностические исследования",
        "Инструментальная диагностика",
    ],
    "other_diagnostics": [
        "Иные диагностические исследования",
        "Иные диагностические методы",
        "Иная диагностика",
    ],
    "treatment": [
        "Лечение, включая",
        "Лечение",
    ],
    "treatment_conservative": [
        "Консервативное лечение",
    ],
    "treatment_surgical": [
        "Хирургическое лечение",
    ],
}

MAIN_SECTIONS = [
    "definition",
    "icd10",
    "laboratory_diagnostics",
    "instrumental_diagnostics",
    "other_diagnostics",
    "treatment",
]


def flexible_phrase(phrase):
    """Регулярное выражение, допускающее переносы и лишние пробелы в PDF."""
    return r"\s+".join(re.escape(part) for part in phrase.split())


def find_heading(text, aliases):
    """Ищет заголовок в начале строки; возвращает последнее совпадение."""
    matches = []
    for alias in aliases:
        phrase = flexible_phrase(alias)
        if aliases is HEADING_ALIASES["treatment"]:
            # Лечение — глава верхнего уровня (например, «3. Лечение»),
            # а не вложенные заголовки «3.1.1. Лечение ...».
            prefix = r"(?im)^[ \t]*\d+\.[ \t]+"
        else:
            prefix = r"(?im)^[ \t]*(?:\d+(?:\.\d+)*\.?[ \t]+)?"
        pattern = re.compile(prefix + phrase)
        for match in pattern.finditer(text):
            matches.append((match.start(), match.end(), alias))

    if not matches:
        return None

    # В PDF сначала часто идёт оглавление, а затем сам текст.
    # Последнее совпадение обычно относится к основному содержанию.
    return max(matches, key=lambda item: item[0])


def find_next_main_chapter(text, start):
    """Находит следующую главу 4–9, завершающую раздел лечения."""
    pattern = re.compile(
        r"(?im)^[ \t]*[4-9]\.\s+"
        r"(?:Медицинская реабилитация|Профилактика|Организация|"
        r"Дополнительная информация|Критерии|Приложения|Заключение|\S)"
    )
    match = pattern.search(text, start)
    return match.start() if match else None


def extract_block(text, start, end, key):
    if start is None:
        return {"text": "", "status": "not_found"}

    if end is None or end <= start:
        block = text[start:].strip()
        status = "extracted_end_not_found"
    else:
        block = text[start:end].strip()
        status = "extracted"

    if len(block) < 30:
        status = "too_short"

    return {"text": block, "status": status}


def main():
    parser = argparse.ArgumentParser(
        description="Выделение разделов клинической рекомендации по заголовкам"
    )
    parser.add_argument(
        "--input",
        default="output/749_2.json",
        help="Исходный JSON после скачивания PDF",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Путь для JSON с выделенными разделами",
    )
    args = parser.parse_args()

    source = Path(args.input)
    if not source.exists():
        raise FileNotFoundError(f"Не найден исходный файл: {source}")

    data = json.loads(source.read_text(encoding="utf-8"))
    text = data.get("full_text", "")
    if not text.strip():
        raise RuntimeError("В исходном JSON отсутствует full_text")

    # Не схлопываем пробелы: сохраняем строки и маркеры страниц.
    starts = {}
    matched_aliases = {}
    for key, aliases in HEADING_ALIASES.items():
        found = find_heading(text, aliases)
        starts[key] = found[0] if found else None
        matched_aliases[key] = found[2] if found else None

    sections = {}
    warnings = []

    # Основные разделы ограничиваются следующим найденным разделом.
    for key in MAIN_SECTIONS:
        start = starts[key]
        if start is None:
            sections[key] = {"text": "", "status": "not_found"}
            warnings.append(f"Не найден заголовок раздела: {key}")
            continue

        later_starts = [
            position
            for other_key, position in starts.items()
            if position is not None and position > start and other_key != key
        ]

        if key == "treatment":
            chapter_end = find_next_main_chapter(text, start + 1)
            end = chapter_end
        else:
            end = min(later_starts) if later_starts else None

        sections[key] = extract_block(text, start, end, key)
        if sections[key]["status"] == "extracted_end_not_found":
            warnings.append(f"Не найдена граница окончания раздела: {key}")
        if sections[key]["status"] == "too_short":
            warnings.append(f"Подозрительно короткий раздел: {key}")

    # Дополнительные подразделы лечения. Они не обязательны для всех документов.
    for key in ("treatment_conservative", "treatment_surgical"):
        start = starts[key]
        if start is None:
            sections[key] = {"text": "", "status": "not_found"}
            continue

        possible_ends = [
            position
            for other_key, position in starts.items()
            if position is not None and position > start and other_key != key
        ]
        chapter_end = find_next_main_chapter(text, start + 1)
        if chapter_end is not None:
            possible_ends.append(chapter_end)
        end = min(possible_ends) if possible_ends else None
        sections[key] = extract_block(text, start, end, key)

    missing_main = [
        key for key in MAIN_SECTIONS
        if sections.get(key, {}).get("status") == "not_found"
    ]

    quality_report = {
        "id": data.get("id"),
        "title": data.get("title"),
        "quality_check": "passed" if not missing_main and not warnings else "review_required",
        "errors": [f"Не извлечён обязательный раздел: {key}" for key in missing_main],
        "warnings": warnings,
        "matched_headings": matched_aliases,
        "note": (
            "Автоматическая проверка подтверждает наличие фрагментов, "
            "но не заменяет визуальную проверку полноты и точности медицинского текста."
        ),
    }

    result = {
        "id": data.get("id"),
        "title": data.get("title"),
        "source_url": data.get("source_url"),
        "pdf_url": data.get("pdf_url"),
        "pages_count": data.get("pages_count"),
        "extraction_method": "heading_based_v2",
        "sections": sections,
        "quality_report": quality_report,
    }

    output = Path(args.output) if args.output else Path("output") / f"{data.get('id', 'document')}_sections_v2.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report_file = output.with_name(output.stem.replace("_sections_v2", "") + "_quality_report_v2.json")
    report_file.write_text(
        json.dumps(quality_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Извлечение завершено")
    print("Документ:", data.get("title"), f"({data.get('id')})")
    print("Файл разделов:", output)
    print("Отчёт качества:", report_file)
    print("Статус:", quality_report["quality_check"])
    for key in MAIN_SECTIONS:
        item = sections[key]
        print(f"{key}: {item['status']} ({len(item['text'])} символов)")
    if warnings:
        print("Предупреждения:")
        for warning in warnings:
            print("-", warning)


if __name__ == "__main__":
    main()
