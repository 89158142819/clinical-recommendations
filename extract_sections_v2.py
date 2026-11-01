
import argparse
import json
import re
from pathlib import Path


# ============================================================
# Настройки проекта
# ============================================================

DEFAULT_INPUT = Path("output/749_2.json")

EXTRACTION_METHOD = "universal_structural_headings_v12"

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



DIAGNOSTIC_EXTRACTION_METHOD = "recommendation_blocks_v5"


def clean_diagnostic_block_text(value):
    # Убираем служебные метки страниц и номера страниц,
    # которые pypdf вставляет при переходе между страницами PDF.
    value = re.sub(
        r"(?m)^[ \t]*\d{1,3}[ \t]*\n(?:[ \t]*\n)*[ \t]*(?=\[Страница\s+\d+\])",
        "",
        value
    )
    value = re.sub(
        r"\[Страница\s+\d+\](?:[ \t]*\d{1,3}|[ \t]*\n[ \t]*\d{1,3})?",
        "",
        value,
        flags=re.IGNORECASE
    )
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def extract_diagnostic_recommendations(section_text, section_kind):
    """
    Извлекает рекомендации до маркера уровня убедительности.
    Переносы строк PDF не считаются границами блока. Если в одном
    фрагменте встречаются положительная и отрицательная рекомендации,
    они разделяются по началу предложений.
    """
    if not isinstance(section_text, str) or not section_text.strip():
        return []

    marker_re = re.compile(
        r"(?i)(?:"
        r"Уровень\s+убедительности\s+р[\s\-–—]*е[\s\-–—]*к[\s\-–—]*о[\s\-–—]*м[\s\-–—]*е[\s\-–—]*н[\s\-–—]*д[\s\-–—]*а[\s\-–—]*ц[\s\-–—]*и[\s\-–—]*[ий]"
        r"|УДД\s*\d+\s*[;,]?\s*УУР"
        r")\s*[:\-–—]?\s*[A-ZА-ЯЁ0-9]+(?:\s*\))?"
    )
    recommendation_re = re.compile(
        r"(?i)(?<![а-яё])(?:не\s+рекомендуется|не\s+рекомендовано|не\s+рекомендована|не\s+рекомендованы|рекомендуется|рекомендовано|рекомендована|рекомендованы)(?![а-яё])"
    )
    bullet_re = re.compile(r"^[ \t]*[•●▪]\s*", re.MULTILINE)
    bullet_marker_re = re.compile(r"[•●▪]\s*")

    # Убираем разрыв страницы до нормализации переносов строк.
    text = re.sub(
        r"[ \t]*\n*[ \t]*\[Страница\s+\d+\][ \t]*\n[ \t]*\d{1,3}[ \t]*\n?",
        " ",
        section_text,
        flags=re.IGNORECASE,
    )
    text = clean_diagnostic_block_text(text)
    text = re.sub(r"\s+", " ", text).strip()

    # Remove only the expected subsection heading at the start of a diagnostic section.
    section_heading_patterns = {
        "laboratory_diagnostics": (
            r"^\s*\d+(?:\.\d+)*\s+лабораторные\s+"
            r"диагностические\s+исследования\b[\s:—–-]*"
        ),
        "instrumental_diagnostics": (
            r"^\s*\d+(?:\.\d+)*\s+инструментальные\s+"
            r"диагностические\s+исследования\b[\s:—–-]*"
        ),
        "other_diagnostics": (
            r"^\s*\d+(?:\.\d+)*\s+иные\s+"
            r"диагностические\s+исследования\b[\s:—–-]*"
        ),
    }
    heading_pattern = section_heading_patterns.get(section_kind)
    if heading_pattern:
        text = re.sub(heading_pattern, "", text, count=1, flags=re.IGNORECASE).strip()

    def sentence_start(value, position):
        prefix = value[:position]
        boundaries = list(re.finditer(
            r"[.!?][\"»')\]]*\s+(?=[А-ЯЁA-Z0-9])",
            prefix
        ))
        return boundaries[-1].end() if boundaries else 0

    def recommendation_start(value, position):
        # Если рекомендация начинается с маркера списка, начинаем блок
        # именно с него, не захватывая комментарий после предыдущего уровня.
        bullets = list(bullet_marker_re.finditer(value, 0, position))
        if bullets:
            return bullets[-1].start()
        return sentence_start(value, position)

    def polarity(match):
        return "negative" if re.match(
            r"не\s+", match.group(0), re.IGNORECASE
        ) else "positive"

    results = []

    def append_block(block_text, level="", boundary_status="incomplete",
                     source_start=0, source_end=0):
        block_text = clean_diagnostic_block_text(block_text).strip()
        block_text = re.sub(r"^[ \t]*[•●▪]\s*", "", block_text)
        if not block_text:
            return
        results.append({
            "number": len(results) + 1,
            "text": block_text,
            "level": level,
            "boundary_status": boundary_status,
            "source_start": source_start,
            "source_end": source_end,
        })

    markers = list(marker_re.finditer(text))
    cursor = 0

    for marker in markers:
        segment = text[cursor:marker.start()]
        matches = list(recommendation_re.finditer(segment))

        if matches:
            clusters = []
            current_polarity = None
            for match in matches:
                current = polarity(match)
                if current != current_polarity:
                    position = recommendation_start(segment, match.start())
                    if not clusters or position > clusters[-1]["start"]:
                        clusters.append({"polarity": current, "start": position})
                    current_polarity = current

            for index, cluster in enumerate(clusters):
                block_start = cluster["start"]
                is_last = index == len(clusters) - 1
                block_end = len(segment) if is_last else clusters[index + 1]["start"]
                block_text = segment[block_start:block_end].strip()

                if is_last:
                    block_text = (block_text + " " + marker.group(0).strip()).strip()
                    status = "complete" if bullet_re.search(block_text) else "complete_without_bullet"
                    append_block(
                        block_text,
                        level=marker.group(0).strip(),
                        boundary_status=status,
                        source_start=cursor + block_start,
                        source_end=marker.end(),
                    )
                else:
                    append_block(
                        block_text,
                        boundary_status="incomplete",
                        source_start=cursor + block_start,
                        source_end=cursor + block_end,
                    )
        elif segment.strip():
            append_block(
                segment.strip() + " " + marker.group(0).strip(),
                level=marker.group(0).strip(),
                boundary_status="review_required",
                source_start=cursor,
                source_end=marker.end(),
            )

        cursor = marker.end()

    tail = text[cursor:]
    matches = list(recommendation_re.finditer(tail))
    if matches:
        starts = []
        current_polarity = None
        for match in matches:
            current = polarity(match)
            if current != current_polarity:
                position = recommendation_start(tail, match.start())
                if not starts or position > starts[-1]:
                    starts.append(position)
                current_polarity = current

        for index, block_start in enumerate(starts):
            block_end = starts[index + 1] if index + 1 < len(starts) else len(tail)
            append_block(
                tail[block_start:block_end],
                boundary_status="incomplete",
                source_start=cursor + block_start,
                source_end=cursor + block_end,
            )

    return results


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

    all_items = laboratory + instrumental + other
    has_review = any(
        item.get("boundary_status") in ("review_required", "incomplete")
        for item in all_items
    )

    return {
        "method": DIAGNOSTIC_EXTRACTION_METHOD,
        "status": (
            "review_required" if has_review
            else "extracted" if all_items
            else "not_extracted"
        ),
        "laboratory": laboratory,
        "instrumental": instrumental,
        "other": other,
        "counts": {
            "laboratory": len(laboratory),
            "instrumental": len(instrumental),
            "other": len(other)
        },
        "note": (
            "Сохранены полные блоки рекомендаций до строки уровня "
            "убедительности включительно. Комментарии после этой строки "
            "не включаются в блок; незавершённые границы требуют проверки."
        )
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
