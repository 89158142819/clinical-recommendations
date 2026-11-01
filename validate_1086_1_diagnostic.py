import json
from pathlib import Path

path = Path("output/1086_1_sections_v2.json")
if not path.exists():
    raise SystemExit(f"Не найден результат обработки: {path}")

data = json.loads(path.read_text(encoding="utf-8"))
summary = data.get("diagnostic_summary") or {}
laboratory = summary.get("laboratory") or []
instrumental = summary.get("instrumental") or []

errors = []

if data.get("extraction_method") != "universal_structural_headings_v11":
    errors.append("Документ обработан не парсером universal_structural_headings_v11")

if not laboratory:
    errors.append("Не извлечена лабораторная рекомендация")
else:
    lab_text = "\n".join(x.get("text", "") for x in laboratory)
    for phrase in (
        "Всем пациентам при подготовке к хирургическому лечению",
        "стандартного комплекса лабораторных исследований",
        "при наличии клинических показаний",
    ):
        if phrase.lower() not in lab_text.lower():
            errors.append(f"В лабораторном блоке отсутствует важная часть: {phrase}")

all_instrumental = "\n".join(x.get("text", "") for x in instrumental)
required_phrases = (
    "в возрасте 4-6 недель",
    "В процессе консервативного лечения с использованием отводящих ортопедических устройств",
    "Всем детям с подозрением на врожденный вывих бедра",
    "3-4 месяцев и старше",
)
for phrase in required_phrases:
    if phrase.lower() not in all_instrumental.lower():
        errors.append(f"В инструментальной диагностике потеряно условие: {phrase}")

negative_blocks = [
    x for x in instrumental
    if "не рекомендуется" in x.get("text", "").lower()
]
if len(negative_blocks) != 1:
    errors.append(
        "Ожидался отдельный блок с отрицательной рекомендацией по КТ/МРТ; "
        f"получено {len(negative_blocks)}"
    )
else:
    negative_text = negative_blocks[0].get("text", "").lower()
    if "компьютерной томографии" not in negative_text or "магнитно" not in negative_text:
        errors.append("Отрицательный блок не содержит одновременно КТ и МРТ")
    if "уровень убедительности" not in negative_text:
        errors.append("В отрицательном блоке потерян уровень убедительности")

for group_name, group in (("laboratory", laboratory), ("instrumental", instrumental)):
    for item in group:
        block = item.get("text", "")
        if "[страница" in block.lower():
            errors.append(f"{group_name}: в блок попала служебная метка страницы")
        if "Уровень убедительности" in block and item.get("boundary_status") == "incomplete":
            errors.append(f"{group_name}: блок с маркером уровня помечен incomplete")

# Проверяем, что рекомендация по IHDI не склеена с отрицательной рекомендацией КТ/МРТ.
for item in negative_blocks:
    block = item.get("text", "").lower()
    if "оценка степени децентрации" in block or "классификации ihdi" in block:
        errors.append("Рекомендация по IHDI ошибочно объединена с отрицательной рекомендацией КТ/МРТ")

print("ЛАБОРАТОРНЫЕ БЛОКИ:", len(laboratory))
print("ИНСТРУМЕНТАЛЬНЫЕ БЛОКИ:", len(instrumental))
for item in instrumental:
    print(
        item.get("number"),
        item.get("boundary_status"),
        item.get("level"),
        item.get("text", "")[:260].replace("\\n", " "),
    )

if errors:
    print("\\nОШИБКИ ПРОВЕРКИ:")
    for error in errors:
        print("-", error)
    raise SystemExit(1)

print("\\nПРОВЕРКА 1086_1 ПРОЙДЕНА")
