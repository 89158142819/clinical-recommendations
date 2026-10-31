
import argparse
import json
import re
from pathlib import Path


# ============================================================
# Настройки проекта
# ============================================================

DEFAULT_INPUT = Path("output/749_2.json")

EXTRACTION_METHOD = "universal_structural_headings_v5"


# ============================================================
# Структура клинической рекомендации
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

            candidates.append({
                "key": section["key"],
                "number": number,
                "alias": alias,
                "start": match.start(),
                "matched_text": match.group(0),
            })

    # Удаляем дубликаты на одной позиции.
    unique = {}

    for candidate in candidates:

        position = candidate["start"]

        if position not in unique:
            unique[position] = candidate
        else:
            old_length = len(
                unique[position]["matched_text"]
            )

            new_length = len(
                candidate["matched_text"]
            )

            if new_length > old_length:
                unique[position] = candidate

    return sorted(
        unique.values(),
        key=lambda item: item["start"]
    )


# ============================================================
# Поиск следующей крупной главы
# ============================================================

def find_next_major_chapter(text, chapter_number, after_position):
    """
    Ищет заголовок следующей крупной главы.

    Например:
    5. Профилактика и диспансерное наблюдение

    Учитывает:
    - начало заголовка с новой строки;
    - точку или закрывающую скобку после номера;
    - наличие пробела или его отсутствие;
    - заглавную русскую букву после номера.

    Не принимает за главу 5 подразделы:
    5.1
    5.1.1
    5.2

    Ищет только после указанной позиции, чтобы не выбрать
    заголовок из оглавления.
    """

    number = re.escape(str(chapter_number))

    pattern = (
        r"(?im)^[ \t]*"
        + number
        + r"\s*[.)]\s*"
        + r"(?=[А-ЯЁ])"
        + r"[^\n]{3,250}"
    )

    candidates = []

    for match in re.finditer(pattern, text):

        if match.start() <= after_position:
            continue

        candidates.append({
            "start": match.start(),
            "matched_text": match.group(0).strip(),
        })

    if not candidates:
        return None, []

    # Берём первое совпадение после начала главы 4.
    candidates.sort(key=lambda item: item["start"])

    return candidates[0], candidates


# ============================================================
# Выбор заголовков основного текста
# ============================================================

def select_headings(all_candidates):
    """
    Выбирает последовательность заголовков.

    Обратный проход позволяет использовать последние
    подходящие совпадения, а не заголовки оглавления.
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
    Извлекает 15 основных разделов.

    Особые правила:

    Глава 3 заканчивается перед заголовком главы 4.

    Глава 4 заканчивается перед заголовком главы 5.

    Внутренние подразделы глав 3 и 4 не используются
    для определения границ крупных разделов.
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

    # --------------------------------------------------------
    # Дополнительная граница главы 4.
    # --------------------------------------------------------

    chapter5_heading = None
    chapter5_candidates = []

    if "rehabilitation" in extracted:

        rehabilitation_start = (
            extracted["rehabilitation"]["start"]
        )

        chapter5_heading, chapter5_candidates = (
            find_next_major_chapter(
                text=text,
                chapter_number=5,
                after_position=rehabilitation_start
            )
        )

        if chapter5_heading:

            rehabilitation_end = (
                chapter5_heading["start"]
            )

            extracted["rehabilitation"]["end"] = (
                rehabilitation_end
            )

            extracted["rehabilitation"]["text"] = (
                text[
                    rehabilitation_start:rehabilitation_end
                ].strip()
            )

    return (
        extracted,
        matched_headings,
        all_candidates,
        chapter5_heading,
        chapter5_candidates,
    )


# ============================================================
# Проверка последовательности заголовков
# ============================================================

def check_heading_order(matched_headings):

    warnings = []

    previous_start = -1

    for section in SECTIONS:

        key = section["key"]

        if key not in matched_headings:
            continue

        current_start = (
            matched_headings[key]["start"]
        )

        if current_start <= previous_start:

            warnings.append(
                f"Нарушен порядок заголовков: {key}"
            )

        previous_start = current_start

    return warnings


# ============================================================
# Контроль границы главы 3 «Лечение»
# ============================================================

def check_treatment_boundary(extracted, matched_headings):

    warnings = []

    if "treatment" not in matched_headings:

        warnings.append(
            "Не найден заголовок главы 3."
        )

        return warnings

    if "rehabilitation" not in matched_headings:

        warnings.append(
            "Не найден заголовок главы 4."
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
# Контроль границы главы 4 «Реабилитация»
# ============================================================

def check_rehabilitation_boundary(
    extracted,
    matched_headings,
    chapter5_heading
):

    warnings = []

    if "rehabilitation" not in extracted:

        warnings.append(
            "Не удалось извлечь текст главы 4."
        )

        return warnings

    if chapter5_heading is None:

        warnings.append(
            "Не найден заголовок главы 5 после главы 4. "
            "Граница реабилитации не подтверждена."
        )

        return warnings

    rehabilitation = extracted["rehabilitation"]

    if rehabilitation["end"] != chapter5_heading["start"]:

        warnings.append(
            "Конец главы 4 не совпадает с началом главы 5."
        )

    if rehabilitation["start"] >= chapter5_heading["start"]:

        warnings.append(
            "Некорректный порядок границ глав 4 и 5."
        )

    if not rehabilitation["text"].strip():

        warnings.append(
            "Текст главы 4 пустой."
        )

    return warnings


# ============================================================
# Формирование отчёта качества
# ============================================================

def build_quality_report(
    text,
    extracted,
    matched_headings,
    all_candidates,
    chapter5_heading,
    chapter5_candidates
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

    warnings.extend(
        check_rehabilitation_boundary(
            extracted,
            matched_headings,
            chapter5_heading
        )
    )

    # Проверка пустых разделов.
    for key, section_data in extracted.items():

        if not section_data["text"].strip():

            warnings.append(
                f"Раздел {key} найден, но его текст пустой."
            )

    # --------------------------------------------------------
    # Проверка границы главы 3.
    # --------------------------------------------------------

    treatment_boundary_ok = False

    if (
        "treatment" in extracted
        and "rehabilitation" in matched_headings
    ):

        treatment_boundary_ok = (
            extracted["treatment"]["end"]
            == matched_headings["rehabilitation"]["start"]
        )

    # --------------------------------------------------------
    # Проверка границы главы 4.
    # --------------------------------------------------------

    rehabilitation_boundary_ok = False

    if (
        "rehabilitation" in extracted
        and chapter5_heading is not None
    ):

        rehabilitation_boundary_ok = (
            extracted["rehabilitation"]["end"]
            == chapter5_heading["start"]
        )

    # --------------------------------------------------------
    # Контроль объёма лечения.
    # --------------------------------------------------------

    if "treatment" in extracted:

        treatment_text = extracted["treatment"]["text"]

        if len(treatment_text) < 100:

            warnings.append(
                "Подозрительно короткий текст главы 3. "
                "Требуется ручная проверка."
            )

    # --------------------------------------------------------
    # Контроль объёма реабилитации.
    # --------------------------------------------------------

    if "rehabilitation" in extracted:

        rehabilitation_text = (
            extracted["rehabilitation"]["text"]
        )

        if len(rehabilitation_text) < 100:

            warnings.append(
                "Подозрительно короткий текст главы 4. "
                "Требуется ручная проверка."
            )

    # --------------------------------------------------------
    # Итоговый статус.
    # --------------------------------------------------------

    if (
        not missing_sections
        and not warnings
        and treatment_boundary_ok
        and rehabilitation_boundary_ok
    ):

        quality_check = "passed"

    else:

        quality_check = "review_required"

    # --------------------------------------------------------
    # Отчёт по найденным заголовкам.
    # --------------------------------------------------------

    matched_report = {}

    for key, heading in matched_headings.items():

        matched_report[key] = {
            "number": heading["number"],
            "alias": heading["alias"],
            "start": heading["start"],
            "matched_text": heading["matched_text"],
            "candidate_count": len(
                all_candidates.get(key, [])
            ),
        }

    # --------------------------------------------------------
    # Отчёт по главе 5.
    # --------------------------------------------------------

    chapter5_report = None

    if chapter5_heading is not None:

        chapter5_report = {
            "start": chapter5_heading["start"],
            "matched_text": chapter5_heading["matched_text"],
            "candidate_count": len(chapter5_candidates),
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

        "rehabilitation_boundary_check": {

            "passed": rehabilitation_boundary_ok,

            "rehabilitation_start": (
                extracted["rehabilitation"]["start"]
                if "rehabilitation" in extracted
                else None
            ),

            "rehabilitation_end": (
                extracted["rehabilitation"]["end"]
                if "rehabilitation" in extracted
                else None
            ),

            "chapter5_start": (
                chapter5_heading["start"]
                if chapter5_heading
                else None
            ),

            "chapter5_heading": chapter5_report,
        },

        "note": (
            "Проверка подтверждает обнаружение структурных "
            "заголовков и определение границ глав 3 и 4. "
            "Медицинская полнота, сохранность текста и "
            "соответствие исходному PDF требуют отдельной проверки."
        ),
    }


# ============================================================
# Основная функция
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Извлечение разделов клинической рекомендации"
        )
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

    with input_path.open(
        "r",
        encoding="utf-8"
    ) as file:

        source_data = json.load(file)

    if "full_text" not in source_data:

        raise ValueError(
            "В исходном JSON отсутствует поле full_text."
        )

    full_text = source_data["full_text"]

    if (
        not isinstance(full_text, str)
        or not full_text.strip()
    ):

        raise ValueError(
            "Поле full_text пустое или имеет неверный формат."
        )

    document_id = source_data.get(
        "id",
        input_path.stem
    )

    output_path = (
        Path(args.output)
        if args.output
        else Path(
            f"output/{document_id}_sections_v2.json"
        )
    )

    report_path = (
        Path(args.report)
        if args.report
        else Path(
            f"output/{document_id}_quality_report_v2.json"
        )
    )

    # --------------------------------------------------------
    # Извлечение разделов.
    # --------------------------------------------------------

    (
        extracted,
        matched_headings,
        all_candidates,
        chapter5_heading,
        chapter5_candidates,
    ) = extract_sections(full_text)

    # --------------------------------------------------------
    # Формирование отчёта качества.
    # --------------------------------------------------------

    quality_report = build_quality_report(
        full_text,
        extracted,
        matched_headings,
        all_candidates,
        chapter5_heading,
        chapter5_candidates,
    )

    # --------------------------------------------------------
    # Формирование итогового JSON.
    # --------------------------------------------------------

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

    with output_path.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2
        )

    with report_path.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            quality_report,
            file,
            ensure_ascii=False,
            indent=2
        )

    # --------------------------------------------------------
    # Вывод результатов в GitHub Actions.
    # --------------------------------------------------------

    print("=" * 70)

    print(
        "РЕЗУЛЬТАТ ИЗВЛЕЧЕНИЯ КЛИНИЧЕСКОЙ РЕКОМЕНДАЦИИ"
    )

    print("=" * 70)

    print(f"Документ: {document_id}")

    print(f"Метод: {EXTRACTION_METHOD}")

    print(f"Длина исходного текста: {len(full_text)}")

    print()

    print(
        f"Статус: {quality_report['quality_check']}"
    )

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

    # --------------------------------------------------------
    # Вывод границы главы 3.
    # --------------------------------------------------------

    print()

    print("ПРОВЕРКА ГРАНИЦЫ ЛЕЧЕНИЯ:")

    treatment_boundary = (
        quality_report["treatment_boundary_check"]
    )

    print(
        "Начало лечения:",
        treatment_boundary["treatment_start"]
    )

    print(
        "Конец лечения:",
        treatment_boundary["treatment_end"]
    )

    print(
        "Начало реабилитации:",
        treatment_boundary["rehabilitation_start"]
    )

    print(
        "Граница подтверждена:",
        treatment_boundary["passed"]
    )

    # --------------------------------------------------------
    # Вывод границы главы 4.
    # --------------------------------------------------------

    print()

    print("ПРОВЕРКА ГРАНИЦЫ РЕАБИЛИТАЦИИ:")

    rehabilitation_boundary = (
        quality_report["rehabilitation_boundary_check"]
    )

    print(
        "Начало реабилитации:",
        rehabilitation_boundary["rehabilitation_start"]
    )

    print(
        "Конец реабилитации:",
        rehabilitation_boundary["rehabilitation_end"]
    )

    print(
        "Начало главы 5:",
        rehabilitation_boundary["chapter5_start"]
    )

    if chapter5_heading:

        print(
            "Заголовок главы 5:",
            chapter5_heading["matched_text"]
        )

    else:

        print("Заголовок главы 5: НЕ НАЙДЕН")

    print(
        "Граница подтверждена:",
        rehabilitation_boundary["passed"]
    )

    # --------------------------------------------------------
    # Предупреждения.
    # --------------------------------------------------------

    if quality_report["warnings"]:

        print()

        print("ПРЕДУПРЕЖДЕНИЯ:")

        for warning in quality_report["warnings"]:

            print(f"- {warning}")

    # --------------------------------------------------------
    # Итог.
    # --------------------------------------------------------

    print()

    print(f"Файл разделов: {output_path}")

    print(f"Отчёт качества: {report_path}")

    print("=" * 70)


if __name__ == "__main__":
    main()
