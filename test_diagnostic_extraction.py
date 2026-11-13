import json
import re
from pathlib import Path

from extract_sections_v2 import build_diagnostic_summary
from text_cleaner import clean_full_text


SOURCES = [
    "903_1",
    "520_2",
    "404_2",
    "1067_1",
    "507_4",
    "535_3",
    "762_2",
    "1086_1",
    "683_2",
]

OUTPUT = Path("diagnostic_regression_results.json")

LEVEL_MARKER_RE = re.compile(
    r"(?:Уровень\\s+у[\\s\\-–—]*б[\\s\\-–—]*е[\\s\\-–—]*д"
    r"[\\s\\-–—]*и[\\s\\-–—]*т[\\s\\-–—]*е[\\s\\-–—]*л"
    r"[\\s\\-–—]*ь[\\s\\-–—]*н[\\s\\-–—]*о[\\s\\-–—]*с"
    r"[\\s\\-–—]*т[\\s\\-–—]*и\\s+р[\\s\\-–—]*е"
    r"[\\s\\-–—]*к[\\s\\-–—]*о[\\s\\-–—]*м[\\s\\-–—]*е"
    r"[\\s\\-–—]*н[\\s\\-–—]*д[\\s\\-–—]*а[\\s\\-–—]*ц"
    r"[\\s\\-–—]*и[\\s\\-–—]*[ий]|УДД\\s*\\d+\\s*[;,]?\\s*УУР)",
    re.IGNORECASE,
)


def normalize_spaces(value):
    return re.sub(r"\\s+", " ", str(value or "")).strip()


def prepare_sections(sections):
    """Применяет текущую очистку PDF к сохранённым диагностическим разделам."""
    prepared = {}
    for key in (
        "laboratory_diagnostics",
        "instrumental_diagnostics",
        "other_diagnostics",
    ):
        prepared[key] = {
            "text": clean_full_text(str(sections.get(key, "") or ""))
        }
    return prepared


def fail(errors, message):
    errors.append(message)
    print("ОШИБКА:", message)


def check_level_markers(document_id, summary, errors):
    for group in ("laboratory", "instrumental", "other"):
        for item in summary[group]:
            if item.get("boundary_status") == "incomplete":
                continue
            if not LEVEL_MARKER_RE.search(item.get("text", "")):
                fail(
                    errors,
                    f"{document_id}/{group}/{item.get('number')}: "
                    "отсутствует маркер уровня убедительности",
                )


def check_520_2(summary, prepared, errors):
    items = summary["laboratory"]

    if len(items) != 5:
        fail(
            errors,
            f"520_2: ожидалось 5 лабораторных блоков, получено {len(items)}",
        )

    if any(x.get("boundary_status") == "incomplete" for x in items):
        fail(errors, "520_2: обнаружен незавершённый лабораторный блок")

    combined = normalize_spaces(
        " ".join(x.get("text", "") for x in items)
    ).lower()

    for phrase in (
        "каждые 3 месяца",
        "перед началом терапии бисфосфонатами",
        "перед каждым курсом терапии бисфосфонатами",
    ):
        if phrase not in combined:
            fail(errors, f"520_2: не найдено условие контроля: {phrase}")

    if "комментарий:" in combined or "комментарии:" in combined:
        fail(errors, "520_2: комментарий попал в текст рекомендации")

    cleaned_source = prepared["laboratory_diagnostics"]["text"].lower()
    if "терапиибисфосфонатами" in cleaned_source:
        fail(
            errors,
            "520_2: очистка не разделила склеенное слово "
            "«терапиибисфосфонатами»",
        )

    for joined, separated in (
        ("ионизированногокальцияв", "ионизированного кальция в"),
        ("костногоскелета", "костного скелета"),
    ):
        if joined in cleaned_source:
            fail(errors, f"520_2: осталось склеенное сочетание «{joined}»")
        # Второе выражение может находиться в другом диагностическом разделе,
        # поэтому здесь фиксируем наличие только если оно действительно в тексте.
        if joined == "костногоскелета" and separated in cleaned_source:
            print(f"ПРОВЕРЕНО: восстановлено «{separated}»")


def check_903_1(summary, errors):
    counts = summary["counts"]
    if counts["laboratory"] != 2:
        fail(errors, f"903_1: ожидалось 2 лабораторных блока, получено {counts['laboratory']}")
    if counts["instrumental"] != 10:
        fail(errors, f"903_1: ожидалось 10 инструментальных блоков, получено {counts['instrumental']}")

    all_text = normalize_spaces(
        " ".join(x.get("text", "") for x in summary["instrumental"])
    ).lower()

    for phrase in ("24 - 96 часов", "не позднее 12 часов", "7 - 10 дней"):
        if phrase not in all_text:
            fail(errors, f"903_1: потеряно условие инструментальной диагностики: {phrase}")

    if "комментарий." in all_text or "[страница" in all_text:
        fail(errors, "903_1: в инструментальный блок попал комментарий или метка страницы")


def check_1086_1(summary, errors):
    for group in ("laboratory", "instrumental"):
        for item in summary[group]:
            if re.match(
                r"^\\s*\\d+(?:\\.\\d+)*\\s+"
                r"(?:лабораторные|инструментальные)\\s+диагностические\\s+исследования",
                item.get("text", ""),
                re.IGNORECASE,
            ):
                fail(errors, f"1086_1/{group}: заголовок подраздела попал в рекомендацию")

    negative = [
        x.get("text", "")
        for x in summary["instrumental"]
        if re.search(r"не\\s+рекомендуется", x.get("text", ""), re.IGNORECASE)
    ]
    if not negative:
        fail(errors, "1086_1: не найдена отрицательная рекомендация КТ/МРТ")
    elif not any(
        "компьютерной томографии" in x.lower() and "магнитно" in x.lower()
        for x in negative
    ):
        fail(errors, "1086_1: отрицательная рекомендация не содержит КТ и МРТ")


def check_535_3(summary, errors):
    counts = summary["counts"]
    if not counts["laboratory"] or not counts["instrumental"]:
        fail(errors, "535_3: отсутствуют лабораторные или инструментальные рекомендации")
    for group in ("laboratory", "instrumental"):
        if len(summary[group]) < 2:
            fail(errors, f"535_3/{group}: блоки не разделены; найдено {len(summary[group])}")


def check_683_2(summary, errors):
    labs = summary["laboratory"]
    if len(labs) != 3:
        fail(errors, f"683_2: ожидалось 3 лабораторных блока, получено {len(labs)}")

    starts = (
        "рекомендуется клинико-лабораторное исследование",
        "рекомендуется определять содержание антистрептолизина",
        "рекомендуется бактериологическое исследование",
    )
    for index, expected in enumerate(starts):
        if index >= len(labs):
            break
        actual = re.sub(r"^\\s*[•●▪]\\s*", "", labs[index].get("text", "")).strip().lower()
        if not actual.startswith(expected):
            fail(errors, f"683_2: блок {index + 1} начинается неверно: {actual[:120]}")

    for index, level in enumerate(("5", "5", "4")):
        if index >= len(labs):
            break
        if not re.search(
            rf"уровень\\s+достоверности\\s+доказательств\\s*[-–—]\\s*{level}\\b",
            labs[index].get("text", ""),
            re.IGNORECASE,
        ):
            fail(errors, f"683_2: у блока {index + 1} не сохранён уровень {level}")

    for index, item in enumerate(labs):
        value = item.get("text", "").lower()
        if "комментарий:" in value or "комментарии:" in value:
            fail(errors, f"683_2: комментарий попал в лабораторный блок {index + 1}")

    instrumental = summary["instrumental"]
    if len(instrumental) != 1:
        fail(errors, f"683_2: ожидался 1 инструментальный блок, получено {len(instrumental)}")
    elif not instrumental[0].get("text", "").strip().lower().startswith(
        "рекомендуется инструментальное обследование"
    ):
        fail(errors, "683_2: инструментальный блок начинается не с рекомендации")
    elif "перед осмотром пациенту рекомендуется" in instrumental[0]["text"].lower():
        fail(errors, "683_2: подготовка пациента ошибочно включена в рекомендацию")


def main():
    results = []
    errors = []

    for document_id in SOURCES:
        source = Path("site-data/docs") / f"{document_id}.json"
        if not source.exists():
            fail(errors, f"{document_id}: отсутствует файл {source}")
            continue

        with source.open("r", encoding="utf-8") as file:
            document = json.load(file)

        prepared = prepare_sections(document.get("sections", {}))
        summary = build_diagnostic_summary(prepared)

        results.append({
            "id": document_id,
            "title": document.get("title"),
            "counts": summary["counts"],
            "diagnostic_summary": summary,
        })

        print("=" * 72)
        print(f"{document.get('title')} ({document_id})")
        print(
            f"Лабораторные: {summary['counts']['laboratory']} | "
            f"Инструментальные: {summary['counts']['instrumental']} | "
            f"Иные: {summary['counts']['other']}"
        )

        check_level_markers(document_id, summary, errors)

        if document_id == "520_2":
            check_520_2(summary, prepared, errors)
        elif document_id == "903_1":
            check_903_1(summary, errors)
        elif document_id == "1086_1":
            check_1086_1(summary, errors)
        elif document_id == "535_3":
            check_535_3(summary, errors)
        elif document_id == "683_2":
            check_683_2(summary, errors)

    OUTPUT.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("\\nРезультат сохранён в", OUTPUT)

    if errors:
        print("\\nОШИБКИ РЕГРЕССИОННОГО ТЕСТА:")
        for error in errors:
            print("-", error)
        raise SystemExit(f"ТЕСТ НЕ ПРОЙДЕН: {len(errors)} ошибок")

    print("\\nРЕГРЕССИОННЫЙ ТЕСТ ПРОЙДЕН")


if __name__ == "__main__":
    main()
