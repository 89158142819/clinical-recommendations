
import json
import time
import requests

from pathlib import Path
from datetime import datetime, timezone
from io import BytesIO
from pypdf import PdfReader


# ============================================================
# НАСТРОЙКИ
# ============================================================

DOCUMENT_ID = "1087_1"

TITLE = "Детский церебральный паралич (Церебральный паралич)"

SOURCE_URL = (
    f"https://cr.minzdrav.gov.ru/view-cr/{DOCUMENT_ID}"
)

PDF_URL = "https://apicr.minzdrav.gov.ru/api.ashx"

OUTPUT_DIR = Path("output")
OUTPUT_FILE = OUTPUT_DIR / f"{DOCUMENT_ID}.json"

MAX_ATTEMPTS = 5

CONNECT_TIMEOUT = 30
READ_TIMEOUT = 300

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

                content = bytearray()

                for chunk in response.iter_content(
                    chunk_size=CHUNK_SIZE
                ):
                    if chunk:
                        content.extend(chunk)

                pdf_bytes = bytes(content)

                if not pdf_bytes:
                    raise ValueError(
                        "Сервер вернул пустой файл"
                    )

                if not pdf_bytes.startswith(b"%PDF-"):
                    raise ValueError(
                        "Полученный файл не является PDF"
                    )

                print("PDF успешно скачан.")

                print(
                    "Размер файла: "
                    f"{len(pdf_bytes) / 1024 / 1024:.2f} МБ"
                )

                return pdf_bytes

        except (
            requests.exceptions.RequestException,
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

    raise RuntimeError(
        f"Не удалось скачать рекомендацию {DOCUMENT_ID} "
        f"после {MAX_ATTEMPTS} попыток. "
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

    for page_number, page in enumerate(
        reader.pages,
        start=1
    ):

        page_text = page.extract_text() or ""

        # Сохраняем номер страницы, как в исходном загрузчике
        pages_text.append(
            f"[Страница {page_number}]\n{page_text}"
        )

        if page_number % 25 == 0:

            print(
                f"Обработано страниц: "
                f"{page_number}/{total_pages}"
            )

    full_text = "\n\n".join(pages_text)

    if not full_text.strip():
        raise ValueError(
            "Не удалось извлечь текст из PDF. "
            "Поле full_text не будет сохранено пустым."
        )

    print()
    print("Извлечение текста завершено.")

    print(f"Количество страниц: {total_pages}")
    print(f"Длина текста: {len(full_text)} символов")

    return full_text, total_pages


# ============================================================
# СОХРАНЕНИЕ JSON
# ============================================================

def save_json(full_text, pages_count):

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    data = {
        "id": DOCUMENT_ID,

        "title": TITLE,

        "source_url": SOURCE_URL,

        "pdf_url": (
            f"{PDF_URL}?id={DOCUMENT_ID}&op=GetClinrecPdf"
        ),

        "pages_count": pages_count,

        "extracted_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "extraction_status": "success",

        "sections": {
            "definition": "",
            "icd10": "",
            "laboratory_diagnostics": "",
            "instrumental_diagnostics": "",
            "other_diagnostics": "",
            "treatment": "",
        },

        # ВАЖНО:
        # Парсер extract_sections_v2.py читает именно full_text
        "full_text": full_text,
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

    # Дополнительная проверка сохранённого файла
    with open(
        OUTPUT_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        saved_data = json.load(file)

    saved_text = saved_data.get("full_text", "")

    if not saved_text.strip():

        raise ValueError(
            "Ошибка: после сохранения поле full_text пустое."
        )

    print(
        "Проверка JSON пройдена. "
        f"Символов в full_text: {len(saved_text)}"
    )


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
    full_text, pages_count = extract_text(pdf_bytes)

    # 3. Сохранение JSON
    save_json(full_text, pages_count)

    print()
    print("=" * 60)
    print("ЗАГРУЗКА УСПЕШНО ЗАВЕРШЕНА")
    print("=" * 60)


if __name__ == "__main__":

    main()
