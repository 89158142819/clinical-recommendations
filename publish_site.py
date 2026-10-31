import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
SITE_DIR = BASE_DIR / "site-data"
DOCS_DIR = SITE_DIR / "docs"

PUBLISH_IDS = [
    "1067_1", "1066_1", "1065_1", "1064_1", "762_2",
    "507_4", "535_3", "937_2", "1062_1", "760_2",
    "761_2", "771_2", "1060_1", "1061_1", "1058_1",
    "593_4", "1059_1", "1057_1", "260_3", "123_6",
    "1056_1", "1053_1", "404_2", "318_3", "773_2",
    "1048_1", "1047_1", "511_2", "1045_1", "1046_1",
    "1043_1", "1044_1", "1042_1", "1040_1", "1041_1",
    "1037_1", "1033_1", "1036_1", "1035_1", "1034_1",
    "1032_1",
]

def read_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def main():
    catalog = read_json(BASE_DIR / "catalog.json")
    registry = read_json(BASE_DIR / "processing_registry.json")
    metadata = {str(x["id"]): x for x in catalog["recommendations"]}

    if DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    published = []
    errors = []

    for document_id in PUBLISH_IDS:
        source = OUTPUT_DIR / f"{document_id}_sections_v2.json"
        if not source.exists():
            errors.append(f"{document_id}: отсутствует {source}")
            continue

        data = read_json(source)
        registry_item = registry.get("results", {}).get(document_id, {})

        if data.get("quality_check") != "passed":
            errors.append(
                f"{document_id}: статус парсера "
                f"{data.get('quality_check')!r}, публикация запрещена"
            )
            continue

        if registry_item.get("status") != "passed":
            errors.append(
                f"{document_id}: статус реестра "
                f"{registry_item.get('status')!r}, публикация запрещена"
            )
            continue

        item = metadata.get(document_id)
        if not item:
            errors.append(f"{document_id}: нет метаданных в catalog.json")
            continue

        sections = data.get("sections")
        if not isinstance(sections, dict) or not sections:
            errors.append(f"{document_id}: отсутствуют извлечённые разделы")
            continue

        diagnostic_summary = data.get("diagnostic_summary")
        if (
            not isinstance(diagnostic_summary, dict)
            or not isinstance(diagnostic_summary.get("laboratory"), list)
            or not isinstance(diagnostic_summary.get("instrumental"), list)
        ):
            errors.append(
                f"{document_id}: отсутствует структурированная диагностика. "
                "Документ необходимо обработать парсером v7."
            )
            continue

        relative_file = f"docs/{document_id}.json"
        target = SITE_DIR / relative_file
        shutil.copyfile(source, target)

        published.append({
            **item,
            "document_file": relative_file,
            "quality_check": "passed",
            "sections_count": len(sections),
        })

    if errors:
        print("ОШИБКИ ПУБЛИКАЦИИ:")
        for error in errors:
            print("-", error)
        raise SystemExit(
            f"Публикация остановлена: ошибок {len(errors)}. "
            "Каталог не сформирован."
        )

    result = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": catalog.get("source"),
        "total": len(published),
        "recommendations": published,
    }

    SITE_DIR.mkdir(parents=True, exist_ok=True)
    with (SITE_DIR / "recommendations.json").open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print("ПУБЛИЧНЫЙ КАТАЛОГ СФОРМИРОВАН")
    print(f"Опубликовано рекомендаций: {len(published)}")
    print(f"Файл каталога: {SITE_DIR / 'recommendations.json'}")
    print(f"Файлы разделов: {DOCS_DIR}")
    print("=" * 60)

if __name__ == "__main__":
    main()
