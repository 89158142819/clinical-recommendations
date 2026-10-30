import argparse
import json
import re
from pathlib import Path


# Ищем смысловые заголовки, но границы определяем по нумерации документа.
# Номера подразделов не зашиты: они определяются из самого PDF-текста.
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
    "treatment_conservative": ["Консервативное лечение"],
    "treatment_surgical": ["Хирургическое лечение"],
}

MAIN_SECTIONS = [
    "definition",
    "icd10",
    "laboratory_diagnostics",
    "instrumental_diagnostics",
    "other_diagnostics",
    "treatment",
]

# Заголовок с номером в начале строки: 1., 1.1, 2.3.1 и т. п.
NUMBERED_HEADING_RE = re.compile(
    r"(?m)^[ \t]*(?P<number>\d+(?:\.\d+)*)(?:[.)])?[ \t]+(?P<title>[^\n]{2,180})"
)


def normalize_spaces(value):
    return re.sub(r"\s+", " ", value or "").strip().casefold()


def phrase_pattern(phrase):
    return r"\s+".join(re.escape(part) for part in phrase.split())


def heading_depth(number):
    return number.count(".") + 1


def collect_numbered_headings(text):
    """Собирает нумерованные заголовки, расположенные в начале строки."""
    headings = []
    for match in NUMBERED_HEADING_RE.finditer(text):
        headings.append({
            "start": match.start(),
            "end": match.end(),
            "number": match.group("number").rstrip("."),
            "depth": heading_depth(match.group("number").rstrip(".")),
            "title": match.group("title").strip(),
        })
    return headings


def find_alias_candidates(text, aliases, key):
    """Ищет заголовок с номером. Совпадение должно начинаться после номера."""
    candidates = []
    for alias in aliases:
        pattern = re.compile(
            r"(?im)^[ \t]*(?P<number>\d+(?:\.\d+)*)(?:[.)])?[ \t]+"
            + phrase_pattern(alias)
        )
        for match in pattern.finditer(text):
            number = match.group("number").rstrip(".")
            # Поле лечения — только заголовок главы, не вложенный подраздел.
            if key == "treatment" and heading_depth(number) != 1:
                continue
            candidates.append({
                "start": match.start(),
                "number": number,
                "depth": heading_depth(number),
                "alias": alias,
            })

    # Убираем дубли одного заголовка, оставляя совпадение с наиболее длинным alias.
    unique = {}
    for item in candidates:
        marker = (item["start"], item["number"])
        if marker not in unique or len(item["alias"]) > len(unique[marker]["alias"]):
            unique[marker] = item
    return list(unique.values())


def find_section_start(text, headings, key, aliases):
    candidates = find_alias_candidates(text, aliases, key)
    if not candidates:
        return None

    # В документе заголовок может встретиться в оглавлении и в основном тексте.
    # Берём последнее совпадение, но только если оно является нумерованным заголовком.
    candidate = max(candidates, key=lambda item: item["start"])

    # Уточняем границу начала по списку реальных строковых заголовков.
    same_position = [h for h in headings if h["start"] == candidate["start"]]
    if same_position:
        candidate["depth"] = same_position[0]["depth"]
    return candidate


def find_section_end(headings, start_info, text_length):
    """Ищет следующий соседний подраздел или следующую главу."""
    start = start_info["start"]
    number = start_info["number"]
    depth = start_info["depth"]
    parent = number.rpartition(".")[0] if "." in number else ""
    try:
        current_index = int(number.rsplit(".", 1)[-1])
    except ValueError:
        current_index = None

    for heading in headings:
        if heading["start"] <= start:
            continue

        next_number = heading["number"]
        next_depth = heading["depth"]
        next_parent = next_number.rpartition(".")[0] if "." in next_number else ""

        # Вложенные подразделы остаются внутри текущего блока.
        if next_depth > depth:
            continue

        # Следующий соседний подраздел: 1.5 после 1.4; 2.3.2 после 2.3.1.
        if next_depth == depth and next_parent == parent:
            try:
                next_index = int(next_number.rsplit(".", 1)[-1])
            except ValueError:
                next_index = None
            if current_index is not None and next_index == current_index + 1:
                return heading["start"]
            continue

        # Следующая глава завершает текущий подраздел/главу.
        # Для 1.4 это, например, глава 2; для главы 3 — глава 4.
        if next_depth < depth and not number.startswith(next_number + "."):
            return heading["start"]
        if depth == 1 and next_depth == 1 and next_number != number:
            try:
                next_index = int(next_number)
            except ValueError:
                next_index = None
            if current_index is not None and next_index == current_index + 1:
                return heading["start"]

    return text_length


def extract_block(text, start_info, headings):
    if start_info is None:
        return {"text": "", "status": "not_found", "heading_number": None}

    end = find_section_end(headings, start_info, len(text))
    block = text[start_info["start"]:end].strip()
    status = "extracted" if len(block) >= 30 else "too_short"
    return {
        "text": block,
        "status": status,
        "heading_number": start_info["number"],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Извлечение подразделов клинической рекомендации по заголовкам и нумерации"
    )
    parser.add_argument("--input", default="output/749_2.json")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    source = Path(args.input)
    if not source.exists():
        raise FileNotFoundError(f"Не найден исходный файл: {source}")

    data = json.loads(source.read_text(encoding="utf-8"))
    text = data.get("full_text", "")
    if not text.strip():
        raise RuntimeError("В исходном JSON отсутствует full_text")

    headings = collect_numbered_headings(text)
    sections = {}
    warnings = []
    matched_headings = {}

    for key, aliases in HEADING_ALIASES.items():
        start_info = find_section_start(text, headings, key, aliases)
        if start_info is None:
            sections[key] = {
                "text": "", "status": "not_found", "heading_number": None
            }
            matched_headings[key] = None
            if key in MAIN_SECTIONS:
                warnings.append(f"Не найден заголовок раздела: {key}")
            continue

        sections[key] = extract_block(text, start_info, headings)
        matched_headings[key] = {
            "number": start_info["number"],
            "alias": start_info["alias"],
        }
        if sections[key]["status"] == "too_short":
            warnings.append(f"Подозрительно короткий раздел: {key}")

    # Проверка логики границ: основные поля не должны начинаться в обратном порядке.
    found_main = [
        (key, sections[key].get("heading_number"))
        for key in MAIN_SECTIONS
        if sections[key].get("heading_number") is not None
    ]
    positions = {}
    for key in MAIN_SECTIONS:
        if sections[key].get("heading_number") is not None:
            info = find_section_start(text, headings, key, HEADING_ALIASES[key])
            positions[key] = info["start"] if info else None

    ordered = [(key, positions[key]) for key in MAIN_SECTIONS if positions.get(key) is not None]
    for (key_a, pos_a), (key_b, pos_b) in zip(ordered, ordered[1:]):
        if pos_b <= pos_a:
            warnings.append(f"Нарушен порядок разделов: {key_a} / {key_b}")

    missing_main = [
        key for key in MAIN_SECTIONS
        if sections.get(key, {}).get("status") == "not_found"
    ]

    quality_report = {
        "id": data.get("id"),
        "title": data.get("title"),
        "quality_check": "review_required" if missing_main or warnings else "passed",
        "errors": [f"Не извлечён обязательный раздел: {key}" for key in missing_main],
        "warnings": warnings,
        "matched_headings": matched_headings,
        "numbered_headings_found": len(headings),
        "note": (
            "Границы определяются по следующему нумерованному заголовку того же или более высокого уровня. "
            "Статус passed не подтверждает медицинскую полноту и точность; требуется проверка текста и страниц."
        ),
    }

    result = {
        "id": data.get("id"),
        "title": data.get("title"),
        "source_url": data.get("source_url"),
        "pdf_url": data.get("pdf_url"),
        "pages_count": data.get("pages_count"),
        "extraction_method": "numbered_heading_boundaries_v2",
        "sections": sections,
        "quality_report": quality_report,
    }

    output = (
        Path(args.output) if args.output
        else Path("output") / f"{data.get('id', 'document')}_sections_v2.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    report_file = output.with_name(
        output.stem.replace("_sections_v2", "") + "_quality_report_v2.json"
    )
    report_file.write_text(
        json.dumps(quality_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("Извлечение завершено")
    print("Документ:", data.get("title"), f"({data.get('id')})")
    print("Файл разделов:", output)
    print("Отчёт качества:", report_file)
    print("Статус:", quality_report["quality_check"])
    for key in MAIN_SECTIONS:
        item = sections[key]
        print(
            f"{key}: {item['status']} | "
            f"заголовок {item.get('heading_number')} | {len(item['text'])} символов"
        )
    if warnings:
        print("Предупреждения:")
        for warning in warnings:
            print("-", warning)


if __name__ == "__main__":
    main()
