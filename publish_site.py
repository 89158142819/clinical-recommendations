import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
SITE_DIR = BASE_DIR / "site-data"
DOCS_DIR = SITE_DIR / "docs"

SUPPORTED_DIAGNOSTIC_METHODS = {
    "recommendation_blocks_v1",
    "recommendation_blocks_v2",
    "recommendation_blocks_v3",
    "recommendation_blocks_v4",
    "recommendation_blocks_v5",
    "recommendation_blocks_v6",
}


def read_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_previous_publication():
    path = SITE_DIR / "recommendations.json"
    if not path.exists() or path.stat().st_size == 0:
        return {}

    previous = read_json(path)
    items = previous.get("recommendations", [])
    if not isinstance(items, list):
        raise ValueError("Некорректный site-data/recommendations.json")

    return {
        str(item["id"]): item
        for item in items
        if isinstance(item, dict) and item.get("id") is not None
    }


def existing_document_is_available(item):
    relative_file = item.get("document_file")
    if not relative_file:
        return False

    path = SITE_DIR / relative_file
    try:
        path.resolve().relative_to(SITE_DIR.resolve())
    except ValueError:
        return False

    return path.is_file() and path.stat().st_size > 0


def validate_new_document(document_id, data, registry_item):
    if data.get("quality_check") != "passed":
        raise ValueError(
            f"{document_id}: качество парсера "
            f"{data.get('quality_check')!r}, публикация запрещена"
        )

    if registry_item.get("status") != "passed":
        raise ValueError(
            f"{document_id}: статус реестра "
            f"{registry_item.get('status')!r}, публикация запрещена"
        )

    sections = data.get("sections")
    if not isinstance(sections, dict) or not sections:
        raise ValueError(f"{document_id}: отсутствуют извлечённые разделы")

    diagnostic_summary = data.get("diagnostic_summary")
    if (
        not isinstance(diagnostic_summary, dict)
        or diagnostic_summary.get("method") not in SUPPORTED_DIAGNOSTIC_METHODS
        or not isinstance(diagnostic_summary.get("laboratory"), list)
        or not isinstance(diagnostic_summary.get("instrumental"), list)
        or not isinstance(diagnostic_summary.get("other"), list)
    ):
        raise ValueError(
            f"{document_id}: отсутствует структурированная диагностика v2"
        )


def main():
    catalog = read_json(BASE_DIR / "catalog.json")
    registry_path = BASE_DIR / "processing_registry.json"

    if not registry_path.exists() or registry_path.stat().st_size == 0:
        registry = {
            "updated_at": None,
            "total_processed": 0,
            "results": {},
        }
    else:
        registry = read_json(registry_path)

    if not isinstance(registry.get("results"), dict):
        raise ValueError("Некорректный processing_registry.json")

    metadata = {
        str(item["id"]): item
        for item in catalog.get("recommendations", [])
    }
    previous_publication = load_previous_publication()

    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    published_by_id = {}
    preserved_count = 0
    updated_count = 0
    errors = []

    # Сначала сохраняем действующую публикацию. Старые документы не
    # исчезают из каталога только потому, что в текущем запуске
    # переобрабатывалась небольшая выборка.
    for document_id, previous_item in previous_publication.items():
        if (
            document_id in metadata
            and existing_document_is_available(previous_item)
        ):
            published_by_id[document_id] = {
                **metadata[document_id],
                "document_file": previous_item["document_file"],
                "quality_check": previous_item.get("quality_check", "passed"),
                "sections_count": previous_item.get("sections_count", 0),
            }
            preserved_count += 1

    # Затем заменяем только те документы, которые успешно обработаны
    # в текущем запуске актуальной версией парсера.
    for document_id, registry_item in registry["results"].items():
        document_id = str(document_id)

        if document_id not in metadata:
            continue

        if (
            registry_item.get("status") != "passed"
            or registry_item.get("quality_check") != "passed"
        ):
            continue

        source = OUTPUT_DIR / f"{document_id}_sections_v2.json"
        if not source.is_file() or source.stat().st_size == 0:
            # Если документ уже сохранён в действующей публикации,
            # отсутствие временного JSON допустимо: это не новый
            # результат текущего запуска, а ранее опубликованная версия.
            if document_id in published_by_id:
                continue

            errors.append(
                f"{document_id}: реестр сообщает passed, "
                "но новый JSON разделов отсутствует и прежняя публикация недоступна"
            )
            continue

        try:
            data = read_json(source)
            validate_new_document(document_id, data, registry_item)
        except Exception as error:
            errors.append(str(error))
            continue

        relative_file = f"docs/{document_id}.json"
        target = SITE_DIR / relative_file
        shutil.copyfile(source, target)

        published_by_id[document_id] = {
            **metadata[document_id],
            "document_file": relative_file,
            "quality_check": "passed",
            "sections_count": len(data["sections"]),
        }
        updated_count += 1

    if errors:
        print("ОШИБКИ ПУБЛИКАЦИИ:")
        for error in errors:
            print("-", error)
        raise SystemExit(
            f"Публикация остановлена: ошибок {len(errors)}. "
            "Каталог не перезаписан."
        )

    # Сохраняем порядок исходного каталога Минздрава.
    published = [
        published_by_id[str(item["id"])]
        for item in catalog.get("recommendations", [])
        if str(item["id"]) in published_by_id
    ]

    result = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": catalog.get("source"),
        "total": len(published),
        "recommendations": published,
    }

    SITE_DIR.mkdir(parents=True, exist_ok=True)
    with (SITE_DIR / "recommendations.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(result, file, ensure_ascii=False, indent=2)

    print("=" * 60)
    print("ПУБЛИЧНЫЙ КАТАЛОГ СФОРМИРОВАН")
    print(f"Всего опубликовано: {len(published)}")
    print(f"Сохранено ранее опубликованных: {preserved_count}")
    print(f"Обновлено новой обработкой: {updated_count}")
    print("Новые документы проходят проверку структуры и диагностики v2.")
    print("=" * 60)


if __name__ == "__main__":
    main()
