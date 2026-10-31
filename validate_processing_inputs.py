import json
import os
from pathlib import Path

batch = int(os.environ["BATCH_SIZE"])
start = int(os.environ["START_OFFSET"])
end = int(os.environ["END_OFFSET"])

with Path("catalog.json").open(encoding="utf-8") as file:
    catalog = json.load(file)

recommendations = catalog.get("recommendations", [])
total = len(recommendations)

if catalog.get("total") != total:
    raise SystemExit("Размер каталога не совпадает с количеством рекомендаций")
if not 1 <= batch <= 100:
    raise SystemExit("Размер партии должен быть от 1 до 100")
if not 0 <= start < end <= total:
    raise SystemExit(f"Диапазон должен быть в пределах 0–{total}")

print(f"Всего документов: {total}")
print(f"Диапазон: {start}–{end - 1}")
print(f"Размер партии: {batch}")
