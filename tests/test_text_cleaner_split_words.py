import json
from pathlib import Path

from text_cleaner import repair_split_words


CASES = [
    ("подозрение м на наличие", "подозрением на наличие"),
    ("ул ьтразвукового исследования", "ультразвукового исследования"),
    ("к омпьютерная томография", "компьютерная томография"),
    ("ко нтрастированием", "контрастированием"),
    ("п ациентам", "пациентам"),
    ("п о краю", "по краю"),
    ("в о время", "во время"),
    ("показани й к выполнению", "показаний к выполнению"),
    ("достаточно й для оценки", "достаточной для оценки"),
    ("полученно м в начале", "полученном в начале"),
]

UNCHANGED = [
    "в процессе лечения",
    "с пациентом",
    "по показаниям",
    "к врачу",
    "на основании данных",
]


def main():
    results = []

    for source, expected in CASES:
        actual = repair_split_words(source)
        results.append({
            "source": source,
            "expected": expected,
            "actual": actual,
            "passed": actual == expected,
        })

    for source in UNCHANGED:
        actual = repair_split_words(source)
        results.append({
            "source": source,
            "expected": source,
            "actual": actual,
            "passed": actual == source,
        })

    output = Path("output")
    output.mkdir(parents=True, exist_ok=True)
    (output / "text_cleaner_regression_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    failures = [item for item in results if not item["passed"]]
    for item in failures:
        print(
            f"ОШИБКА: {item['source']!r}; "
            f"ожидалось {item['expected']!r}; "
            f"получено {item['actual']!r}"
        )

    if failures:
        raise SystemExit(
            f"Тест очистки слов: ошибок {len(failures)} из {len(results)}"
        )

    print(
        f"Тест очистки слов пройден: {len(CASES)} исправлений, "
        f"{len(UNCHANGED)} обычных фраз сохранены без изменений."
    )


if __name__ == "__main__":
    main()
