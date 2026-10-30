

import json
import re
from pathlib import Path

INPUT = Path("output/749_2.json")
OUTPUT = Path("output/749_2_sections.json")

data = json.loads(INPUT.read_text(encoding="utf-8"))
text = data["full_text"]

# Убираем лишние пробелы и переносы строк
text = re.sub(r"\s+", " ", text)

# Находим начало основного содержания
markers = list(re.finditer(
    r"1\.\s*Краткая информация по заболеванию",
    text,
    re.IGNORECASE
))

if not markers:
    raise RuntimeError(
        "Не найдено начало основного содержания документа."
    )

body = text[markers[-1].start():]


def extract(start_pattern, end_pattern):
    start = re.search(
        start_pattern,
        body,
        re.IGNORECASE
    )

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
    json.dumps(
        result,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)


print("Обработка завершена.")
print("Результат:", OUTPUT)

for name, section in sections.items():
    print("\n" + "=" * 60)
    print(name)
    print("Статус:", section["status"])
    print("Символов:", len(section["text"]))

    print("\nНАЧАЛО РАЗДЕЛА:")
    print(section["text"][:700])

    print("\nКОНЕЦ РАЗДЕЛА:")
    print(section["text"][-300:])
