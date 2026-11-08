from extract_sections_v2 import extract_sections, find_heading_candidates, SECTIONS


def run():
    source = """Диагностика заболевания или состояния
Жалобы и анамнез
Сведения о жалобах пациента и анамнезе.
Физикальное обследование
Объективные данные осмотра.
Лабораторные диагностические исследования
Рекомендуется выполнить общий анализ крови.
Инструментальные диагностические исследования
Рекомендуется проведение ЭКГ.
Иные диагностические исследования
Рекомендуется генетическое исследование.
Лечение
Основные подходы к терапии.
Реабилитация
Мероприятия по восстановлению.
"""

    extracted, matched, candidates, _, _ = extract_sections(source)

    expected = (
        "diagnostics",
        "complaints_anamnesis",
        "physical_examination",
        "laboratory_diagnostics",
        "instrumental_diagnostics",
        "other_diagnostics",
        "treatment",
        "rehabilitation",
    )

    missing = [key for key in expected if key not in matched]
    assert not missing, f"Не найдены смысловые заголовки: {missing}"

    for key in expected:
        assert matched[key].get("semantic") is True, (
            f"{key}: ожидался семантический заголовок без нумерации"
        )

    assert extracted["laboratory_diagnostics"]["text"].startswith(
        "Лабораторные диагностические исследования"
    )
    assert "Рекомендуется выполнить общий анализ крови" in (
        extracted["laboratory_diagnostics"]["text"]
    )
    assert "Инструментальные диагностические исследования" not in (
        extracted["laboratory_diagnostics"]["text"]
    )

    # Обычное предложение, начинающееся со слова «Диагностика»,
    # не должно считаться заголовком.
    sentence = "Диагностика заболевания проводится на основании жалоб пациента."
    diag_section = next(x for x in SECTIONS if x["key"] == "diagnostics")
    false_candidates = find_heading_candidates(sentence, diag_section)
    assert not false_candidates, false_candidates

    print("OK: найдены заголовки диагностики и подразделов без нумерации")
    print("OK: текст лабораторного подраздела ограничен следующим заголовком")
    print("OK: обычное предложение не принято за заголовок")


if __name__ == "__main__":
    run()
