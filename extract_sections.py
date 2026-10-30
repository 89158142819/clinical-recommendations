import json
import re
from pathlib import Path


INPUT = Path("output/749_2.json")
OUTPUT = Path("output/749_2_sections.json")

# Минимальная длина разделов для контрольной проверки.
# Это ориентировочные значения для рекомендации
# «Грипп у взрослых», а не универсальные нормативы.
MIN_LENGTHS = {
    "definition": 100,
    "icd10": 100,
    "laboratory_diagnostics": 500,
    "instrumental_diagnostics": 300,
    "other_diagnostics": 100,
    "treatment": 1000,
    "treatment_conservative": 500,
    "treatment_surgical": 10
}


# Загружаем исходный документ
if not INPUT.exists():
    raise FileNotFoundError(
        f"Не найден исходный файл: {INPUT}"
    )

data = json.loads(INPUT.read_text(encoding="utf-8"))

text = re.sub(
    r"\s+",
    " ",
    data["full_text"]
)

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
    """Извлекает текст между двумя заголовками."""

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

    remainder = body[start.end():]

    end = re.search(
        end_pattern,
        remainder,
        re.IGNORECASE
    )

    if not end:
        return {
            "text": body[start.start():].strip(),
            "status": "end_heading_not_found"
        }

    section_text = body[
        start.start():start.end() + end.start()
    ]

    return {
        "text": section_text.strip(),
        "status": "extracted"
    }


# Заголовок главы 4
chapter4_pattern = (
    r"(?<!\d)4\.\s*Медицинская реабилитация"
)


# Извлекаем разделы
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
        r"3\.\s*Лечение(?:,|\s)"
    ),

    "treatment": extract(
        r"3\.\s*Лечение(?:,|\s)",
        chapter4_pattern
    ),

    "treatment_conservative": extract(
        r"3\.1\.?\s*Консервативное лечение",
        r"3\.2\.?\s*Хирургическое лечение"
    ),

    "treatment_surgical": extract(
        r"3\.2\.?\s*Хирургическое лечение",
        chapter4_pattern
    )
}


# Формируем итоговый результат
result = {
    "id": data["id"],
    "title": data["title"],
    "source_url": data["source_url"],
    "sections": sections
}


# --------------------------------------------------
# ПРОВЕРКА КАЧЕСТВА ИЗВЛЕЧЕНИЯ
# --------------------------------------------------

errors = []
warnings = []

for name, section in sections.items():

    section_text = section["text"]
    status = section["status"]

    # Проверяем наличие начального заголовка
    if status == "heading_not_found":
        errors.append(
            f"{name}: не найден начальный заголовок."
        )

    # Проверяем наличие конечного заголовка
    elif status == "end_heading_not_found":
        errors.append(
            f"{name}: не найден конечный заголовок."
        )

    # Проверяем минимальную длину
    if len(section_text) < MIN_LENGTHS[name]:
        warnings.append(
            f"{name}: подозрительно короткий раздел "
            f"({len(section_text)} символов)."
        )


# Дополнительные проверки структуры

if sections["other_diagnostics"]["text"]:
    if re.search(
        r"3\.\s*Лечение",
        sections["other_diagnostics"]["text"],
        re.IGNORECASE
    ):
        errors.append(
            "В раздел иной диагностики попал текст главы 3."
        )


if sections["treatment"]["text"]:

    treatment_text = sections["treatment"]["text"]

    if not re.search(
        r"3\.1\.?\s*Консервативное лечение",
        treatment_text,
        re.IGNORECASE
    ):
        warnings.append(
            "В разделе лечения не найден подраздел 3.1."
        )

    if not re.search(
        r"3\.2\.?\s*Хирургическое лечение",
        treatment_text,
        re.IGNORECASE
    ):
        warnings.append(
            "В разделе лечения не найден подраздел 3.2."
        )

    if not re.search(
        chapter4_pattern,
        body,
        re.IGNORECASE
    ):
        errors.append(
            "В исходном тексте не найден заголовок главы 4."
        )


if sections["treatment_surgical"]["text"]:

    if not re.search(
        r"3\.2\.?\s*Хирургическое лечение",
        sections["treatment_surgical"]["text"],
        re.IGNORECASE
    ):
        errors.append(
            "В хирургическом лечении отсутствует заголовок 3.2."
        )


# Сохраняем результат
OUTPUT.parent.mkdir(exist_ok=True)

OUTPUT.write_text(
    json.dumps(
        result,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)


# --------------------------------------------------
# ВЫВОД РЕЗУЛЬТАТОВ
# --------------------------------------------------

print("\nОБРАБОТКА ЗАВЕРШЕНА")
print("Результат:", OUTPUT)

print("\nПРОВЕРКА РАЗДЕЛОВ")

for name, section in sections.items():
    print(
        f"{name}: "
        f"статус={section['status']}; "
        f"символов={len(section['text'])}"
    )


print("\n" + "=" * 60)
print("РЕЗУЛЬТАТ КОНТРОЛЯ КАЧЕСТВА")

if not errors and not warnings:
    print("Критических ошибок и предупреждений не обнаружено.")

if errors:
    print("\nОШИБКИ:")
    for error in errors:
        print("-", error)

if warnings:
    print("\nПРЕДУПРЕЖДЕНИЯ:")
    for warning in warnings:
        print("-", warning)


# Сохраняем отдельный отчет о проверке
report = {
    "id": data["id"],
    "title": data["title"],
    "quality_check": (
        "errors_found" if errors
        else "warnings_found" if warnings
        else "passed"
    ),
    "errors": errors,
    "warnings": warnings
}

REPORT = Path("output/749_2_quality_report.json")

REPORT.write_text(
    json.dumps(
        report,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

print("\nОтчет о проверке:", REPORT)
