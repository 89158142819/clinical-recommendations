
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


# Названия разделов и возможные варианты заголовков

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


# Структурный заголовок:
# 1. Название
# 1.1 Название
# 1.1.1. Название

NUMBERED_HEADING_RE = re.compile(
    r"^[ \t]*(?P<number>\d+(?:\.\d+)*(?:\.)?)[ \t]+"
    r"(?P<title>[^\n]{2,180})[ \t]*$"
)


# ---------------------------------------------------------
# НОРМАЛИЗАЦИЯ
# ---------------------------------------------------------

def normalize_text(value):
    """Нормализация текста для сравнения заголовков."""

    value = value.lower().replace("ё", "е")
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def clean_heading_number(number):
    """Убирает завершающую точку из номера."""

    return number.rstrip(".")


def get_heading_depth(number):
    """Определяет уровень заголовка по количеству частей номера."""

    return len(clean_heading_number(number).split("."))


# ---------------------------------------------------------
# ПОИСК СТРУКТУРНЫХ ЗАГОЛОВКОВ
# ---------------------------------------------------------

def is_structural_heading(title):
    """
    Отсекает большинство нумерованных пунктов внутри текста.

    Структурные заголовки обычно начинаются с заглавной буквы.
    Пункты перечней вида '1. на амбулаторном этапе...' 
    не считаются заголовками разделов.
    """

    title = title.strip()

    if not title:
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
    """Собирает структурные нумерованные заголовки."""

    headings = []
    offset = 0

    for line in full_text.splitlines(keepends=True):
        line_without_newline = line.rstrip("\r\n")

        match = NUMBERED_HEADING_RE.match(line_without_newline)

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
# ПОИСК НУЖНЫХ РАЗДЕЛОВ
# ---------------------------------------------------------

def find_alias_candidates(headings, aliases):
    """Находит заголовки, соответствующие вариантам названия."""

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
    """Находит начало нужного раздела."""

    aliases = HEADING_ALIASES[field_name]

    candidates = find_alias_candidates(
        headings,
        aliases,
    )

    if not candidates:
        return None

    # Берём первое подходящее совпадение.
    return candidates[0]


# ---------------------------------------------------------
# ОПРЕДЕЛЕНИЕ ГРАНИЦ РАЗДЕЛОВ
# ---------------------------------------------------------

def find_section_end(full_text, headings, current_heading):
    """
    Определяет конец раздела по иерархии заголовков.

    Следующий заголовок того же или более высокого уровня
    завершает текущий раздел.

    Вложенные подразделы остаются внутри родительского раздела.

    Примеры:

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

        # Следующий заголовок того же или более высокого уровня
        # завершает текущий раздел.
        if heading["depth"] <= current_depth:
            return heading["start"]

    return len(full_text)


def extract_block(full_text, headings, field_name):
    """Извлекает текст раздела."""

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
    Проверяет, не выглядит ли конец текста оборванным.

    Проверка формирует предупреждение для ручной оценки.
    Она не определяет медицинскую полноту автоматически.
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

    # Дополнительная проверка подраздела консервативного лечения.

    conservative = sections.get(
        "treatment_conservative",
        {},
    )

    treatment = sections.get(
        "treatment",
        {},
    )

    if conservative.get("text") and treatment.get("text"):

        conservative_text = conservative["text"]
        treatment_text = treatment["text"]

        if (
            len(conservative_text) < len(treatment_text) * 0.25
            and "3.2" in treatment_text
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
            "Границы разделов определяются по следующему "
            "структурному заголовку того же или более высокого "
            "уровня. Вложенные подразделы включаются в "
            "родительский раздел. Статус passed подтверждает "
            "техническое извлечение, но не подтверждает "
            "медицинскую полноту и точность. Требуется "
            "проверка текста и страниц оригинального документа."
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

    # Поля разделов сохраняются в корне JSON,
    # чтобы не менять прежний формат результата.

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
