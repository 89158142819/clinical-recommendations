
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


# Возможные названия разделов

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


# Нумерованные заголовки:
# 1. Название
# 1.1 Название
# 1.1.1. Название

NUMBERED_HEADING_RE = re.compile(
    r"^[ \t]*(?P<number>\d+(?:\.\d+)*(?:\.)?)[ \t]+"
    r"(?P<title>[^\n]{2,180})[ \t]*$"
)


# Признаки строк оглавления

TOC_LEADERS_RE = re.compile(
    r"(?:\.{3,}|…{2,}|·{3,}|_{3,})"
)


# ---------------------------------------------------------
# НОРМАЛИЗАЦИЯ
# ---------------------------------------------------------

def normalize_text(value):
    """Приводит текст к единому виду для сравнения."""

    value = value.lower().replace("ё", "е")
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def clean_heading_number(number):
    return number.rstrip(".")


def get_heading_depth(number):
    return len(clean_heading_number(number).split("."))


# ---------------------------------------------------------
# ОПРЕДЕЛЕНИЕ СТРУКТУРНЫХ ЗАГОЛОВКОВ
# ---------------------------------------------------------

def is_toc_line(title):
    """
    Исключает строки оглавления с точками-лидерами,
    многоточиями и другими разделителями.
    """

    if TOC_LEADERS_RE.search(title):
        return True

    return False


def is_structural_heading(title):
    """
    Проверяет, похожа ли строка на заголовок раздела.

    Исключаются пустые строки, строки оглавления
    и обычные пункты перечней, начинающиеся со строчной буквы.
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

    return True


def collect_numbered_headings(full_text):
    """
    Собирает нумерованные структурные заголовки
    и сохраняет их позиции в исходном тексте.
    """

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

            if is_structural_heading(title):

                headings.append({
                    "number": number,
                    "title": title,
                    "normalized_title": normalize_text(title),
                    "depth": get_heading_depth(number),
                    "start": offset,
                    "end": offset + len(line_without_newline),
                })

        offset += len(line)

    return headings


# ---------------------------------------------------------
# ПОИСК НУЖНЫХ ЗАГОЛОВКОВ
# ---------------------------------------------------------

def find_alias_candidates(headings, aliases):
    """Находит совпадения с названиями разделов."""

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
    Находит начало нужного раздела.

    Строки оглавления уже исключены на этапе сбора заголовков.
    Поэтому выбирается первое подходящее совпадение
    среди оставшихся структурных заголовков.
    """

    aliases = HEADING_ALIASES[field_name]

    candidates = find_alias_candidates(
        headings,
        aliases,
    )

    if not candidates:
        return None

    return candidates[0]


# ---------------------------------------------------------
# ОПРЕДЕЛЕНИЕ ГРАНИЦ РАЗДЕЛОВ
# ---------------------------------------------------------

def find_section_end(full_text, headings, current_heading):
    """
    Следующий заголовок того же или более высокого уровня
    завершает текущий раздел.

    Вложенные подразделы остаются внутри родительского раздела.

    Например:

    2.3 включает:
        2.3.1
        2.3.2
        2.3.3

    и заканчивается перед:
        2.4

    3.1 включает:
        3.1.1
        3.1.2

    и заканчивается перед:
        3.2

    3 включает всю главу и заканчивается перед:
        4
    """

    current_start = current_heading["start"]
    current_depth = current_heading["depth"]

    for heading in headings:

        if heading["start"] <= current_start:
            continue

        if heading["depth"] <= current_depth:
            return heading["start"]

    return len(full_text)


def extract_block(full_text, headings, field_name):
    """Извлекает полный текст выбранного раздела."""

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
    """
    Выявляет некоторые признаки возможного обрыва текста.

    Результат используется как предупреждение,
    а не как окончательная оценка полноты.
    """

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

    # Проверка относительной длины консервативного лечения

    conservative = sections.get(
        "treatment_conservative",
        {},
    )

    treatment = sections.get(
        "treatment",
        {},
    )

    if conservative.get("text") and treatment.get("text"):

        conservative_length = len(
            conservative["text"]
        )

        treatment_length = len(
            treatment["text"]
        )

        if (
            conservative_length < treatment_length * 0.25
            and "3.2" in treatment["text"]
        ):
            warnings.append(
                "Подраздел консервативного лечения выглядит "
                "необычно коротким относительно главы лечения."
            )

    if errors:
        quality_check = "failed"
    elif warnings:
        quality_check = "review_required"
    else:
        quality_check = "passed"

    return {
        "document_id": DOCUMENT_ID,
        "quality_check": quality_check,
        "errors": errors,
        "warnings": warnings,
        "matched_headings": matched_headings,
        "numbered_headings_found": len(headings),
        "note": (
            "Строки оглавления с точками-лидерами исключаются. "
            "Вложенные подразделы включаются в родительский раздел. "
            "Границы определяются по следующему структурному "
            "заголовку того же или более высокого уровня. "
            "Статус passed подтверждает техническое извлечение, "
            "но не подтверждает медицинскую полноту и точность. "
            "Необходима проверка текста и страниц оригинального документа."
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
    print(
        f"Количество символов: {len(full_text)}"
    )

    headings = collect_numbered_headings(full_text)

    print(
        "Найдено структурных нумерованных заголовков: "
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
