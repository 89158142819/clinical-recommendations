import json
from pathlib import Path

from extract_sections_v2 import build_diagnostic_summary

# Несколько разных КР для проверки вариантов оформления рекомендаций:
# 404_2 — целиакия, вложенные пункты и провокационная нагрузка;
# 1067_1 — короткий раздел и отсутствие показаний к части исследований;
# 507_4 — туберкулёз у детей, сложные рекомендации и иммунодиагностика;
# 535_3 — рак носоглотки, рекомендации в маркированных блоках;
# 762_2 — трансплантация сердца, длинные блоки «Рекомендовано».
SOURCES = [
    "404_2",
    "1067_1",
    "507_4",
    "535_3",
    "762_2",
]
OUTPUT = Path("diagnostic_regression_results.json")

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
        print(f"\\n{group.upper()}")
        for number, item in enumerate(summary[group], 1):
            print(f"{number}. {item['name']}")
            print("   Показания:", item["indications"])
            print("   Цель:", item["purpose"])
            print("   Тип:", item["recommendation_type"])

    # Проверяем, что парсер действительно извлекает ожидаемые разделы
    # на нескольких документах, а не только на целиакии.
    if document_id == "404_2" and not all(counts[k] > 0 for k in ("laboratory", "instrumental", "other")):
        errors.append("404_2: один из трёх диагностических подразделов пуст")
    if document_id == "507_4" and not all(counts[k] > 0 for k in ("laboratory", "instrumental", "other")):
        errors.append("507_4: не извлечены пункты из одного из трёх подразделов")
    if document_id == "535_3" and not all(counts[k] > 0 for k in ("laboratory", "instrumental")):
        errors.append("535_3: не извлечены лабораторные или инструментальные исследования")
    if document_id == "762_2" and not all(counts[k] > 0 for k in ("laboratory", "instrumental", "other")):
        errors.append("762_2: не извлечены пункты из одного из трёх подразделов")

OUTPUT.write_text(
    json.dumps(results, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print("\\nРезультат сохранён в", OUTPUT)
if errors:
    print("\\nОШИБКИ РЕГРЕССИОННОГО ТЕСТА:")
    for error in errors:
        print("-", error)
    raise SystemExit(1)

print("\\nРЕГРЕССИОННЫЙ ТЕСТ ПРОЙДЕН")
