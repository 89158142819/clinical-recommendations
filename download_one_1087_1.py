
import json
import re
from pathlib import Path
from io import BytesIO

import requests
from pypdf import PdfReader


# ============================================================
# НАСТРОЙКИ РЕКОМЕНДАЦИИ
# ============================================================

DOCUMENT_ID = "1087_1"
TITLE = "Детский церебральный паралич (Церебральный паралич)"

PDF_URL = (
    "https://apicr.minzdrav.gov.ru/api.ashx"
    f"?id={DOCUMENT_ID}&op=GetClinrecPdf"
)

SOURCE_URL = f"https://cr.minzdrav.gov.ru/view-cr/{DOCUMENT_ID}"


# ============================================================
# ЗАГРУЗКА PDF
# ============================================================

print("=" * 60)
print("ЗАГРУЗКА КЛИНИЧЕСКОЙ РЕКОМЕНДАЦИИ")
print("=" * 60)

print(f"ID: {DOCUMENT_ID}")
print(f"Название: {TITLE}")
print(f"Источник: {SOURCE_URL}")

response = requests.get(
    PDF_URL,
    timeout=60,
    headers={
        "User-Agent": "ClinicalRecommendationsCatalog/1.0"
    }
)

response.raise_for_status()

if not response.content.startswith(b"%PDF"):
    raise RuntimeError(
        "Источник не вернул PDF-файл. "
        f"Получен Content-Type: "
        f"{response.headers.get('Content-Type')}"
    )

print("PDF успешно загружен.")


# ============================================================
# ИЗВЛЕЧЕНИЕ ТЕКСТА
# ============================================================

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
        "Текст не удалось извлечь. "
        "Возможно, PDF состоит из изображений."
    )


# ============================================================
# ПОДГОТОВКА РЕЗУЛЬТАТА
# ============================================================

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


# ============================================================
# СОХРАНЕНИЕ JSON
# ============================================================

output_dir = Path("output")
output_dir.mkdir(exist_ok=True)

output_file = output_dir / f"{DOCUMENT_ID}.json"

output_file.write_text(
    json.dumps(
        result,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)


# ============================================================
# ИТОГОВЫЙ ОТЧЁТ
# ============================================================

print()
print("=" * 60)
print("РЕЗУЛЬТАТ ЗАГРУЗКИ")
print("=" * 60)

print(f"ID рекомендации: {DOCUMENT_ID}")
print(f"Название: {TITLE}")
print(f"Количество страниц: {len(reader.pages)}")
print(f"Извлечено символов: {len(full_text)}")
print(f"Статус: {result['extraction_status']}")
print(f"Результат сохранён: {output_file}")

print("=" * 60)
print("ЗАГРУЗКА ЗАВЕРШЕНА УСПЕШНО")
print("=" * 60)
