import json
from pathlib import Path

registry_path = Path("processing_registry.json")
if not registry_path.exists():
    print("Реестр обработки пока отсутствует.")
    raise SystemExit(0)

with registry_path.open(encoding="utf-8") as file:
    registry = json.load(file)

results = registry.get("results", {})
counts = {}
for item in results.values():
    status = item.get("status", "unknown")
    counts[status] = counts.get(status, 0) + 1

print("Всего записей в реестре:", len(results))
for status in ("passed", "review_required", "failed"):
    print(f"{status}: {counts.get(status, 0)}")

site_path = Path("site-data/recommendations.json")
if site_path.exists():
    with site_path.open(encoding="utf-8") as file:
        site = json.load(file)
    print("Опубликовано на сайте:", site.get("total", 0))
else:
    print("Каталог публикации пока отсутствует.")
