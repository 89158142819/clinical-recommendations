import json
import sys
from pathlib import Path

# При запуске файла напрямую Python добавляет в sys.path папку tests,
# а не корень репозитория. Добавляем корень проекта, чтобы импортировать
# text_cleaner.py из корневой папки.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

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
        try:
            actual = repair_split_words(source)
            error = None
        except Exception as exc:
            actual = None
            error = f"{type(exc).__name__}: {exc}"

        results.append({
            "source": source,
            "expected": expected,
            "actual": actual,
            "error": error,
            "passed": actual == expected and error is None,
        })

    for source in UNCHANGED:
        try:
            actual = repair_split_words(source)
            error = None
        except Exception as exc:
            actual = None
            error = f"{type(exc).__name__}: {exc}"

        results.append({
            "source": source,
            "expected": source,
            "actual": actual,
            "error": error,
            "passed": actual == source and error is None,
        })

    output = ROOT / "text_cleaner_regression_results.json"
    output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    failures = [item for item in results if not item["passed"]]
    for item in failures:
        print(
            f"ОШИБКА: {item['source']!r}; "
            f"ожидалось {item['expected']!r}; "
            f"получено {item['actual']!r}; "
            f"ошибка {item['error']!r}"
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
