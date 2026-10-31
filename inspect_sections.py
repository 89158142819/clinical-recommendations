
import json
import sys
from pathlib import Path

FILE = Path("output/1090_1_sections_v2.json")
REPORT_LIMIT = 300

if not FILE.exists():
    print(f"ОШИБКА: файл не найден: {FILE}")
    sys.exit(1)

with FILE.open("r", encoding="utf-8") as f:
    data = json.load(f)

print("=" * 70)
print("ДИАГНОСТИКА ИЗВЛЕЧЁННЫХ РАЗДЕЛОВ 1090_1")
print("=" * 70)

print("Тип корневого объекта:", type(data).__name__)

if isinstance(data, dict):
    print("Ключи JSON:", list(data.keys()))

    sections = data.get("sections", data)

elif isinstance(data, list):
    sections = data

else:
    print("ОШИБКА: неизвестная структура JSON")
    sys.exit(1)

if not isinstance(sections, (dict, list)):
    print("ОШИБКА: разделы имеют неожиданный формат")
    sys.exit(1)

if isinstance(sections, dict):
    items = list(sections.items())
else:
    items = [
        (str(i), section)
        for i, section in enumerate(sections)
    ]

print("\nКоличество объектов:", len(items))

empty_sections = []
short_sections = []

for name, section in items:
    if isinstance(section, dict):
        title = section.get("title", name)
        content = (
            section.get("text")
            or section.get("content")
            or section.get("full_text")
            or ""
        )
    elif isinstance(section, str):
        title = name
        content = section
    else:
        title = name
        content = ""

    content = str(content).strip()

    if not content:
        empty_sections.append(name)

    if 0 < len(content) < 100:
        short_sections.append(name)

    print("\n" + "-" * 70)
    print(f"РАЗДЕЛ: {name}")
    print(f"ЗАГОЛОВОК: {title}")
    print(f"ДЛИНА: {len(content)} символов")

    print("\nНАЧАЛО:")
    print(content[:REPORT_LIMIT] or "[ПУСТО]")

    print("\nКОНЕЦ:")
    print(content[-REPORT_LIMIT:] or "[ПУСТО]")

print("\n" + "=" * 70)
print("ИТОГ ДИАГНОСТИКИ")
print("=" * 70)

print("Всего объектов:", len(items))
print("Пустые разделы:", empty_sections)
print("Очень короткие разделы:", short_sections)

if empty_sections:
    print("СТАТУС: REVIEW_REQUIRED")
else:
    print("СТАТУС: базовая проверка содержимого пройдена")
