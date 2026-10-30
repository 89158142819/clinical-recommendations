
import json
import re
from pathlib import Path


# ---------------------------------------------------------
# НАСТРОЙКИ
# ---------------------------------------------------------

DOCUMENT_ID = "749_2"

INPUT_FILE = Path(f"output/{DOCUMENT_ID}.json")
OUTPUT_FILE = Path(f"output/{DOCUMENT_ID}_sections_v2.json")
QUALITY_FILE = Path(f"output/{DOCUMENT_ID}_quality_report_v2.json")


HEADING_ALIASES = {
    "definition": [
        "определение заболевания или состояния",
        "определение заболевания",
        "определение состояния",
    ],
    "icd10": [
        "особенности кодирования заболевания или состояния",
        "кодирование заболевания или состояния",
        "кодирование заболевания",
    ],
    "laboratory_diagnostics": [
        "лабораторные диагностические исследования",
        "лабораторная диагностика",
    ],
    "instrumental_diagnostics": [
        "инструментальные диагностические исследования",
        "инструментальная диагностика",
    ],
    "other_diagnostics": [
        "иные диагностические исследования",
        "прочие диагностические исследования",
        "иные методы диагностики",
    ],
    "treatment": [
        "лечение, включая медикаментозную и немедикаментозную терапии",
        "лечение, включая медикаментозную и немедикаментозную терапию",
        "лечение",
    ],
    "treatment_conservative": [
        "консервативное лечение",
    ],
    "treatment_surgical": [
        "хирургическое лечение",
    ],
}


# Номер раздела в начале строки.
NUMBER_PREFIX_RE = re.compile(
    r"^[ \t]*(?P<number>\d+(?:\.\d+)*(?:\.)?)"
    r"(?:[ \t]+(?P<title>.*)|[ \t]*)$"
)

TOC_LEADERS_RE = re.compile(
    r"(?:\.{3,}|…{2,}|·{3,}|_{3,})"
)

PAGE_MARKER_RE = re.compile(
    r"^\s*\[Страница\s+\d+\]\s*$",
    re.IGNORECASE,
)

BULLET_RE = re.compile(
    r"^\s*(?:[-–—•●▪◦*]|\d+[.)])\s+"
)


# Частые начала обычных предложений,
# которые не должны становиться заголовками.

SENTENCE_STARTS = (
    "при ",
    "при этом",
    "при наличии",
    "при подозрении",
    "при отсутствии",
    "при развитии",
    "при возникновении",
    "в случае",
    "в случаях",
    "в зависимости",
    "в соответствии",
    "в результате",
    "на амбулаторном",
    "на стационарном",
    "на этапе",
    "для диагностики",
    "для выявления",
    "для оценки",
    "для определения",
    "после ",
    "если ",
    "когда ",
    "с целью",
    "с учетом",
    "с учётом",
    "согласно",
    "при необходимости",
    "пациентам",
    "пациенту",
    "больным",
    "всем пациентам",
    "рекомендуется",
    "следует",
    "необходимо",
    "проводится",
    "выполняется",
    "назначается",
    "осуществляется",
    "может быть",
)


# Ограничения на продолжение многострочного заголовка.

MAX_HEADING_LINES = 5
MAX_HEADING_LENGTH = 400
MAX_CONTINUATION_LINE_LENGTH = 160


# ---------------------------------------------------------
# НОРМАЛИЗАЦИЯ
# ---------------------------------------------------------

def normalize_text(value):
    value = value.lower().replace("ё", "е")
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def clean_heading_number(number):
    return number.rstrip(".")


def get_heading_depth(number):
    return len(clean_heading_number(number).split("."))


def get_number_parts(number):
    return [
        int(part)
        for part in clean_heading_number(number).split(".")
    ]


# ---------------------------------------------------------
# РАБОТА СО СТРОКАМИ
# ---------------------------------------------------------

def get_lines_with_offsets(full_text):
    result = []
    offset = 0

    for line in full_text.splitlines(keepends=True):
        content = line.rstrip("\r\n")

        result.append({
            "text": content,
            "start": offset,
            "end": offset + len(line),
        })

        offset += len(line)

    return result


def is_page_marker(line):
    return bool(PAGE_MARKER_RE.match(line.strip()))


def is_toc_line(title):
    return bool(TOC_LEADERS_RE.search(title))


def is_sentence_ending(text):
    return text.rstrip().endswith((".", "!", "?", ";"))


# ---------------------------------------------------------
# ПРОВЕРКА СТРУКТУРНОГО ЗАГОЛОВКА
# ---------------------------------------------------------

def is_structural_heading(number, title):
    title = title.strip()

    if not title:
        return False

    if is_toc_line(title):
        return False

    if len(title) > MAX_HEADING_LENGTH:
        return False

    first_letter = None

    for char in title:
        if char.isalpha():
            first_letter = char
            break

    if first_letter is None:
        return False

    if not first_letter.isupper():
        return False

    normalized = normalize_text(title)

    for phrase in SENTENCE_STARTS:
        if normalized.startswith(normalize_text(phrase)):
            return False

    # Структурный заголовок обычно не заканчивается
    # точкой, точкой с запятой или запятой.
    if title.endswith((".", ";", ",")):
        return False

    # Не принимаем длинные предложения за заголовки.
    if len(title) > 220 and re.search(
        r"\b(проводится|выполняется|назначается|рекомендуется)\b",
        normalized,
    ):
        return False

    return True


# ---------------------------------------------------------
# СБОР МНОГОСТРОЧНЫХ ЗАГОЛОВКОВ
# ---------------------------------------------------------

def collect_numbered_headings(full_text):

    lines = get_lines_with_offsets(full_text)

    headings = []
    rejected = []

    index = 0

    while index < len(lines):

        line = lines[index]
        raw = line["text"]

        if is_page_marker(raw):
            index += 1
            continue

        match = NUMBER_PREFIX_RE.match(raw)

        if not match:
            index += 1
            continue

        number = clean_heading_number(
            match.group("number")
        )

        title_parts = []

        first_title = (match.group("title") or "").strip()

        # Заголовок может быть перенесён:
        # номер на одной строке, название на следующей.
        if first_title:
            title_parts.append(first_title)

        last_line_index = index

        if not title_parts:
            next_index = index + 1

            while next_index < len(lines):
                next_line = lines[next_index]["text"].strip()

                if not next_line:
                    break

                if is_page_marker(next_line):
                    next_index += 1
                    continue

                if NUMBER_PREFIX_RE.match(next_line):
                    break

                if len(next_line) > MAX_CONTINUATION_LINE_LENGTH:
                    break

                if BULLET_RE.match(next_line):
                    break

                title_parts.append(next_line)
                last_line_index = next_index
                break

        # Собираем продолжение заголовка.
        # Продолжение не должно выглядеть как отдельный абзац.
        continuation_index = last_line_index + 1

        while (
            title_parts
            and continuation_index < len(lines)
            and len(title_parts) < MAX_HEADING_LINES
        ):

            next_raw = lines[continuation_index]["text"]
            next_line = next_raw.strip()

            if not next_line:
                break

            if is_page_marker(next_line):
                continuation_index += 1
                continue

            if NUMBER_PREFIX_RE.match(next_line):
                break

            if BULLET_RE.match(next_line):
                break

            if len(next_line) > MAX_CONTINUATION_LINE_LENGTH:
                break

            if is_sentence_ending(next_line):
                break

            if re.match(
                r"^(?:рисунок|таблица|примечание|источник)\b",
                next_line,
                re.IGNORECASE,
            ):
                break

            current_title = " ".join(title_parts)

            if len(current_title) + len(next_line) > MAX_HEADING_LENGTH:
                break

            title_parts.append(next_line)
            last_line_index = continuation_index
            continuation_index += 1

        title = " ".join(title_parts).strip()

        if is_structural_heading(number, title):

            headings.append({
                "number": number,
                "title": title,
                "normalized_title": normalize_text(title),
                "depth": get_heading_depth(number),
                "parts": get_number_parts(number),
                "start": line["start"],
                "end": lines[last_line_index]["end"],
                "line": index + 1,
            })

            index = last_line_index + 1

        else:

            if title:
                rejected.append({
                    "number": number,
                    "title": title[:250],
                    "line": index + 1,
                    "reason": "Не прошёл проверку структурного заголовка",
                })

            index += 1

    return headings, rejected


# ---------------------------------------------------------
# ПОИСК НУЖНЫХ ЗАГОЛОВКОВ
# ---------------------------------------------------------

def find_alias_candidates(headings, aliases):

    normalized_aliases = [
        normalize_text(alias)
        for alias in aliases
    ]

    candidates = []

    for heading in headings:

        title = heading["normalized_title"]

        for alias in normalized_aliases:

            if title == alias or title.startswith(alias + " "):
                candidates.append(heading)
                break

    return candidates


def find_section_start(headings, field_name):

    candidates = find_alias_candidates(
        headings,
        HEADING_ALIASES[field_name],
    )

    if not candidates:
        return None

    # Для основного раздела лечения выбираем
    # наиболее высокий уровень нумерации.
    # Это предотвращает выбор 3.1.1 вместо главы 3.
    if field_name == "treatment":
        candidates.sort(
            key=lambda item: (
                item["depth"],
                item["start"],
            )
        )
    else:
        candidates.sort(
            key=lambda item: item["start"]
        )

    return candidates[0]


# ---------------------------------------------------------
# ОПРЕДЕЛЕНИЕ ГРАНИЦ РАЗДЕЛА
# ---------------------------------------------------------

def is_next_section_heading(current_heading, candidate):

    current_depth = current_heading["depth"]
    candidate_depth = candidate["depth"]

    # Все вложенные подразделы остаются внутри.
    if candidate_depth > current_depth:
        return False

    # Следующий заголовок того же или более высокого уровня
    # завершает текущий раздел.
    return True


def find_section_boundary(full_text, headings, current_heading):

    current_start = current_heading["start"]

    for heading in headings:

        if heading["start"] <= current_start:
            continue

        if is_next_section_heading(
            current_heading,
            heading,
        ):
            return {
                "offset": heading["start"],
                "heading": heading,
            }

    return {
        "offset": len(full_text),
        "heading": None,
    }


# ---------------------------------------------------------
# ИЗВЛЕЧЕНИЕ ТЕКСТА
# ---------------------------------------------------------

def extract_block(full_text, headings, field_name):

    heading = find_section_start(
        headings,
        field_name,
    )

    if heading is None:
        return {
            "text": "",
            "status": "not_found",
            "heading_number": None,
            "boundary_heading": None,
            "boundary_offset": None,
        }

    boundary = find_section_boundary(
        full_text,
        headings,
        heading,
    )

    start = heading["start"]
    end = boundary["offset"]

    extracted_text = full_text[start:end].strip()

    next_heading = boundary["heading"]

    return {
        "text": extracted_text,
        "status": "extracted" if extracted_text else "empty",
        "heading_number": heading["number"],
        "boundary_heading": (
            {
                "number": next_heading["number"],
                "title": next_heading["title"],
            }
            if next_heading else None
        ),
        "boundary_offset": end,
    }


# ---------------------------------------------------------
# ПРОВЕРКА ОКОНЧАНИЯ ТЕКСТА
# ---------------------------------------------------------

def check_suspicious_ending(text):

    if not text:
        return "Пустой текст раздела."

    ending = text.rstrip()
    warnings = []

    # Проверяем разные виды тире и дефиса.
    if ending.endswith(("-", "–", "—")):
        warnings.append(
            "Текст заканчивается дефисом или тире. "
            "Возможно, предложение или значение обрезано."
        )

    if ending.endswith(("(", "[", "{")):
        warnings.append(
            "Текст заканчивается открывающей скобкой."
        )

    if ending.endswith(":"):
        warnings.append(
            "Текст заканчивается двоеточием. "
            "Возможно, далее должно следовать продолжение."
        )

    if ending.endswith(","):
        warnings.append(
            "Текст заканчивается запятой."
        )

    # Последний непустой фрагмент.
    last_line = ending.splitlines()[-1].strip()

    # Не считаем маркер страницы признаком обрыва.
    if not is_page_marker(last_line):

        # Если конец выглядит как незавершённое предложение,
        # отправляем на ручную проверку.
        if (
            len(last_line) > 35
            and last_line[-1].isalnum()
            and not last_line.endswith("г.")
        ):
            warnings.append(
                "Последняя строка не имеет завершающего "
                "знака препинания. Проверьте оригинал."
            )

    return " ".join(warnings) if warnings else None


# ---------------------------------------------------------
# ПРОВЕРКА СТРУКТУРЫ РАЗДЕЛОВ
# ---------------------------------------------------------

def check_expected_depth(field_name, section):

    number = section.get("heading_number")

    if not number:
        return None

    depth = get_heading_depth(number)

    expected = {
        "definition": 2,
        "icd10": 2,
        "laboratory_diagnostics": 2,
        "instrumental_diagnostics": 2,
        "other_diagnostics": 2,
        "treatment": 1,
        "treatment_conservative": 2,
        "treatment_surgical": 2,
    }

    expected_depth = expected.get(field_name)

    if expected_depth is not None and depth != expected_depth:
        return (
            f"Для {field_name} найден заголовок {number} "
            f"уровня {depth}, ожидался уровень {expected_depth}."
        )

    return None


# ---------------------------------------------------------
# ОТЧЁТ КАЧЕСТВА
# ---------------------------------------------------------

def build_quality_report(sections, headings, rejected):

    errors = []
    warnings = []

    matched_headings = {}
    boundaries = {}

    for field_name, section in sections.items():

        matched_headings[field_name] = (
            section["heading_number"]
        )

        boundaries[field_name] = {
            "next_heading": section.get("boundary_heading"),
            "boundary_offset": section.get("boundary_offset"),
            "characters": len(section["text"]),
        }

        if section["status"] == "not_found":
            errors.append(
                f"Не найден заголовок раздела: {field_name}"
            )

        elif section["status"] == "empty":
            errors.append(
                f"Раздел найден, но текст пустой: {field_name}"
            )

        ending_warning = check_suspicious_ending(
            section["text"]
        )

        if ending_warning:
            warnings.append(
                f"{field_name}: {ending_warning}"
            )

        depth_warning = check_expected_depth(
            field_name,
            section,
        )

        if depth_warning:
            warnings.append(depth_warning)

    # Проверка соотношения консервативного лечения
    # и всей главы лечения.

    conservative = sections.get(
        "treatment_conservative",
        {},
    )

    treatment = sections.get(
        "treatment",
        {},
    )

    if conservative.get("text") and treatment.get("text"):

        if (
            len(conservative["text"]) <
            len(treatment["text"]) * 0.25
        ):
            warnings.append(
                "Подраздел консервативного лечения выглядит "
                "необычно коротким относительно главы лечения."
            )

    # Если хирургическое лечение заканчивается не главой 4,
    # проверяем его границу вручную.
    surgical = sections.get("treatment_surgical", {})
    surgical_boundary = surgical.get("boundary_heading")

    if surgical.get("text") and surgical_boundary is None:
        warnings.append(
            "Для хирургического лечения не найден следующий "
            "структурный заголовок. Проверьте конец раздела."
        )

    # Подозрительные нумерованные строки сохраняем
    # для диагностики, но сами по себе они не являются ошибкой.
    rejected_preview = rejected[:40]

    quality_check = "passed"

    if errors:
        quality_check = "failed"
    elif warnings:
        quality_check = "review_required"

    return {
        "document_id": DOCUMENT_ID,
        "quality_check": quality_check,
        "errors": errors,
        "warnings": warnings,
        "matched_headings": matched_headings,
        "boundaries": boundaries,
        "numbered_headings_found": len(headings),
        "rejected_numbered_candidates": rejected_preview,
        "rejected_candidates_count": len(rejected),
        "note": (
            "Парсер поддерживает многострочные заголовки. "
            "Вложенные подразделы включаются в родительский "
            "раздел. Проверяются границы, уровень нумерации "
            "и подозрительные окончания. Статус passed не "
            "подтверждает медицинскую полноту и точность. "
            "Необходима сверка текста и страниц оригинала."
        ),
    }


# ---------------------------------------------------------
# ОСНОВНАЯ ФУНКЦИЯ
# ---------------------------------------------------------

def main():

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Не найден исходный файл: {INPUT_FILE}"
        )

    with INPUT_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        source_data = json.load(file)

    full_text = source_data.get("full_text", "")

    if not full_text:
        raise ValueError(
            "В исходном JSON отсутствует поле full_text "
            "или оно пустое."
        )

    print("Исходный текст загружен.")
    print(f"Количество символов: {len(full_text)}")

    headings, rejected = collect_numbered_headings(
        full_text
    )

    print(
        "Найдено структурных заголовков: "
        f"{len(headings)}"
    )

    print(
        "Отклонено нумерованных кандидатов: "
        f"{len(rejected)}"
    )

    sections = {}

    for field_name in HEADING_ALIASES:

        sections[field_name] = extract_block(
            full_text,
            headings,
            field_name,
        )

        section = sections[field_name]

        print(
            f"{field_name}: "
            f"{section['status']}, "
            f"заголовок {section['heading_number']}, "
            f"символов {len(section['text'])}"
        )

        if section.get("boundary_heading"):
            print(
                "  Следующая граница: "
                f"{section['boundary_heading']['number']} "
                f"{section['boundary_heading']['title']}"
            )
        else:
            print("  Следующая граница: не найдена")

    result = {
        "document_id": DOCUMENT_ID,
        "title": source_data.get(
            "title",
            "Без названия",
        ),
        "source": source_data.get("source"),
        **sections,
    }

    quality_report = build_quality_report(
        sections,
        headings,
        rejected,
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2,
        )

    with QUALITY_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            quality_report,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("\nИзвлечение завершено.")
    print(f"Результат: {OUTPUT_FILE}")
    print(f"Отчёт качества: {QUALITY_FILE}")

    print(
        "Статус проверки: "
        f"{quality_report['quality_check']}"
    )

    if quality_report["errors"]:
        print("\nОшибки:")

        for error in quality_report["errors"]:
            print(f"- {error}")

    if quality_report["warnings"]:
        print("\nПредупреждения:")

        for warning in quality_report["warnings"]:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
