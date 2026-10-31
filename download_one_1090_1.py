import json
import time
from pathlib import Path
from datetime import datetime, timezone

import requests
from pypdf import PdfReader


DOCUMENT_ID = "1090_1"
TITLE = "Нарушения ритма сердца у новорождённого"

PDF_URL = (
    "https://apicr.minzdrav.gov.ru/api.ashx"
    f"?id={DOCUMENT_ID}&op=GetClinrecPdf"
)

SOURCE_URL = f"https://cr.minzdrav.gov.ru/view-cr/{DOCUMENT_ID}"

OUTPUT_DIR = Path("output")
PDF_PATH = OUTPUT_DIR / f"{DOCUMENT_ID}.pdf"
JSON_PATH = OUTPUT_DIR / f"{DOCUMENT_ID}.json"

MAX_ATTEMPTS = 5
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 300
CHUNK_SIZE = 1024 * 1024


def download_pdf():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/pdf,*/*",
    }

    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            print(f"Скачивание PDF: попытка {attempt}/{MAX_ATTEMPTS}")

            with requests.get(
                PDF_URL,
                headers=headers,
                stream=True,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            ) as response:
                response.raise_for_status()

                with open(PDF_PATH, "wb") as file:
                    for chunk in response.iter_content(
                        chunk_size=CHUNK_SIZE
                    ):
                        if chunk:
                            file.write(chunk)

            with open(PDF_PATH, "rb") as file:
                signature = file.read(5)

            if signature != b"%PDF-":
                raise ValueError(
                    "Полученный файл не является PDF-документом"
                )

            size_mb = PDF_PATH.stat().st_size / (1024 * 1024)
            print(f"PDF успешно скачан: {size_mb:.2f} МБ")
            return

        except Exception as error:
            last_error = error
            print(f"Ошибка скачивания: {error}")

            if attempt < MAX_ATTEMPTS:
                delay = attempt * 10
                print(f"Повтор через {delay} секунд")
                time.sleep(delay)

    raise RuntimeError(
        f"Не удалось скачать рекомендацию {DOCUMENT_ID}: {last_error}"
    )


def extract_pdf_text():
    print("Извлечение текста из PDF...")

    reader = PdfReader(str(PDF_PATH))

    pages_text = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        pages_text.append(
            f"\n\n[СТРАНИЦА {page_number}]\n\n{page_text}"
        )

    full_text = "\n".join(pages_text).strip()

    if not full_text:
        raise ValueError(
            "Из PDF не удалось извлечь текст. "
            "Поле full_text оказалось пустым."
        )

    print(f"Количество страниц: {len(reader.pages)}")
    print(f"Количество символов: {len(full_text)}")

    return full_text, len(reader.pages)


def save_json(full_text, pages_count):
    result = {
        "id": DOCUMENT_ID,
        "title": TITLE,
        "source_url": SOURCE_URL,
        "pdf_url": PDF_URL,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "pages_count": pages_count,
        "extraction_status": "success",
        "full_text": full_text,
        "sections": {},
    }

    with open(JSON_PATH, "w", encoding="utf-8") as file:
        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print(f"JSON сохранён: {JSON_PATH}")


def main():
    print("=" * 60)
    print(f"ЗАГРУЗКА КЛИНИЧЕСКОЙ РЕКОМЕНДАЦИИ {DOCUMENT_ID}")
    print(TITLE)
    print("=" * 60)

    download_pdf()
    full_text, pages_count = extract_pdf_text()
    save_json(full_text, pages_count)

    print("=" * 60)
    print("ЗАГРУЗКА УСПЕШНО ЗАВЕРШЕНА")
    print("=" * 60)


if __name__ == "__main__":
    main()
