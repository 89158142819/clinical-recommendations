import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
SITE_DIR = BASE_DIR / "site-data"
DOCS_DIR = SITE_DIR / "docs"

def read_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def main():
    catalog = read_json(BASE_DIR / "catalog.json")
    registry = read_json(BASE_DIR / "processing_registry.json")
    metadata = {str(x["id"]): x for x in catalog["recommendations"]}

    # Не удаляем уже опубликованные документы: каталог пополняется
    # партиями. В публичный список попадают только документы, прошедшие
    # структурную проверку актуальным парсером v8 и имеющие новую
    # структурированную диагностику.
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    published = []
    errors = []

    for item in catalog["recommendations"]:
        document_id = str(item["id"])
        registry_item = registry.get("results", {}).get(document_id, {})

        if (
            registry_item.get("status") != "passed"
            or registry_item.get("quality_check") != "passed"
            or registry_item.get("extraction_method") != "universal_structural_headings_v8"
        ):
            continue

        source = OUTPUT_DIR / f"{document_id}_sections_v2.json"
        existing = DOCS_DIR / f"{document_id}.json"

        if source.exists():
            data = read_json(source)
        elif existing.exists():
            data = read_json(existing)
        else:
            errors.append(f"{document_id}: нет JSON разделов для публикации")
            continue

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
            or diagnostic_summary.get("method") != "recommendation_blocks_v2"
            or not isinstance(diagnostic_summary.get("laboratory"), list)
            or not isinstance(diagnostic_summary.get("instrumental"), list)
            or not isinstance(diagnostic_summary.get("other"), list)
        ):
            errors.append(
                f"{document_id}: отсутствует структурированная диагностика v2. "
                "Документ необходимо повторно обработать."
            )
            continue

        relative_file = f"docs/{document_id}.json"
        target = SITE_DIR / relative_file
        if source.exists():
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
    print("Учитываются только записи со статусом passed и парсером v8.")
    print(f"Файл каталога: {SITE_DIR / 'recommendations.json'}")
    print(f"Файлы разделов: {DOCS_DIR}")
    print("=" * 60)

if __name__ == "__main__":
    main()
