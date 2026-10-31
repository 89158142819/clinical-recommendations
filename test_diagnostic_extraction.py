import json
from pathlib import Path

from extract_sections_v2 import build_diagnostic_summary

SOURCE = Path("site-data/docs/404_2.json")
OUTPUT = Path("diagnostic_test_404_2.json")

with SOURCE.open("r", encoding="utf-8") as f:
    document = json.load(f)

sections = document.get("sections", {})
extracted = {
    "laboratory_diagnostics": {"text": sections.get("laboratory_diagnostics", "")},
    "instrumental_diagnostics": {"text": sections.get("instrumental_diagnostics", "")},
    "other_diagnostics": {"text": sections.get("other_diagnostics", "")},
}

summary = build_diagnostic_summary(extracted)
result = {
    "id": document.get("id"),
    "title": document.get("title"),
    "diagnostic_summary": summary,
}
OUTPUT.write_text(
    json.dumps(result, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print("=" * 65)
print("ТЕСТ СТРУКТУРИРОВАНИЯ ДИАГНОСТИКИ")
print("=" * 65)
print("Документ:", document.get("title"), document.get("id"))
print("Лабораторных пунктов:", summary["counts"]["laboratory"])
print("Инструментальных пунктов:", summary["counts"]["instrumental"])
print("Иных диагностических пунктов:", summary["counts"]["other"])
print("Статус:", summary["status"])
for group in ("laboratory", "instrumental", "other"):
    print("\n" + group.upper())
    for number, item in enumerate(summary[group], 1):
        print(f"{number}. {item['name']}")
        print("   Показания:", item["indications"])
        print("   Цель:", item["purpose"])
        print("   Тип:", item["recommendation_type"])
print("\nРезультат записан в", OUTPUT)
