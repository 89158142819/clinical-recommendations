
import argparse
import json
import re
from pathlib import Path


# ============================================================
# Настройки проекта
# ============================================================

DEFAULT_INPUT = Path("output/749_2.json")

EXTRACTION_METHOD = "universal_structural_headings_v4"


# ============================================================
# Структура клинической рекомендации
#
# Важно:
# 1. Порядок разделов соответствует универсальной структуре КР.
# 2. Внутренние подразделы лечения не определяют границы главы 3.
# 3. Альтернативные названия используются только для поиска.
# ============================================================

SECTIONS = [
    {
        "key": "terms",
        "number": None,
        "aliases": [
            "Термины и определения",
        ],
    },
    {
        "key": "definition",
        "number": "1.1",
        "aliases": [
            "Определение заболевания или состояния",
        ],
    },
    {
        "key": "etiology_pathogenesis",
        "number": "1.2",
        "aliases": [
            "Этиология и патогенез заболевания или состояния",
        ],
    },
    {
        "key": "epidemiology",
        "number": "1.3",
        "aliases": [
            "Эпидемиология заболевания или состояния",
        ],
    },
    {
        "key": "icd10",
        "number": "1.4",
        "aliases": [
            "Особенности кодирования заболевания или состояния",
        ],
    },
    {
        "key": "classification",
        "number": "1.5",
        "aliases": [
            "Классификация заболевания или состояния",
            "Классификация заболевания заболевания или состояния",
        ],
    },
    {
        "key": "clinical_picture",
        "number": "1.6",
        "aliases": [
            "Клиническая картина заболевания или состояния",
            "Клиническая картина заболевания",
        ],
    },
    {
        "key": "diagnostics",
        "number": "2",
        "aliases": [
            "Диагностика",
            "Диагностика заболевания или состояния",
        ],
    },
    {
        "key": "complaints_anamnesis",
        "number": "2.1",
        "aliases": [
            "Жалобы и анамнез",
        ],
    },
    {
        "key": "physical_examination",
        "number": "2.2",
        "aliases": [
            "Физикальное обследование",
        ],
    },
    {
        "key": "laboratory_diagnostics",
        "number": "2.3",
        "aliases": [
            "Лабораторные диагностические исследования",
            "Лабораторная диагностика",
        ],
    },
    {
        "key": "instrumental_diagnostics",
        "number": "2.4",
        "aliases": [
            "Инструментальные диагностические исследования",
            "Инструментальная диагностика",
        ],
    },
    {
        "key": "other_diagnostics",
        "number": "2.5",
        "aliases": [
            "Иные диагностические исследования",
            "Иные диагностические методы",
            "Иная диагностика",
        ],
    },
    {
        "key": "treatment",
        "number": "3",
        "aliases": [
            "Лечение",
            "Лечение, включая",
        ],
    },
    {
        "key": "rehabilitation",
        "number": "4",
        "aliases": [
            "Реабилитация",
            "Медицинская реабилитация",
            "Медицинская реабилитация и санаторно-курортное лечение",
        ],
    },
]


# ============================================================
# Формирование регулярного выражения для названия заголовка
# ============================================================

def build_phrase_pattern(phrase):
    """
    Формирует шаблон для поиска заголовка.

    Учитывает:
    - переносы строк;
    - несколько пробелов;
    - пробелы вокруг дефиса;
    - разные варианты дефиса.
    """

    parts = re.split(r"\s+", phrase.strip())

    pattern_parts = []

    for part in parts:
        escaped = re.escape(part)

        # Дефис может быть записан с пробелами или без них.
        escaped = escaped.replace(
            r"\-",
            r"\s*[-–—]\s*"
        )

        pattern_parts.append(escaped)

    return r"\s+".join(pattern_parts)


# ============================================================
# Поиск кандидатов на заголовки
# ============================================================

def find_heading_candidates(text, section):
    """
    Ищет заголовки только в начале строки.

    Для нумерованных заголовков:
    - допускает отсутствие пробела после номера;
    - проверяет точный номер;
    - не путает 2 и 2.1;
    - допускает переносы внутри названия.

    Возвращает все найденные совпадения с позициями.
    """

    candidates = []

    number = section["number"]

    if number is None:
        number_pattern = ""
    else:
        escaped_number = re.escape(number)

        number_pattern = (
            r"^\s*"
            + escaped_number
            + r"\s*\.?\s*"
            + r"(?![\d])"
        )

    for alias in section["aliases"]:

        phrase_pattern = build_phrase_pattern(alias)

        if number is None:
            pattern = (
                r"(?im)^[ \t]*"
                + phrase_pattern
            )
        else:
            pattern = (
                r"(?im)"
                + number_pattern
                + phrase_pattern
            )

        for match in re.finditer(pattern, text):

            start = match.start()

            candidates.append({
                "key": section["key"],
                "number": number,
                "alias": alias,
                "start": start,
                "matched_text": match.group(0),
            })

    # Удаляем дубликаты, найденные по разным aliases
    # на одной позиции.
    unique = {}

    for candidate in candidates:
        position = candidate["start"]

        if position not in unique:
            unique[position] = candidate
        else:
            # При совпадении сохраняем более длинный вариант.
            old_length = len(unique[position]["matched_text"])
            new_length = len(candidate["matched_text"])

            if new_length > old_length:
                unique[position] = candidate

    return sorted(
        unique.values(),
        key=lambda item: item["start"]
    )


# ============================================================
# Выбор заголовков основного текста
# ============================================================

def select_headings(all_candidates):
    """
    Выбирает последовательность заголовков.

    Поскольку оглавление обычно расположено раньше основного
    текста, при выборе используется обратный проход:

    - сначала ищется последнее совпадение главы 4;
    - затем последнее совпадение главы 3 перед главой 4;
    - затем предыдущие разделы по порядку.

    Это позволяет не использовать оглавление вместо
    основного текста, если соответствующие заголовки
    присутствуют в основном тексте.

    Если заголовок отсутствует, он не подменяется догадкой.
    """

    selected = {}

    next_start = float("inf")

    for section in reversed(SECTIONS):

        key = section["key"]

        candidates = all_candidates.get(key, [])

        valid_candidates = [
            candidate
            for candidate in candidates
            if candidate["start"] < next_start
        ]

        if not valid_candidates:
            continue

        chosen = max(
            valid_candidates,
            key=lambda item: item["start"]
        )

        selected[key] = chosen

        next_start = chosen["start"]

    return {
        section["key"]: selected[section["key"]]
        for section in SECTIONS
        if section["key"] in selected
    }


# ============================================================
# Извлечение разделов
# ============================================================

def extract_sections(text):
    """
    Извлекает разделы по найденным структурным заголовкам.

    Каждый раздел заканчивается непосредственно перед
    следующим найденным структурным заголовком.

    Глава 3 «Лечение» заканчивается исключительно
    перед фактическим заголовком главы 4.

    Подразделы 3.1, 3.1.1, 3.1.2 и 3.2
    не используются для определения границ лечения.
    """

    all_candidates = {}

    for section in SECTIONS:
        all_candidates[section["key"]] = (
            find_heading_candidates(text, section)
        )

    matched_headings = select_headings(all_candidates)

    extracted = {}

    ordered_found = [
        section
        for section in SECTIONS
        if section["key"] in matched_headings
    ]

    for index, section in enumerate(ordered_found):

        key = section["key"]

        start = matched_headings[key]["start"]

        if index + 1 < len(ordered_found):
            next_key = ordered_found[index + 1]["key"]
            end = matched_headings[next_key]["start"]
        else:
            end = len(text)

        extracted[key] = {
            "start": start,
            "end": end,
            "text": text[start:end].strip(),
        }

    return extracted, matched_headings, all_candidates


# ============================================================
# Проверка последовательности заголовков
# ============================================================

def check_heading_order(matched_headings):

    warnings = []

    previous_key = None
    previous_start = -1

    for section in SECTIONS:

        key = section["key"]

        if key not in matched_headings:
            continue

        current_start = matched_headings[key]["start"]

        if current_start <= previous_start:
            warnings.append(
                f"Нарушен порядок заголовков: {key}"
            )

        previous_key = key
        previous_start = current_start

    return warnings


# ============================================================
# Контроль главы 3 «Лечение»
# ============================================================

def check_treatment_boundary(extracted, matched_headings):

    warnings = []

    if "treatment" not in matched_headings:
        warnings.append(
            "Не найден заголовок главы 3. "
            "Границы лечения не определены."
        )
        return warnings

    if "rehabilitation" not in matched_headings:
        warnings.append(
            "Не найден заголовок главы 4. "
            "Граница главы 3 требует ручной проверки."
        )
        return warnings

    treatment = extracted.get("treatment")
    rehabilitation = matched_headings["rehabilitation"]

    if treatment is None:
        warnings.append(
            "Не удалось извлечь текст главы 3."
        )
        return warnings

    if treatment["end"] != rehabilitation["start"]:
        warnings.append(
            "Конец главы 3 не совпадает с началом главы 4."
        )

    if treatment["start"] >= rehabilitation["start"]:
        warnings.append(
            "Некорректный порядок границ главы 3 и главы 4."
        )

    if not treatment["text"].strip():
        warnings.append(
            "Текст главы 3 пустой."
        )

    return warnings


# ============================================================
# Формирование отчёта качества
# ============================================================

def build_quality_report(
    text,
    extracted,
    matched_headings,
    all_candidates
):

    warnings = []

    missing_sections = []

    for section in SECTIONS:

        key = section["key"]

        if key not in matched_headings:
            missing_sections.append(key)

            warnings.append(
                f"Не найден заголовок раздела: {key}"
            )

    warnings.extend(
        check_heading_order(matched_headings)
    )

    warnings.extend(
        check_treatment_boundary(
            extracted,
            matched_headings
        )
    )

    # Контроль пустых извлечённых разделов.
    for key, section_data in extracted.items():

        if not section_data["text"].strip():
            warnings.append(
                f"Раздел {key} найден, но его текст пустой."
            )

    # Для главы 3 проверяем, что границы определены
    # строго по заголовкам 3 и 4.
    treatment_boundary_ok = False

    if (
        "treatment" in extracted
        and "rehabilitation" in matched_headings
    ):
        treatment_boundary_ok = (
            extracted["treatment"]["end"]
            == matched_headings["rehabilitation"]["start"]
        )

    # Дополнительная проверка: в тексте лечения
    # должен присутствовать хотя бы один содержательный
    # фрагмент после заголовка.
    if "treatment" in extracted:

        treatment_text = extracted["treatment"]["text"]

        if len(treatment_text) < 100:
            warnings.append(
                "Подозрительно короткий текст главы 3. "
                "Требуется ручная проверка."
            )

    # Если обязательные заголовки найдены и предупреждений
    # нет, результат может получить passed.
    # Наличие заголовков само по себе не доказывает
    # медицинскую полноту документа.
    if not missing_sections and not warnings and treatment_boundary_ok:
        quality_check = "passed"
    else:
        quality_check = "review_required"

    matched_report = {}

    for key, heading in matched_headings.items():

        matched_report[key] = {
            "number": heading["number"],
            "alias": heading["alias"],
            "start": heading["start"],
            "matched_text": heading["matched_text"],
            "candidate_count": len(all_candidates.get(key, [])),
        }

    return {
        "quality_check": quality_check,
        "extraction_method": EXTRACTION_METHOD,
        "text_length": len(text),
        "missing_sections": missing_sections,
        "warnings": warnings,
        "matched_headings": matched_report,
        "treatment_boundary_check": {
            "passed": treatment_boundary_ok,
            "treatment_start": (
                extracted["treatment"]["start"]
                if "treatment" in extracted
                else None
            ),
            "treatment_end": (
                extracted["treatment"]["end"]
                if "treatment" in extracted
                else None
            ),
            "rehabilitation_start": (
                matched_headings["rehabilitation"]["start"]
                if "rehabilitation" in matched_headings
                else None
            ),
        },
        "note": (
            "Проверка подтверждает обнаружение структурных "
            "заголовков и определение границ разделов. "
            "Медицинская полнота, сохранность текста и "
            "соответствие исходному PDF требуют отдельной проверки."
        ),
    }


# ============================================================
# Основная функция
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Извлечение разделов клинической рекомендации"
    )

    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="Путь к исходному JSON"
    )

    parser.add_argument(
        "--output",
        default=None,
        help="Путь к JSON с извлечёнными разделами"
    )

    parser.add_argument(
        "--report",
        default=None,
        help="Путь к отчёту качества"
    )

    args = parser.parse_args()

    input_path = Path(args.input)

    if not input_path.exists():
        raise FileNotFoundError(
            f"Входной файл не найден: {input_path}"
        )

    with input_path.open("r", encoding="utf-8") as file:
        source_data = json.load(file)

    if "full_text" not in source_data:
        raise ValueError(
            "В исходном JSON отсутствует поле full_text."
        )

    full_text = source_data["full_text"]

    if not isinstance(full_text, str) or not full_text.strip():
        raise ValueError(
            "Поле full_text пустое или имеет неверный формат."
        )

    document_id = source_data.get("id", input_path.stem)

    output_path = (
        Path(args.output)
        if args.output
        else Path(f"output/{document_id}_sections_v2.json")
    )

    report_path = (
        Path(args.report)
        if args.report
        else Path(f"output/{document_id}_quality_report_v2.json")
    )

    # Извлечение.
    extracted, matched_headings, all_candidates = (
        extract_sections(full_text)
    )

    # Отчёт качества.
    quality_report = build_quality_report(
        full_text,
        extracted,
        matched_headings,
        all_candidates
    )

    # Итоговый JSON.
    result = {
        "id": document_id,
        "title": source_data.get("title"),
        "extraction_method": EXTRACTION_METHOD,
        "quality_check": quality_report["quality_check"],
        "sections": {
            key: value["text"]
            for key, value in extracted.items()
        },
        "section_positions": {
            key: {
                "start": value["start"],
                "end": value["end"],
                "length": len(value["text"]),
            }
            for key, value in extracted.items()
        },
        "quality_report": quality_report,
    }

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    report_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2
        )

    with report_path.open("w", encoding="utf-8") as file:
        json.dump(
            quality_report,
            file,
            ensure_ascii=False,
            indent=2
        )

    # Вывод результатов в GitHub Actions.
    print("=" * 60)
    print("РЕЗУЛЬТАТ ИЗВЛЕЧЕНИЯ КЛИНИЧЕСКОЙ РЕКОМЕНДАЦИИ")
    print("=" * 60)

    print(f"Документ: {document_id}")
    print(f"Метод: {EXTRACTION_METHOD}")
    print(f"Длина исходного текста: {len(full_text)}")
    print()

    print(f"Статус: {quality_report['quality_check']}")
    print()

    print("НАЙДЕННЫЕ РАЗДЕЛЫ:")

    for section in SECTIONS:

        key = section["key"]

        if key in matched_headings:

            heading = matched_headings[key]

            print(
                f"[OK] {key}: "
                f"позиция {heading['start']}"
            )

        else:
            print(f"[НЕТ] {key}")

    print()
    print("ПРОВЕРКА ГРАНИЦЫ ЛЕЧЕНИЯ:")

    boundary = quality_report["treatment_boundary_check"]

    print(
        f"Начало лечения: {boundary['treatment_start']}"
    )

    print(
        f"Конец лечения: {boundary['treatment_end']}"
    )

    print(
        f"Начало реабилитации: "
        f"{boundary['rehabilitation_start']}"
    )

    print(
        f"Граница подтверждена: {boundary['passed']}"
    )

    if quality_report["warnings"]:

        print()
        print("ПРЕДУПРЕЖДЕНИЯ:")

        for warning in quality_report["warnings"]:
            print(f"- {warning}")

    print()
    print(f"Файл разделов: {output_path}")
    print(f"Отчёт качества: {report_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
