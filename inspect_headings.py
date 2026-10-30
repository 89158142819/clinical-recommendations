
import json
import re
from pathlib import Path

source = Path("output/749_2.json")
data = json.loads(source.read_text(encoding="utf-8"))

text = data.get("full_text", "")

patterns = [
    r"^\s*\d+(?:\.\d+)*\.?\s+.{3,}",
    r"^\s*(?:ОПРЕДЕЛЕНИЕ|ДИАГНОСТИКА|ЛЕЧЕНИЕ|"
    r"ЛАБОРАТОРНАЯ ДИАГНОСТИКА|"
    r"ИНСТРУМЕНТАЛЬНАЯ ДИАГНОСТИКА)\s*$"
]

found = []

for line in text.splitlines():
    line = line.strip()

    if not line or len(line) > 180:
        continue

    if any(re.match(p, line, re.IGNORECASE) for p in patterns):
        found.append(line)

result = "\n".join(dict.fromkeys(found))

Path("output/headings.txt").write_text(
    result,
    encoding="utf-8"
)

print("Найдено возможных заголовков:", len(found))
print(result[:12000])
