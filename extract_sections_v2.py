
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


NUMBERED_HEADING_RE = re.compile(
    r"^[ \t]*(?P<number>\d+(?:\.\d+)*(?:\.)?)[ \t]+"
    r"(?P<title>[^\n]{2,180})[ \t]*$"
)

TOC_LEADERS_RE = re.compile(
    r"(?:\.{3,}|…{2,}|·{3,}|_{3,})"
)


# Фразы, с которых часто начинаются нумерованные пункты,
# а не структурные заголовки.

SENTENCE_STARTS = (
    "при ",
    "при этом",
    "при наличии",
    "при подозрении",
    "в случае",
    "в случаях",
    "в зависимости",
    "на амбулаторном",
    "на стационарном",
    "на этапе",
    "для диагностики",
    "для выявления",
    "после ",
    "если ",
    "когда ",
    "с целью",
    "с учетом",
    "с учётом",
)


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
# ПРОВЕРКА СТРОК НА ПРИЗНАКИ ОГЛАВЛЕНИЯ
# ---------------------------------------------------------

def is_toc_line(title):
    return bool(TOC_LEADERS_RE.search(title))


# ---------------------------------------------------------
# ПРОВЕРКА СТРУКТУРНЫХ ЗАГОЛОВКОВ
# ---------------------------------------------------------

def is_structural_heading(number, title):
    """
    Отделяет структурные заголовки от нумерованных пунктов текста.

    В частности, исключает пункты вида:
    3. При подозрении на заболевание...

    При этом сохраняет заголовки вида:
    2.4 Инструментальные диагностические исследования
    3.2 Хирургическое лечение
    """

    title = title.strip()

    if not title:
        return False

    if is_toc_line(title):
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

    # Проверка начала фразы для нумерованных пунктов.
    for phrase in SENTENCE_STARTS:
        if normalized.startswith(normalize_text(phrase)):
            return False

    # Заголовок не должен выглядеть как законченное предложение.
    if title.endswith((".", ";", ",")):
        return False

    return True


def collect_numbered_headings(full_text):
    """Собирает структурные нумерованные заголовки."""

    headings = []
    offset = 0

    for line in full_text.splitlines(keepends=True):

        line_without_newline = line.rstrip("\r\n")

        match = NUMBERED_HEADING_RE.match(
            line_without_newline
        )

        if match:

            number = clean_heading_number(
                match.group("number")
            )

            title = match.group("title").strip()

            if is_structural_heading(number, title):

                headings.append({
                    "number": number,
                    "title": title,
                    "normalized_title": normalize_text(title),
                    "depth": get_heading_depth(number),
                    "parts": get_number_parts(number),
                    "start": offset,
                    "end": offset + len(line_without_newline),
                })

        offset += len(line)

    return headings


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
    """
    Находит начало раздела.

    Оглавление предварительно исключается при сборе заголовков.
    """

    candidates = find_alias_candidates(
        headings,
        HEADING_ALIASES[field_name],
    )

    if not candidates:
        return None

    return candidates[0]


# ---------------------------------------------------------
# ПРОВЕРКА ГРАНИЦ РАЗДЕЛА
# ---------------------------------------------------------

def is_next_section_heading(current_heading, candidate):
    """
    Проверяет, может ли следующий заголовок завершать раздел.

    Для раздела 2.3:
    - 2.3.1 и 2.3.2 остаются внутри;
    - 2.4 завершает раздел;
    - нумерованный пункт 3. При подозрении... не считается
      структурным заголовком благодаря предыдущей проверке.

    Для раздела 3.1:
    - 3.1.1 и 3.1.2 остаются внутри;
    - 3.2 завершает раздел.

    Для главы 3:
    - вложенные подразделы остаются внутри;
    - следующая глава 4 завершает раздел.
    """

    current_depth = current_heading["depth"]
    candidate_depth = candidate["depth"]

    if candidate_depth > current_depth:
        return False

    current_parts = current_heading["parts"]
    candidate_parts = candidate["parts"]

    # Следующий заголовок того же уровня.
    if candidate_depth == current_depth:

        # Например, 2.3 -> 2.4 или 3.1 -> 3.2.
        if current_parts[:-1] == candidate_parts[:-1]:
            return True

        # Заголовок другого раздела того же уровня.
        # Например, 2.5 -> 3.1.
        return True

    # Заголовок более высокого уровня.
    # Например, 3.1 -> 4 или 2.3 -> 3.
    return True


def find_section_end(full_text, headings, current_heading):

    current_start = current_heading["start"]

    for heading in headings:

        if heading["start"] <= current_start:
            continue

        if is_next_section_heading(
            current_heading,
            heading,
        ):
            return heading["start"]

    return len(full_text)


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
        }

    start = heading["start"]

    end = find_section_end(
        full_text,
        headings,
        heading,
    )

    extracted_text = full_text[start:end].strip()

    return {
        "text": extracted_text,
        "status": "extracted" if extracted_text else "empty",
        "heading_number": heading["number"],
    }


# ---------------------------------------------------------
# ПРОВЕРКА ОКОНЧАНИЯ ТЕКСТА
# ---------------------------------------------------------

def check_suspicious_ending(text):

    if not text:
        return "Пустой текст раздела."

    ending = text.rstrip()
    warnings = []

    if ending.endswith(":"):
        warnings.append(
            "Текст заканчивается двоеточием."
        )

    if ending.endswith("(") or ending.endswith("["):
        warnings.append(
            "Текст заканчивается открывающей скобкой."
        )

    if ending.endswith("-"):
        warnings.append(
            "Текст заканчивается дефисом."
        )

    if warnings:
        return " ".join(warnings)

    return None


# ---------------------------------------------------------
# ОТЧЁТ КАЧЕСТВА
# ---------------------------------------------------------

def build_quality_report(sections, headings):

    errors = []
    warnings = []

    matched_headings = {}

    for field_name, section in sections.items():

        matched_headings[field_name] = (
            section["heading_number"]
        )

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

    # Проверка консервативного лечения.

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
        "numbered_headings_found": len(headings),
        "note": (
            "При определении границ учитывается уровень "
            "нумерации и структура заголовков. Нумерованные "
            "пункты текста с признаками обычного предложения "
            "исключаются. Вложенные подразделы включаются "
            "в родительский раздел. Статус passed не подтверждает "
            "медицинскую полноту и точность. Необходима проверка "
            "текста и страниц оригинального документа."
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

    headings = collect_numbered_headings(full_text)

    print(
        "Найдено структурных заголовков: "
        f"{len(headings)}"
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

    # Сохраняем прежнюю структуру JSON:
    # поля разделов находятся в корне.

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
