
import argparse
import json
import re
from pathlib import Path


# ============================================================
# Настройки проекта
# ============================================================

DEFAULT_INPUT = Path("output/749_2.json")

EXTRACTION_METHOD = "universal_structural_headings_v7"

OPTIONAL_SECTION_KEYS = {
    "other_diagnostics",
}


# ============================================================
# Структура клинической рекомендации
# ============================================================

SECTIONS = [
    {
        "key": "terms",
        "number": None,
        "aliases": ["Термины и определения"],
    },
    {
        "key": "definition",
        "number": "1.1",
        "aliases": [
            "Определение заболевания или состояния",
            "Определеие заболевания или состояния",
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
            "Особенности кодирования по Международной статистической классификации болезней и проблем, связанных со здоровьем",
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
        "numbers": [
            "2.1",
            "2.1.1",
        ],
        "aliases": [
            "Жалобы и анамнез",
        ],
    },
    {
        "key": "physical_examination",
        "number": "2.2",
        "numbers": [
            "2.2",
            "2.1.2",
        ],
        "aliases": [
            "Физикальное обследование",
        ],
    },
    {
        "key": "laboratory_diagnostics",
        "number": "2.3",
        "numbers": [
            "2.3",
            "2.1.3",
        ],
        "aliases": [
            "Лабораторные диагностические исследования",
            "Лабораторные диагностические обследования",
            "Лабораторная диагностика",
        ],
    },
    {
        "key": "instrumental_diagnostics",
        "number": "2.4",
        "numbers": [
            "2.4",
            "2.1.3",
        ],
        "aliases": [
            "Инструментальные диагностические исследования",
            "Инструментальная диагностика",
        ],
    },
    {
        "key": "other_diagnostics",
        "number": "2.5",
        "numbers": [
            "2.5",
            "2.1.4",
        ],
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
# Формирование регулярного выражения для заголовка
# ============================================================

def build_phrase_pattern(phrase):

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
# Формирование шаблонов нумерации
# ============================================================

def build_number_patterns(section):

    key = section["key"]

    if key == "treatment":

        # Обычная запись главы 3 и ошибочная запись .3.
        return [
            (
                r"^\s*3\s*\.?\s*(?![\d])",
                "3",
            ),
            (
                r"^\s*\.\s*3\s*\.?\s*(?![\d])",
                ".3",
            ),
            (
                r"^\s*\.3\s*\.?\s*(?![\d])",
                ".3",
            ),
        ]

    numbers = section.get(
        "numbers",
        [section["number"]]
    )

    result = []

    for number in numbers:

        escaped_number = re.escape(number)

        result.append((
            (
                r"^\s*"
                + escaped_number
                + r"\s*\.?\s*"
                + r"(?![\d])"
            ),
            number,
        ))

    return result


# ============================================================
# Поиск кандидатов на заголовки
# ============================================================

def find_heading_candidates(text, section):

    candidates = []

    number = section["number"]

    if number is None:

        number_patterns = [
            ("", None)
        ]

    else:

        number_patterns = build_number_patterns(
            section
        )

    for alias in section["aliases"]:

        phrase_pattern = build_phrase_pattern(alias)

        for number_pattern, matched_number in number_patterns:

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
                    "number": matched_number,
                    "alias": alias,
                    "start": match.start(),
                    "matched_text": match.group(0),
                })

    # Удаляем дублирующиеся совпадения по одной позиции.
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
# Нормализация названий глав
# ============================================================

def normalize_heading_text(value):

    value = value.lower().replace("ё", "е")

    return re.sub(
        r"[^а-яa-z0-9]",
        "",
        value
    )


# ============================================================
# Очистка строки оглавления
# ============================================================

def clean_toc_heading_line(line):

    value = line.strip()

    value = re.sub(
        r"^\s*5(?:\s*[.)])?\s*",
        "",
        value
    )

    value = re.split(
        r"\.{2,}|…{1,}",
        value,
        maxsplit=1
    )[0]

    value = re.sub(
        r"\s+\d{1,4}\s*$",
        "",
        value
    )

    return value.strip(" \t.-–—")


# ============================================================
# Поиск названия главы 5 в оглавлении
# ============================================================

def find_chapter_title_in_contents(text, before_position):

    pattern = (
        r"(?im)^[ \t]*"
        r"5(?:\s*[.)])?\s+"
        r"(?=[А-ЯЁ])"
        r"([^\n]{10,300})"
    )

    for match in re.finditer(pattern, text):

        if match.start() >= before_position:
            break

        raw_line = match.group(1)

        title = clean_toc_heading_line(
            "5. " + raw_line
        )

        normalized = normalize_heading_text(title)

        if len(normalized) < 20:
            continue

        if len(title.split()) < 3:
            continue

        return {
            "title": title,
            "normalized_title": normalized,
            "start": match.start(),
            "matched_text": match.group(0).strip(),
        }

    return None


# ============================================================
# Получение текста заголовка из основного текста
# ============================================================

def get_heading_text_from_lines(lines, start_index):

    collected = []

    for index in range(
        start_index,
        min(start_index + 4, len(lines))
    ):

        line = lines[index].strip()

        if not line:
            break

        if index > start_index and re.match(
            r"^\d+(?:\.\d+)*\s*[.)]",
            line
        ):
            break

        collected.append(line)

    return " ".join(collected)


# ============================================================
# Сравнение заголовка главы 5
# ============================================================

def compare_chapter_titles(toc_title, body_title):

    normalized_toc = normalize_heading_text(
        toc_title
    )

    normalized_body = normalize_heading_text(
        body_title
    )

    if not normalized_toc or not normalized_body:
        return False, None

    # Полное совпадение или совпадение по началу.
    if normalized_body.startswith(normalized_toc):

        return True, "exact"

    if normalized_toc.startswith(normalized_body):

        return True, "exact"

    # Считаем длину общего начального фрагмента.
    common_length = 0

    for first, second in zip(
        normalized_toc,
        normalized_body
    ):

        if first != second:
            break

        common_length += 1

    shorter_length = min(
        len(normalized_toc),
        len(normalized_body)
    )

    # Принимаем сокращённое название только при достаточно
    # длинном общем начале. Это позволяет учитывать ситуацию,
    # когда в основном тексте продолжение заголовка отличается.
    if (
        common_length >= 30
        and common_length / shorter_length >= 0.35
    ):

        return True, "common_prefix"

    return False, None


# ============================================================
# Поиск настоящей главы 5
# ============================================================

def find_next_major_chapter(
    text,
    chapter_number,
    after_position
):

    if str(chapter_number) != "5":
        return None, []

    toc_heading = find_chapter_title_in_contents(
        text,
        after_position
    )

    if toc_heading is None:
        return None, []

    lines = text.splitlines()

    line_positions = []

    current_position = 0

    for line in lines:

        line_positions.append(current_position)

        current_position += len(line) + 1

    pattern = (
        r"^[ \t]*"
        r"5(?:\s*[.)])?\s+"
        r"(?=[А-ЯЁ])"
        r"[^\n]{3,300}"
    )

    candidates = []

    for line_index, line in enumerate(lines):

        line_start = line_positions[line_index]

        if line_start <= after_position:
            continue

        if not re.match(
            pattern,
            line,
            flags=re.IGNORECASE
        ):
            continue

        heading_text = get_heading_text_from_lines(
            lines,
            line_index
        )

        heading_without_number = re.sub(
            r"^\s*5(?:\s*[.)])?\s*",
            "",
            heading_text
        )

        is_match, match_type = compare_chapter_titles(
            toc_heading["title"],
            heading_without_number
        )

        if not is_match:
            continue

        candidates.append({
            "start": line_start,
            "matched_text": line.strip(),
            "toc_title": toc_heading["title"],
            "normalized_title": toc_heading["normalized_title"],
            "match_type": match_type,
        })

    if not candidates:
        return None, []

    candidates.sort(
        key=lambda item: item["start"]
    )

    return candidates[0], candidates


# ============================================================
# Выбор заголовков основного текста
# ============================================================

def select_headings(all_candidates):

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

    all_candidates = {}

    for section in SECTIONS:

        all_candidates[section["key"]] = (
            find_heading_candidates(text, section)
        )

    matched_headings = select_headings(
        all_candidates
    )

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
    # Граница главы 4.
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

    # --------------------------------------------------------
    # Необязательные разделы.
    # --------------------------------------------------------

    for optional_key in OPTIONAL_SECTION_KEYS:

        if optional_key not in extracted:

            extracted[optional_key] = {
                "start": None,
                "end": None,
                "text": "",
            }

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

        current_start = matched_headings[key]["start"]

        if current_start <= previous_start:

            warnings.append(
                f"Нарушен порядок заголовков: {key}"
            )

        previous_start = current_start

    return warnings


# ============================================================
# Контроль границы главы 3
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
# Контроль границы главы 4
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
            "Не найдено подтверждённое совпадение заголовка "
            "главы 5 с названием из оглавления. "
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

            if key in OPTIONAL_SECTION_KEYS:
                continue

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

    # --------------------------------------------------------
    # Проверка пустых разделов.
    # --------------------------------------------------------

    for key, section_data in extracted.items():

        if key in OPTIONAL_SECTION_KEYS:
            continue

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
    # Список отсутствующих необязательных разделов.
    # --------------------------------------------------------

    optional_sections_not_found = [
        key
        for key in OPTIONAL_SECTION_KEYS
        if key not in matched_headings
    ]

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
            "toc_title": chapter5_heading["toc_title"],
            "match_type": chapter5_heading["match_type"],
            "candidate_count": len(chapter5_candidates),
        }

    return {

        "quality_check": quality_check,

        "extraction_method": EXTRACTION_METHOD,

        "text_length": len(text),

        "missing_sections": missing_sections,

        "optional_sections_not_found": (
            optional_sections_not_found
        ),

        "optional_sections": {
            key: {
                "found": key in matched_headings,
                "empty": not bool(
                    extracted.get(key, {}).get("text", "").strip()
                ),
            }
            for key in OPTIONAL_SECTION_KEYS
        },

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
            "Для отдельных документов допускается альтернативная "
            "нумерация диагностических подразделов. "
            "Подраздел 2.5 «Иные диагностические исследования» "
            "считается необязательным. Если он отсутствует, "
            "в итоговом JSON сохраняется пустое значение. "
            "Граница главы 4 определяется сопоставлением "
            "названия главы 5 из оглавления с основным текстом. "
            "Медицинская полнота, сохранность текста и "
            "соответствие исходному PDF требуют отдельной проверки."
        ),
    }



DIAGNOSTIC_EXTRACTION_METHOD = "recommendation_blocks_v1"

def clean_diagnostic_value(value):
    value = re.sub(r"\s+", " ", value or "")
    return value.strip(" \t\r\n:;,.–—-")


def extract_diagnostic_recommendations(section_text, section_kind):
    if not isinstance(section_text, str) or not section_text.strip():
        return []

    bullet_re = re.compile(r"(?m)^[ \t]*[•●▪]\s*")
    bullets = list(bullet_re.finditer(section_text))
    results = []

    research_re = re.compile(
        r"(?i)(антител|иммуноглобулин|анализ|исследован|определени|"
        r"эндоскоп|биопси|ультразву|узи\b|рентген|томограф|денситометр|"
        r"генетическ|hла|hla|пцр|копролог|гормон|электрокарди|"
        r"эхокарди|спирометр|скопи|маммограф|функци|пункци|"
        r"морфологическ|консультац|направить)"
    )

    for index, match in enumerate(bullets):
        end = bullets[index + 1].start() if index + 1 < len(bullets) else len(section_text)
        block = section_text[match.end():end]
        block = re.sub(r"\s*\[Страница\s+\d+\]\s*", " ", block)
        block = clean_diagnostic_value(block)

        if not re.match(r"(?i)^(?:не\s+)?рекомендуется\b|^рекомендовано\b", block):
            continue

        if re.match(r"(?i)^не\s+рекомендуется\b", block):
            kind = "not_recommended"
            block = re.sub(r"(?i)^не\s+рекомендуется\s*", "", block)
        elif re.match(r"(?i)^рекомендуется\s+рассмотреть\b", block):
            kind = "consider"
            block = re.sub(r"(?i)^рекомендуется\s+рассмотреть\s*", "", block)
        else:
            kind = "recommended"
            block = re.sub(r"(?i)^(?:рекомендуется|рекомендовано)\s*", "", block)

        block = re.split(
            r"\bУровень\s+достоверности\s+доказательств\b|\bКомментарии?\s*:",
            block, maxsplit=1, flags=re.IGNORECASE
        )[0]
        block = clean_diagnostic_value(block)
        if len(block) < 20 or not research_re.search(block):
            continue
        if re.search(r"(?i)\bкритери\w*\b", block) and re.search(r"(?i)\bиспользовать\b", block):
            continue

        patient = re.search(
            r"\b(?:пациентам|пациентов|пациенту|пациента|детям|взрослым|лицам|родственникам)\b",
            block, flags=re.IGNORECASE
        )
        action = re.search(
            r"\b(?:выполнить|выполнение|провести|проведение|"
            r"определить|определение|исследовать|исследование|"
            r"измерить|измерение|оценить|оценка|направить)\b",
            block, flags=re.IGNORECASE
        )
        purpose_match = re.search(
            r"\bс\s+(?:(?:диагностической|лечебной|профилактической)\s+)?целью\b|"
            r"\bдля\s+[^.;]{0,70}\b(?:скрининга|диагностики|подтверждения|"
            r"исключения|верификации|оценки|выявления)\b",
            block, flags=re.IGNORECASE
        )

        # Название исследования может стоять как до указания пациентов,
        # так и после него ("пациентам ... выполнить исследование").
        if action and patient and action.start() > patient.start():
            name_start = action.start()
            name_end_match = re.search(
                r"\b(?:на\s+фоне|через\s+\d|в\s+динамике|"
                r"с\s+интервалом|при\s+появлении)\b",
                block[name_start + 1:],
                flags=re.IGNORECASE
            )
            name_end = (
                name_start + 1 + name_end_match.start()
                if name_end_match else len(block)
            )
            if purpose_match and purpose_match.start() > name_start:
                name_end = min(name_end, purpose_match.start())
            name = clean_diagnostic_value(block[name_start:name_end])
            indication_start = patient.start()
            indication_end = name_start
        else:
            if patient:
                name_end = patient.start()
            elif purpose_match:
                name_end = purpose_match.start()
            elif action:
                name_end = min(len(block), action.start() + 220)
            else:
                name_end = min(len(block), 220)

            name = clean_diagnostic_value(block[:name_end])
            indication_start = patient.start() if patient else None
            indication_end = (
                purpose_match.start()
                if purpose_match and purpose_match.start() > (indication_start or 0)
                else len(block)
            )

        name = re.sub(
            r"^(?:селективное|рутинное|повторное|выполнение|проведение|выполнить|провести|"
            r"исследовать|измерить|оценить)\s+",
            "", name, flags=re.IGNORECASE
        )
        name = clean_diagnostic_value(name)
        name = re.sub(r"(?i)^содержание\s+", "Определение содержания ", name)
        if name.count("(") > name.count(")"):
            name += ")" * (name.count("(") - name.count(")"))

        # Часто встречающиеся лабораторные и инструментальные методы
        # приводим к коротким и понятным названиям.
        lower_name = name.lower()

        if section_kind == "other_diagnostics":
            source_lower = block.lower()
            # Сам пункт о комплексном обследовании заменяется карточками
            # его вложенных компонентов, чтобы не создавать общую карточку-дубль.
            if re.search(r"(?i)комплексн\w*\s+лабораторно[- ]инструментальн\w*\s+исследован", source_lower):
                continue

            # Пропускаем все рекомендации с диагностическими методами,
            # а не только три заранее заданных названия.
            diagnostic_action = re.search(
                r"(?i)антител|иммуноглобулин|анализ|исследован|определени|"
                r"биопси|эндоскоп|гастроэнтеролог|консультац|обследован|"
                r"ультразву|узи\b|рентген|денситометр|генетическ|"
                r"hla[- ]?dq|гистологическ|патолого-анатомическ|"
                r"копролог|гормон|томограф|скрининг",
                source_lower
            )
            non_diagnostic_action = re.search(
                r"(?i)разрешить\s+.*диет|перевести\s+на\s+общий\s+стол|"
                r"продолжить\s+динамическое\s+наблюдение|"
                r"избегать\s+неоправданных\s+диетологических",
                source_lower
            )
            if not diagnostic_action or non_diagnostic_action:
                continue

            if "hla-dq2" in source_lower or "hla -dq2" in source_lower or "hla dq2" in source_lower:
                name = "Генетическое исследование HLA-DQ2/DQ8"
            elif "нагрузк" in source_lower and "глютен" in source_lower:
                name = "Глютеновая нагрузка (провокационный тест)"
            elif "гастроэнтеролог" in source_lower and (
                "направить" in source_lower or "консультац" in source_lower
            ):
                name = "Консультация врача-гастроэнтеролога"

        lower_name = name.lower()
        if "тканевой трансглютаминазе" in lower_name and "igg" in lower_name and "деамидированным пептидам" in lower_name:
            name = "Антитела к тканевой трансглютаминазе IgG и деамидированным пептидам глиадина IgG"
        elif ("тканевой трансглютаминазе" in lower_name or "тканевой транглютаминазе" in lower_name) and ("iga" in lower_name or "класса а" in lower_name):
            name = "Антитела к тканевой трансглютаминазе IgA (anti-tTG IgA)"
        elif "антител" in lower_name and "эндомизию" in lower_name:
            name = "Антитела к эндомизию IgA (EMA)"
        elif "антител" in lower_name and "нативному глиадину" in lower_name:
            name = "Антитела к нативному глиадину (AGA)"
        elif "эзофагогастродуоденоскопия" in lower_name:
            name = "ЭГДС с биопсией двенадцатиперстной кишки"
        elif "h la-dq2" in lower_name or "hla-dq2" in lower_name or "hla dq2" in lower_name:
            name = "Генетическое исследование HLA-DQ2/DQ8"

        if len(name) > 260:
            name = name[:257].rsplit(" ", 1)[0] + "…"
        if not name:
            continue

        indication = (
            clean_diagnostic_value(block[indication_start:indication_end])
            if indication_start is not None else ""
        )

        purpose = ""
        if purpose_match:
            purpose_start = purpose_match.start()
            purpose_end = len(block)
            if patient and patient.start() > purpose_start:
                purpose_end = patient.start()
            elif action and action.start() > purpose_start:
                purpose_end = action.start()
            purpose = clean_diagnostic_value(block[purpose_start:purpose_end])
        else:
            purpose_match_alt = re.search(
                r"\bдля\s+[^.;]{0,70}\b(?:скрининга|диагностики|подтверждения|"
                r"исключения|верификации|оценки|выявления)\b[^.;]{0,180}",
                block, flags=re.IGNORECASE
            )
            if purpose_match_alt:
                purpose = clean_diagnostic_value(purpose_match_alt.group(0))

        if "anti-ttg iga" in name.lower():
            indication = re.sub(
                r"\s+и\s+исследование\s+уровня\s+иммуноглобулина\s+а\b.*$",
                "", indication, flags=re.IGNORECASE
            )
        indication = re.sub(r"\s+дополнительное$", "", indication, flags=re.IGNORECASE)
        if not indication:
            indication = "В тексте рекомендации отдельные показания не выделены."

        if purpose and purpose.lower().startswith("с диагностической целью"):
            purpose = "Диагностика заболевания"
        elif purpose and purpose.lower().startswith("с целью "):
            purpose = purpose[8:]
        elif purpose and purpose.lower().startswith("для патолого"):
            purpose = "Морфологическое подтверждение диагноза"
        elif purpose and purpose.lower().startswith("для подтверждения диагноза"):
            purpose = "Подтверждение диагноза"
        elif purpose and purpose.lower().startswith("для установления диагноза"):
            purpose = "Установление диагноза"

        purpose = clean_diagnostic_value(purpose)
        if purpose.lower().startswith("скрининга"):
            purpose = "Скрининг" + purpose[len("скрининга"):]
        elif purpose.lower().startswith("исключения "):
            purpose = "Исключение " + purpose[len("исключения "):]
        elif purpose.lower().startswith("установления диагноза"):
            purpose = "Установление диагноза"
        if purpose:
            purpose = purpose[0].upper() + purpose[1:]
        else:
            purpose = "Отдельная цель исследования в формулировке рекомендации не указана."

        results.append({
            "name": name,
            "indications": indication,
            "purpose": purpose,
            "recommendation_type": kind,
            "source_excerpt": block[:1200],
            "source_section": section_kind,
        })

        # В одной рекомендации может быть сразу несколько исследований.
        # В целиакии отдельно указано первичное определение общего IgA.
        if (
            section_kind == "laboratory_diagnostics"
            and "anti-ttg iga" in name.lower()
            and re.search(r"(?i)и\s+исследование\s+уровня\s+иммуноглобулина\s+а\s+в\s+крови", block)
        ):
            results.append({
                "name": "Общий иммуноглобулин A (IgA)",
                "indications": indication,
                "purpose": "Исключение дефицита IgA, способного привести к ложноотрицательному результату серологического скрининга",
                "recommendation_type": kind,
                "source_excerpt": block[:1200],
                "source_section": section_kind,
            })

    # В разделе иных методов часть рекомендаций оформлена как
    # комплексное обследование с вложенным перечнем процедур. Эти строки
    # не начинаются словом «Рекомендуется», но являются частью рекомендации.
    if section_kind == "other_diagnostics":
        bullet_matches = list(bullet_re.finditer(section_text))
        for parent_index, parent_match in enumerate(bullet_matches):
            parent_end = (
                bullet_matches[parent_index + 1].start()
                if parent_index + 1 < len(bullet_matches)
                else len(section_text)
            )
            parent_text = clean_diagnostic_value(
                section_text[parent_match.end():parent_end]
            )
            if not (
                re.match(r"(?i)^рекомендуется\b|^рекомендовано\b", parent_text)
                and re.search(r"(?i)комплексн\w*\s+лабораторно[- ]инструментальн\w*\s+исследован", parent_text)
            ):
                continue

            indication_match = re.search(
                r"(?i)(пациентам\s+с\s+подтвержденным\s+диагнозом.*?обследования)",
                parent_text
            )
            inherited_indication = (
                clean_diagnostic_value(indication_match.group(1))
                if indication_match else
                "Пациентам с подтвержденным диагнозом целиакии при первичном обследовании."
            )

            for child_index in range(parent_index + 1, len(bullet_matches)):
                child_match = bullet_matches[child_index]
                child_text_end = (
                    bullet_matches[child_index + 1].start()
                    if child_index + 1 < len(bullet_matches)
                    else len(section_text)
                )
                child_text = clean_diagnostic_value(
                    section_text[child_match.end():child_text_end]
                )

                # Следующая самостоятельная рекомендация завершает список
                # компонентов комплексного обследования.
                if re.match(
                    r"(?i)^(?:не\s+)?рекомендуется\b|^рекомендовано\b|^рекомендовано\b",
                    child_text
                ):
                    break

                child_text = re.split(
                    r"\bУровень\s+достоверности\s+доказательств\b",
                    child_text, maxsplit=1, flags=re.IGNORECASE
                )[0]
                child_text = clean_diagnostic_value(child_text)
                if len(child_text) < 8:
                    continue

                low = child_text.lower()
                if "клинический осмотр" in low:
                    child_name = "Клинический осмотр и антропометрические измерения"
                elif "общий (клинический) анализ крови" in low:
                    child_name = "Общий (клинический) анализ крови развернутый"
                elif "анализ крови биохимический" in low:
                    child_name = "Биохимический анализ крови (общетерапевтический профиль)"
                elif "тиреоидного профиля" in low:
                    child_name = "Исследование гормонов и антител тиреоидного профиля"
                elif "копрологическое исследование" in low:
                    child_name = "Копрологическое исследование"
                elif "ультразвуковое исследование органов брюшной полости" in low:
                    child_name = "УЗИ органов брюшной полости (комплексное)"
                elif "ультразвуковое исследование щитовидной железы" in low:
                    child_name = "УЗИ щитовидной и паращитовидных желез"
                elif "ультразвуковое исследование матки и придатков" in low:
                    child_name = "УЗИ органов малого таза (девочкам старше 12 лет)"
                elif "рентгеноденситометрия" in low:
                    child_name = "Рентгеноденситометрия поясничного отдела позвоночника"
                elif "консультации специалистов" in low:
                    child_name = "Консультации профильных специалистов по показаниям"
                else:
                    # Не отбрасываем незнакомый вложенный пункт:
                    # сохраняем его исходную формулировку как название.
                    child_name = child_text.split(":", 1)[0].strip().rstrip(".")

                results.append({
                    "name": child_name,
                    "indications": inherited_indication,
                    "purpose": "Выявление дефицитных состояний и исключение часто ассоциированных аутоиммунных и эндокринных заболеваний.",
                    "recommendation_type": "recommended",
                    "source_excerpt": child_text[:1200],
                    "source_section": section_kind,
                })

    # Объединяем одинаковые исследования независимо от показаний.
    # Разные клинические ситуации сохраняются внутри одной карточки.
    grouped = {}
    order = []

    for item in results:
        key = re.sub(r"\s+", " ", item["name"].strip().lower())
        key = key.replace("ё", "е")

        if key not in grouped:
            grouped[key] = dict(item)
            grouped[key]["_indications"] = []
            grouped[key]["_purposes"] = []
            grouped[key]["_recommendation_types"] = []
            grouped[key]["_source_excerpts"] = []
            order.append(key)

        target = grouped[key]

        for value in (
            item.get("indications", ""),
            item.get("purpose", ""),
        ):
            if value and value not in (
                "В тексте рекомендации отдельные показания не выделены.",
                "Отдельная цель исследования в формулировке рекомендации не указана."
            ):
                bucket = "_indications" if value == item.get("indications") else "_purposes"
                if value not in target[bucket]:
                    target[bucket].append(value)

        recommendation_type = item.get("recommendation_type")
        if recommendation_type and recommendation_type not in target["_recommendation_types"]:
            target["_recommendation_types"].append(recommendation_type)

        excerpt = item.get("source_excerpt", "")
        if excerpt and excerpt not in target["_source_excerpts"]:
            target["_source_excerpts"].append(excerpt)

    unique = []
    for key in order:
        item = grouped[key]
        indications = item.pop("_indications")
        purposes = item.pop("_purposes")
        recommendation_types = item.pop("_recommendation_types")
        excerpts = item.pop("_source_excerpts")

        if item.get("source_section") == "other_diagnostics" and item.get("name") == "Глютеновая нагрузка (провокационный тест)":
            indications = [
                re.sub(r"\s*•?\s*пациентов излишнему дискомфорту.*$", "", value, flags=re.IGNORECASE).strip()
                for value in indications
            ]
            indications = [value for value in indications if value]
            purposes = [
                "Окончательная верификация диагноза целиакии"
                for value in purposes
                if "верификации диагноза" in value.lower()
            ] or purposes

        item["indications"] = (
            " • ".join(indications)
            if indications else "В тексте рекомендации отдельные показания не выделены."
        )
        item["purpose"] = (
            " • ".join(purposes)
            if purposes else "Отдельная цель исследования в формулировке рекомендации не указана."
        )

        if len(recommendation_types) == 1:
            item["recommendation_type"] = recommendation_types[0]
        elif "not_recommended" in recommendation_types:
            item["recommendation_type"] = "mixed"
        elif "consider" in recommendation_types:
            item["recommendation_type"] = "consider"
        else:
            item["recommendation_type"] = "recommended"

        item["source_excerpt"] = " || ".join(excerpts)[:4000]
        unique.append(item)

    return unique

def build_diagnostic_summary(extracted):
    laboratory = extract_diagnostic_recommendations(
        extracted.get("laboratory_diagnostics", {}).get("text", ""),
        "laboratory_diagnostics"
    )
    instrumental = extract_diagnostic_recommendations(
        extracted.get("instrumental_diagnostics", {}).get("text", ""),
        "instrumental_diagnostics"
    )
    other = extract_diagnostic_recommendations(
        extracted.get("other_diagnostics", {}).get("text", ""),
        "other_diagnostics"
    )
    return {
        "method": DIAGNOSTIC_EXTRACTION_METHOD,
        "status": "draft" if laboratory or instrumental or other else "not_extracted",
        "laboratory": laboratory,
        "instrumental": instrumental,
        "other": other,
        "counts": {
            "laboratory": len(laboratory),
            "instrumental": len(instrumental),
            "other": len(other)
        },
        "note": "Автоматически выделенные формулировки рекомендаций. Требуется сверка с исходным документом."
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
            section["key"]: extracted.get(
                section["key"],
                {"text": ""}
            )["text"]
            for section in SECTIONS
        },

        "diagnostic_summary": build_diagnostic_summary(extracted),

        "section_positions": {

            section["key"]: {
                "start": extracted.get(
                    section["key"],
                    {}
                ).get("start"),

                "end": extracted.get(
                    section["key"],
                    {}
                ).get("end"),

                "length": len(
                    extracted.get(
                        section["key"],
                        {"text": ""}
                    )["text"]
                ),
            }

            for section in SECTIONS
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
    # Вывод результатов.
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
                f"номер {heading['number']}, "
                f"позиция {heading['start']}"
            )

        elif key in OPTIONAL_SECTION_KEYS:

            print(
                f"[НЕТ — НЕОБЯЗАТЕЛЬНЫЙ] {key}"
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

        print(
            "Название из оглавления:",
            chapter5_heading["toc_title"]
        )

        print(
            "Тип совпадения:",
            chapter5_heading["match_type"]
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
