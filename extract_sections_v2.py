
import argparse
import json
import re
from pathlib import Path


# Универсальная структура клинических рекомендаций.
# Внутренние подразделы не используются для определения
# границ основных разделов.

SECTIONS = [
    ("terms", None, [
        "Термины и определения",
    ]),
    ("definition", "1.1", [
        "Определение заболевания или состояния",
    ]),
    ("etiology_pathogenesis", "1.2", [
        "Этиология и патогенез заболевания или состояния",
    ]),
    ("epidemiology", "1.3", [
        "Эпидемиология заболевания или состояния",
    ]),
    ("icd10", "1.4", [
        "Особенности кодирования заболевания или состояния",
    ]),
    ("classification", "1.5", [
        "Классификация заболевания или состояния",
    ]),
    ("clinical_picture", "1.6", [
        "Клиническая картина заболевания или состояния",
    ]),
    ("diagnostics", "2", [
        "Диагностика",
    ]),
    ("complaints_anamnesis", "2.1", [
        "Жалобы и анамнез",
    ]),
    ("physical_examination", "2.2", [
        "Физикальное обследование",
    ]),
    ("laboratory_diagnostics", "2.3", [
        "Лабораторные диагностические исследования",
        "Лабораторная диагностика",
    ]),
    ("instrumental_diagnostics", "2.4", [
        "Инструментальные диагностические исследования",
        "Инструментальная диагностика",
    ]),
    ("other_diagnostics", "2.5", [
        "Иные диагностические исследования",
        "Иные диагностические методы",
        "Иная диагностика",
    ]),
    ("treatment", "3", [
        "Лечение",
        "Лечение, включая",
    ]),
    ("rehabilitation", "4", [
        "Реабилитация",
    ]),
]


def normalize_phrase(value):
    return re.sub(r"\s+", " ", value).strip().casefold()


def build_phrase_pattern(phrase):
    return r"\s+".join(
        re.escape(part) for part in phrase.split()
    )


def find_heading_candidates(text, number, aliases):
    """
    Ищет заголовки только в начале строки.

    Для нумерованных заголовков проверяется точное
    соответствие номера структурному номеру раздела.
    """

    candidates = []

    for alias in aliases:

        phrase = build_phrase_pattern(alias)

        if number is None:
            prefix = r"^[ \t]*"
        else:
            escaped_number = re.escape(number)

            prefix = (
                rf"^[ \t]*{escaped_number}\.?"
                rf"[ \t]+"
            )

        pattern = re.compile(
            prefix + phrase + r"(?=$|[\s.,:;—–\-])",
            re.IGNORECASE | re.MULTILINE
        )

        for match in pattern.finditer(text):

            candidates.append({
                "start": match.start(),
                "end": match.end(),
                "number": number,
                "alias": alias,
            })

    # Удаляем дубли совпадений.
    unique = {}

    for candidate in candidates:

        position = candidate["start"]

        if (
            position not in unique
            or len(candidate["alias"]) >
            len(unique[position]["alias"])
        ):
            unique[position] = candidate

    return sorted(
        unique.values(),
        key=lambda item: item["start"]
    )


def find_all_headings(text):
    """
    Собирает все возможные структурные заголовки.
    """

    result = {}

    for key, number, aliases in SECTIONS:

        result[key] = find_heading_candidates(
            text,
            number,
            aliases
        )

    return result


def select_headings(all_candidates):
    """
    Выбирает заголовки в установленной последовательности.

    При наличии нескольких совпадений выбирается последнее
    последовательное вхождение, что помогает отделить
    основную часть документа от оглавления.
    """

    selected = {}
    cursor = -1

    for key, number, aliases in SECTIONS:

        candidates = all_candidates[key]

        available = [
            item for item in candidates
            if item["start"] > cursor
        ]

        if not available:
            selected[key] = None
            continue

        selected[key] = available[-1]

        cursor = selected[key]["start"]

    return selected


def extract_sections(text):

    all_candidates = find_all_headings(text)

    selected = select_headings(all_candidates)

    sections = {}
    warnings = []

    for index, (key, number, aliases) in enumerate(SECTIONS):

        heading = selected.get(key)

        if heading is None:

            sections[key] = {
                "text": "",
                "status": "not_found",
                "heading_number": number,
                "start": None,
                "end": None,
            }

            warnings.append(
                f"Не найден заголовок раздела: {key}"
            )

            continue

        start = heading["start"]

        # Граница — следующий найденный структурный заголовок
        # из универсальной последовательности.
        next_heading = None

        for next_key, next_number, next_aliases in SECTIONS[index + 1:]:

            candidate = selected.get(next_key)

            if candidate is not None and candidate["start"] > start:
                next_heading = candidate
                break

        if next_heading is not None:
            end = next_heading["start"]
            ends_before = next_heading["number"] or "Термины и определения"
        else:
            end = len(text)
            ends_before = "document_end"

        block = text[start:end].strip()

        status = (
            "extracted"
            if len(block) >= 20
            else "too_short"
        )

        sections[key] = {
            "text": block,
            "status": status,
            "heading_number": number,
            "matched_heading": heading["alias"],
            "start": start,
            "end": end,
            "ends_before": ends_before,
        }

        if status == "too_short":

            warnings.append(
                f"Подозрительно короткий раздел: {key}"
            )

    # Специальная проверка границ главы 3.
    treatment = sections.get("treatment", {})
    rehabilitation = sections.get("rehabilitation", {})

    if treatment.get("start") is not None:

        if rehabilitation.get("start") is None:

            warnings.append(
                "Не найден заголовок главы 4. "
                "Граница главы 3 требует ручной проверки."
            )

        elif treatment["end"] != rehabilitation["start"]:

            warnings.append(
                "Глава 3 заканчивается не непосредственно "
                "перед главой 4."
            )

    missing = [
        key
        for key, number, aliases in SECTIONS
        if sections[key]["status"] == "not_found"
    ]

    quality_report = {

        "quality_check": (
            "review_required"
            if missing or warnings
            else "passed"
        ),

        "missing_sections": missing,

        "warnings": warnings,

        "matched_headings": {
            key: {
                "number": sections[key]["heading_number"],
                "alias": sections[key].get("matched_heading"),
                "start": sections[key]["start"],
            }
            for key, number, aliases in SECTIONS
            if sections[key]["start"] is not None
        },

        "note": (
            "Проверка подтверждает обнаружение структурных "
            "заголовков. Медицинская полнота, сохранность "
            "текста и соответствие исходному PDF требуют "
            "отдельной проверки."
        ),
    }

    return sections, quality_report


def main():

    parser = argparse.ArgumentParser(
        description="Универсальный парсер клинических рекомендаций"
    )

    parser.add_argument(
        "--input",
        default="output/749_2.json"
    )

    parser.add_argument(
        "--output",
        default=None
    )

    args = parser.parse_args()

    input_path = Path(args.input)

    if not input_path.exists():

        raise FileNotFoundError(
            f"Не найден исходный файл: {input_path}"
        )

    data = json.loads(
        input_path.read_text(encoding="utf-8")
    )

    full_text = data.get("full_text", "")

    if not full_text.strip():

        raise RuntimeError(
            "В исходном JSON отсутствует full_text"
        )

    sections, quality = extract_sections(full_text)

    result = {

        "id": data.get("id"),

        "title": data.get("title"),

        "source_url": data.get("source_url"),

        "pdf_url": data.get("pdf_url"),

        "pages_count": data.get("pages_count"),

        "extraction_method": "universal_structural_headings_v3",

        "sections": sections,

        "quality_report": quality,
    }

    output_path = (

        Path(args.output)
        if args.output
        else Path("output") /
        f"{data.get('id', 'document')}_sections_v2.json"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output_path.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    report_path = output_path.with_name(
        output_path.stem.replace(
            "_sections_v2",
            ""
        ) + "_quality_report_v2.json"
    )

    report_path.write_text(
        json.dumps(
            quality,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print("\nИЗВЛЕЧЕНИЕ ЗАВЕРШЕНО")

    print("Документ:", data.get("title"))
    print("ID:", data.get("id"))

    print("\nРЕЗУЛЬТАТЫ:")

    for key, number, aliases in SECTIONS:

        item = sections[key]

        print(
            f"{key}: {item['status']} | "
            f"{len(item['text'])} символов | "
            f"до: {item.get('ends_before')}"
        )

    print("\nСТАТУС:", quality["quality_check"])

    print("\nФайл разделов:", output_path)

    print("Отчёт качества:", report_path)

    if quality["warnings"]:

        print("\nПРЕДУПРЕЖДЕНИЯ:")

        for warning in quality["warnings"]:

            print("-", warning)


if __name__ == "__main__":
    main()
