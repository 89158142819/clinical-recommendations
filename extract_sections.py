
import json
import re
from pathlib import Path

INPUT = Path("output/749_2.json")
OUTPUT = Path("output/749_2_sections.json")

data = json.loads(INPUT.read_text(encoding="utf-8"))
text = data["full_text"]

# Убираем переносы строк внутри заголовков,
# сохраняя границы страниц для дальнейшей проверки.
text = re.sub(r"\s+", " ", text)

# Ищем начало основного содержания, а не оглавление.
markers = list(re.finditer(
    r"1\.\s*Краткая информация по заболеванию",
    text,
    re.IGNORECASE
))

if not markers:
    raise RuntimeError(
        "Не найдено начало основного содержания документа."
    )

content_start = markers[-1].start()
body = text[content_start:]

def extract(start_pattern, end_pattern):
    start = re.search(start_pattern, body, re.IGNORECASE)

    if not start:
        return {
            "text": "",
            "status": "heading_not_found"
        }

    end = re.search(
        end_pattern,
        body[start.end():],
        re.IGNORECASE
    )

    if not end:
        section_text = body[start.start():]
    else:
        section_text = body[
            start.start():start.end() + end.start()
        ]

    return {
        "text": section_text.strip(),
        "status": "extracted"
    }

sections = {
    "definition": extract(
        r"1\.1\.?\s*Определение заболевания",
        r"1\.2\.?\s*Этиология"
    ),

    "icd10": extract(
        r"1\.4\.?\s*Особенности кодирования",
        r"1\.5\.?\s*Классификация"
    ),

    "laboratory_diagnostics": extract(
        r"2\.3\.?\s*Лабораторные диагностические исследования",
        r"2\.4\.?\s*Инструментальные диагностические исследования"
    ),

    "instrumental_diagnostics": extract(
        r"2\.4\.?\s*Инструментальные диагностические исследования",
        r"2\.5\.?\s*Иные диагностические исследования"
    ),

    "other_diagnostics": extract(
        r"2\.5\.?\s*Иные диагностические исследования",
        r"3\.1\.?\s*Консервативное лечение"
    ),

    "treatment_conservative": extract(
        r"3\.1\.?\s*Консервативное лечение",
        r"3\.2\.?\s*Хирургическое лечение"
    ),

    "treatment_surgical": extract(
        r"3\.2\.?\s*Хирургическое лечение",
        r"4\.\s"
    )
}

result = {
    "id": data["id"],
    "title": data["title"],
    "source_url": data["source_url"],
    "sections": sections
}

OUTPUT.parent.mkdir(exist_ok=True)

OUTPUT.write_text(
    json.dumps(result, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print("Обработка завершена.")
print("Результат:", OUTPUT)

for name, section in sections.items():
    print(
        name,
        "| статус:", section["status"],
        "| символов:", len(section["text"])
    )
