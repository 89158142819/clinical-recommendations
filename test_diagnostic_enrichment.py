from diagnostic_enrichment import enrich_diagnostic_summary


def item(text, level="Уровень убедительности рекомендаций С (уровень достоверности доказательств – 5)"):
    return {
        "number": 1,
        "text": text + " " + level,
        "level": level,
        "boundary_status": "complete",
        "source_start": 0,
        "source_end": len(text),
    }


def run():
    mixed = item(
        "Рекомендуется выполнение ультразвукового исследования органов брюшной полости; "
        "не рекомендуется рутинное выполнение компьютерной томографии."
    )
    summary = enrich_diagnostic_summary({
        "method": "recommendation_blocks_v6",
        "status": "extracted",
        "laboratory": [],
        "instrumental": [mixed],
        "other": [],
        "counts": {"laboratory": 0, "instrumental": 1, "other": 0},
    })

    records = summary["instrumental"]
    assert len(records) == 2, records
    assert {x["verdict"] for x in records} == {"recommended", "not_recommended"}
    assert all("Уровень убедительности" in x["text"] for x in records)
    assert all(x["level"].startswith("Уровень убедительности") for x in records)
    assert all(x["source_text"].endswith("5)") for x in records)
    assert any("ультразвукового исследования" in x["study_title"] for x in records)
    assert any("компьютерной томографии" in x["study_title"] for x in records)

    laboratory = item(
        "Всем пациентам рекомендуется проведение клинико-лабораторного исследования "
        "с целью выявления воспалительного процесса."
    )
    summary = enrich_diagnostic_summary({
        "method": "recommendation_blocks_v6",
        "status": "extracted",
        "laboratory": [laboratory],
        "instrumental": [],
        "other": [],
        "counts": {"laboratory": 1, "instrumental": 0, "other": 0},
    })
    record = summary["laboratory"][0]
    assert record["verdict"] == "recommended"
    assert "клинико-лабораторного исследования" in record["study_title"]
    assert "Всем пациентам" in record["conditions"]
    assert "выявления воспалительного процесса" in record["purpose"]
    assert summary["method"] == "recommendation_blocks_v7"

    print("OK: раздельная полярность положительной и отрицательной рекомендаций")
    print("OK: исходный текст и уровень УУР/УДД сохранены")
    print("OK: выделены название исследования, условия и цель")
    print("OK: метод diagnostic_summary обновлён до v7")


if __name__ == "__main__":
    run()
