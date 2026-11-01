import json
from pathlib import Path

SOURCE = Path("output/903_1_sections_v2.json")  # результат повторной обработки исходного PDF

if not SOURCE.exists():
    raise FileNotFoundError(f"Не найден результат обработки: {SOURCE}")

with SOURCE.open("r", encoding="utf-8") as f:
    data = json.load(f)

summary = data.get("diagnostic_summary", {})
counts = summary.get("counts", {})

print("=" * 80)
print("ТЕСТ НОВОГО ИЗВЛЕЧЕНИЯ: ОСТРЫЙ ПАНКРЕАТИТ (903_1)")
print("=" * 80)
print("Метод структуры:", data.get("extraction_method"))
print("Метод диагностики:", summary.get("method"))
print("Качество структуры:", data.get("quality_check"))
print("Статус диагностики:", summary.get("status"))
print("Количество блоков:", counts)

errors = []

expected = {"laboratory": 2, "instrumental": 10}
for group, expected_count in expected.items():
    items = summary.get(group, [])
    print("\n" + group.upper(), "-", len(items), "блоков")
    if len(items) != expected_count:
        errors.append(
            f"{group}: ожидалось {expected_count} блоков, получено {len(items)}"
        )

    for item in items:
        print("\n" + "-" * 60)
        print(
            f"Блок {item.get('number')} | "
            f"граница: {item.get('boundary_status')}"
        )
        print(item.get("text", ""))
        if item.get("boundary_status") != "complete":
            errors.append(
                f"{group}/{item.get('number')}: граница не подтверждена"
            )

if errors:
    print("\nОШИБКИ:")
    for error in errors:
        print("-", error)
    raise SystemExit(1)

print("\nПРОВЕРКА ПОЛНЫХ БЛОКОВ ПРОЙДЕНА")
