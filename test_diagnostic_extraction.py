import json
from pathlib import Path

from extract_sections_v2 import build_diagnostic_summary

SOURCES = [
    "903_1",  # Острый панкреатит — эталон полного блока до уровня убедительности.
    "520_2",  # Незавершённый остеогенез — альтернативная запись уровня УДД/УУР.
    "404_2",
    "1067_1",
    "507_4",
    "535_3",
    "762_2",
    "1086_1",  # Врождённый вывих бедра — контроль границы PDF и КТ/МРТ.
]
OUTPUT = Path("diagnostic_regression_results.json")
LEVEL_MARKER_RE = __import__("re").compile(r"(?:Уровень\\s+убедительности\\s+рекомендаций|УДД\\s*\\d+\\s*[;,]?\\s*УУР)\\s*[:\\-–—]?\\s*[A-ZА-ЯЁ0-9]+", __import__("re").IGNORECASE)

results = []
errors = []

for document_id in SOURCES:
    source = Path("site-data/docs") / f"{document_id}.json"
    if not source.exists():
        errors.append(f"{document_id}: отсутствует тестовый файл {source}")
        continue

    with source.open("r", encoding="utf-8") as f:
        document = json.load(f)

    sections = document.get("sections", {})
    extracted = {
        "laboratory_diagnostics": {"text": sections.get("laboratory_diagnostics", "")},
        "instrumental_diagnostics": {"text": sections.get("instrumental_diagnostics", "")},
        "other_diagnostics": {"text": sections.get("other_diagnostics", "")},
    }

    summary = build_diagnostic_summary(extracted)
    counts = summary["counts"]

    results.append({
        "id": document_id,
        "title": document.get("title"),
        "counts": counts,
        "diagnostic_summary": summary,
    })

    print("=" * 75)
    print(f"{document.get('title')} ({document_id})")
    print(
        "Лабораторные:", counts["laboratory"],
        "| Инструментальные:", counts["instrumental"],
        "| Иные:", counts["other"],
    )

    for group in ("laboratory", "instrumental", "other"):
        print(f"\n{group.upper()}")
        for item in summary[group]:
            text = item.get("text", "")
            print(
                f"{item.get('number')}. "
                f"{item.get('boundary_status')} | "
                f"{len(text)} символов"
            )
            print(text[:500].replace("\n", " "))
            if item.get("boundary_status") != "incomplete":
                if not LEVEL_MARKER_RE.search(text):
                    errors.append(
                        f"{document_id}/{group}/{item.get('number')}: "
                        "в блоке отсутствует строка уровня убедительности"
                    )

    if document_id == "520_2":
        if counts["laboratory"] != 5:
            errors.append(
                f"520_2: ожидалось 5 лабораторных блоков с маркерами УДД/УУР, "
                f"получено {counts['laboratory']}"
            )
        lab_items = summary["laboratory"]
        if any(item.get("boundary_status") == "incomplete" for item in lab_items):
            errors.append("520_2: один или несколько лабораторных блоков остались незавершёнными")
        combined_lab = __import__("re").sub(
            r"\\s+",
            " ",
            " ".join(item.get("text", "") for item in lab_items)
        ).lower()
        for phrase in (
            "каждые 3 месяца",
            "перед началом терапии бисфосфонатами",
            "перед каждым курсом терапии бисфосфонатами",
        ):
            if phrase not in combined_lab:
                errors.append(f"520_2: потеряно условие лабораторного контроля: {phrase}")
        if "комментарий:" in combined_lab or "комментарии:" in combined_lab:
            errors.append("520_2: комментарии после маркера уровня попали в текст рекомендации")

    if document_id == "903_1":
        if counts["laboratory"] != 2:
            errors.append(
                f"903_1: ожидалось 2 лабораторных блока, получено {counts['laboratory']}"
            )
        if counts["instrumental"] != 10:
            errors.append(
                f"903_1: ожидалось 10 инструментальных блоков, получено {counts['instrumental']}"
            )
        all_text = "\\n".join(
            item["text"] for item in summary["instrumental"]
        ).lower()
        normalized_all_text = __import__("re").sub(r"\\s+", " ", all_text)
        for phrase in ("24 - 96 часов", "не позднее 12 часов", "7 - 10 дней"):
            if phrase.lower() not in normalized_all_text:
                errors.append(
                    f"903_1: потеряно важное условие инструментальной диагностики: {phrase}"
                )
        if "комментарий." in all_text:
            errors.append(
                "903_1: комментарий после уровня убедительности попал в блок рекомендации"
            )
        combined_text = "\n".join(
            item["text"]
            for group in ("laboratory", "instrumental")
            for item in summary[group]
        ).lower()
        if "[страница" in combined_text:
            errors.append("903_1: в блоки попали служебные метки страниц PDF")
        if __import__("re").search(r"(?m)^\s*\d{1,3}\s*$", combined_text):
            errors.append("903_1: в блоки попали отдельные номера страниц PDF")

    if document_id == "1086_1":
        for group in ("laboratory", "instrumental"):
            for item in summary[group]:
                if __import__("re").match(
                    r"^\s*\d+(?:\.\d+)*\s+(?:лабораторные|инструментальные)\s+диагностические\s+исследования",
                    item.get("text", ""),
                    __import__("re").IGNORECASE,
                ):
                    errors.append(
                        f"1086_1/{group}/{item.get('number')}: "
                        "заголовок подраздела попал в текст рекомендации"
                    )
        negative_blocks = [
            item.get("text", "")
            for item in summary["instrumental"]
            if __import__("re").search(
                r"не\s+рекомендуется",
                item.get("text", ""),
                __import__("re").IGNORECASE,
            )
        ]
        if not negative_blocks:
            errors.append("1086_1: не найдена отдельная отрицательная рекомендация КТ/МРТ")
        elif not any(
            "компьютерной томографии" in value.lower()
            and "магнитно" in value.lower()
            for value in negative_blocks
        ):
            errors.append("1086_1: отрицательный блок не содержит одновременно КТ и МРТ")

    if document_id == "535_3":
        if not all(counts[k] > 0 for k in ("laboratory", "instrumental")):
            errors.append("535_3: не извлечены лабораторные или инструментальные рекомендации")
        for group in ("laboratory", "instrumental"):
            if len(summary[group]) < 2:
                errors.append(
                    f"535_3/{group}: рекомендации не разделены на отдельные блоки; "
                    f"получено {len(summary[group])}"
                )

OUTPUT.write_text(
    json.dumps(results, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print("\nРезультат сохранён в", OUTPUT)
if errors:
    print("\nОШИБКИ РЕГРЕССИОННОГО ТЕСТА:")
    for error in errors:
        print("-", error)
    raise SystemExit(1)

print("\nРЕГРЕССИОННЫЙ ТЕСТ ПРОЙДЕН")
