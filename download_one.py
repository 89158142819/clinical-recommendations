
import json
import re
from pathlib import Path

import requests
from pypdf import PdfReader
from io import BytesIO

DOCUMENT_ID = "749_2"
TITLE = "Грипп у взрослых"

PDF_URL = (
    "https://apicr.minzdrav.gov.ru/api.ashx"
    f"?id={DOCUMENT_ID}&op=GetClinrecPdf"
)

SOURCE_URL = f"https://cr.minzdrav.gov.ru/view-cr/{DOCUMENT_ID}"

print(f"Загрузка документа: {TITLE}")

response = requests.get(
    PDF_URL,
    timeout=60,
    headers={"User-Agent": "ClinicalRecommendationsCatalog/1.0"}
)
response.raise_for_status()

if not response.content.startswith(b"%PDF"):
    raise RuntimeError(
        "Источник не вернул PDF-файл. "
        f"Получен Content-Type: {response.headers.get('Content-Type')}"
    )

reader = PdfReader(BytesIO(response.content))

pages = []
for number, page in enumerate(reader.pages, start=1):
    text = page.extract_text() or ""
    pages.append({
        "page": number,
        "text": text
    })

full_text = "\n\n".join(
    f"[Страница {p['page']}]\n{p['text']}"
    for p in pages
)

if not full_text.strip():
    raise RuntimeError(
        "Текст не удалось извлечь. Возможно, PDF состоит из изображений."
    )

def clean(text):
    return re.sub(r"\s+", " ", text).strip()

result = {
    "id": DOCUMENT_ID,
    "title": TITLE,
    "source_url": SOURCE_URL,
    "pdf_url": PDF_URL,
    "pages_count": len(reader.pages),
    "extracted_at": None,
    "extraction_status": "text_extracted",
    "sections": {
        "definition": "",
        "icd10": "",
        "laboratory_diagnostics": "",
        "instrumental_diagnostics": "",
        "other_diagnostics": "",
        "treatment": ""
    },
    "full_text": full_text
}

Path("output").mkdir(exist_ok=True)

output_file = Path("output") / f"{DOCUMENT_ID}.json"
output_file.write_text(
    json.dumps(result, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print(f"Готово! Страниц: {len(reader.pages)}")
print(f"Извлечено символов: {len(full_text)}")
print(f"Результат сохранён: {output_file}")
