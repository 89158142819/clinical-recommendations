
import json
import time
import requests

from pathlib import Path
from pypdf import PdfReader
from io import BytesIO


# ============================================================
# НАСТРОЙКИ
# ============================================================

DOCUMENT_ID = "1087_1"
TITLE = "Детский церебральный паралич (Церебральный паралич)"

SOURCE_URL = f"https://cr.minzdrav.gov.ru/view-cr/{DOCUMENT_ID}"

PDF_URL = "https://apicr.minzdrav.gov.ru/api.ashx"

OUTPUT_DIR = Path("output")
OUTPUT_FILE = OUTPUT_DIR / f"{DOCUMENT_ID}.json"

# Количество попыток скачивания
MAX_ATTEMPTS = 5

# Тайм-аут подключения и чтения ответа
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 300

# Размер блока при потоковой загрузке
CHUNK_SIZE = 1024 * 1024


# ============================================================
# СКАЧИВАНИЕ PDF
# ============================================================

def download_pdf():

    session = requests.Session()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,*/*",
        "Connection": "keep-alive",
    }

    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):

        print()
        print(f"Попытка скачивания: {attempt}/{MAX_ATTEMPTS}")

        try:

            with session.get(
                PDF_URL,
                params={
                    "id": DOCUMENT_ID,
                    "op": "GetClinrecPdf",
                },
                headers=headers,
                stream=True,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            ) as response:

                response.raise_for_status()

                content_type = response.headers.get(
                    "Content-Type", ""
                ).lower()

                content = bytearray()

                for chunk in response.iter_content(
                    chunk_size=CHUNK_SIZE
                ):

                    if chunk:
                        content.extend(chunk)

                pdf_bytes = bytes(content)

                if not pdf_bytes:
                    raise ValueError("Сервер вернул пустой файл")

                if not pdf_bytes.startswith(b"%PDF-"):
                    raise ValueError(
                        "Полученный файл не является PDF. "
                        f"Content-Type: {content_type}"
                    )

                print("PDF успешно скачан.")
                print(
                    f"Размер файла: "
                    f"{len(pdf_bytes) / 1024 / 1024:.2f} МБ"
                )

                session.close()

                return pdf_bytes

        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
            ValueError,
        ) as error:

            last_error = error

            print(f"Ошибка скачивания: {error}")

            if attempt < MAX_ATTEMPTS:

                pause = attempt * 15

                print(
                    f"Повторная попытка через {pause} секунд..."
                )

                time.sleep(pause)

    session.close()

    raise RuntimeError(
        "Не удалось скачать клиническую рекомендацию "
        f"{DOCUMENT_ID} после {MAX_ATTEMPTS} попыток. "
        f"Последняя ошибка: {last_error}"
    )


# ============================================================
# ИЗВЛЕЧЕНИЕ ТЕКСТА ИЗ PDF
# ============================================================

def extract_text(pdf_bytes):

    print()
    print("Извлечение текста из PDF...")

    reader = PdfReader(BytesIO(pdf_bytes))

    pages_text = []

    total_pages = len(reader.pages)

    print(f"Количество страниц: {total_pages}")

    for page_number, page in enumerate(reader.pages, start=1):

        text = page.extract_text() or ""

        pages_text.append(text)

        if page_number % 25 == 0:
            print(
                f"Обработано страниц: "
                f"{page_number}/{total_pages}"
            )

    full_text = "\n\n".join(pages_text)

    if not full_text.strip():
        raise ValueError(
            "Не удалось извлечь текст из PDF"
        )

    print("Извлечение текста завершено.")
    print(f"Длина текста: {len(full_text)} символов")

    return full_text


# ============================================================
# СОХРАНЕНИЕ JSON
# ============================================================

def save_json(text):

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    data = {
        "id": DOCUMENT_ID,
        "title": TITLE,
        "source_url": SOURCE_URL,
        "text": text,
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )

    print()
    print("JSON успешно сохранён.")
    print(f"Файл: {OUTPUT_FILE}")


# ============================================================
# ОСНОВНОЙ ЗАПУСК
# ============================================================

def main():

    print("=" * 60)
    print("ЗАГРУЗКА КЛИНИЧЕСКОЙ РЕКОМЕНДАЦИИ")
    print("=" * 60)

    print(f"ID: {DOCUMENT_ID}")
    print(f"Название: {TITLE}")
    print(f"Источник: {SOURCE_URL}")

    # 1. Скачивание PDF
    pdf_bytes = download_pdf()

    # 2. Извлечение текста
    full_text = extract_text(pdf_bytes)

    # 3. Сохранение JSON
    save_json(full_text)

    print()
    print("=" * 60)
    print("ЗАГРУЗКА УСПЕШНО ЗАВЕРШЕНА")
    print("=" * 60)


if __name__ == "__main__":

    main()
