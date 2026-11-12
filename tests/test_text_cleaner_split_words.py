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


def main():
    failures = []

    for source, expected in CASES:
        actual = repair_split_words(source)
        if actual != expected:
            failures.append((source, expected, actual))

    # Проверяем, что нормальные словосочетания не склеиваются.
    unchanged = [
        "в процессе лечения",
        "с пациентом",
        "по показаниям",
        "к врачу",
        "на основании данных",
    ]

    for source in unchanged:
        actual = repair_split_words(source)
        if actual != source:
            failures.append((source, source, actual))

    if failures:
        for source, expected, actual in failures:
            print(f"ОШИБКА: {source!r}")
            print(f"  Ожидалось: {expected!r}")
            print(f"  Получено:  {actual!r}")
        raise SystemExit(f"Тест очистки слов: ошибок {len(failures)}")

    print(f"Тест очистки слов пройден: {len(CASES)} исправлений, "
          f"{len(unchanged)} обычных фраз сохранены без изменений.")


if __name__ == "__main__":
    main()
