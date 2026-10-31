
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO

import requests
from pypdf import PdfReader


# ============================================================
# Настройки
# ============================================================

DEFAULT_DOCUMENT_ID = "759_2"

DEFAULT_TITLE = (
    "Периодический синдром, ассоциированный с мутацией "
    "гена рецептора фактора некроза опухоли (TRAPS)"
)

OUTPUT_DIR = Path("output")

HEADERS = {
    "User-Agent": "ClinicalRecommendationsCatalog/1.0"
}

SECTION_KEYS = [
    "terms",
    "definition",
    "etiology_pathogenesis",
    "epidemiology",
    "icd10",
    "classification",
    "clinical_picture",
    "diagnostics",
    "complaints_anamnesis",
    "physical_examination",
    "laboratory_diagnostics",
    "instrumental_diagnostics",
    "other_diagnostics",
    "treatment",
    "rehabilitation",
]


# ============================================================
# Загрузка и извлечение текста
# ============================================================

def download_document(document_id, title):

    pdf_url = (
        "https://apicr.minzdrav.gov.ru/api.ashx"
        f"?id={document_id}&op=GetClinrecPdf"
    )

    source_url = (
        f"https://cr.minzdrav.gov.ru/view-cr/{document_id}"
    )

    print("=" * 70)
    print("ЗАГРУЗКА КЛИНИЧЕСКОЙ РЕКОМЕНДАЦИИ")
    print("=" * 70)

    print(f"ID: {document_id}")
    print(f"Название: {title}")
    print()

    # --------------------------------------------------------
    # Скачивание PDF
    # --------------------------------------------------------

    print("Скачивание PDF...")

    response = requests.get(
        pdf_url,
        timeout=120,
        headers=HEADERS
    )

    response.raise_for_status()

    if not response.content.startswith(b"%PDF"):

        raise RuntimeError(
            "Источник не вернул PDF-файл. "
            f"Content-Type: {response.headers.get('Content-Type')}"
        )

    print(
        f"PDF скачан. Размер: "
        f"{len(response.content):,} байт"
    )

    # --------------------------------------------------------
    # Чтение PDF
    # --------------------------------------------------------

    reader = PdfReader(
        BytesIO(response.content)
    )

    if reader.is_encrypted:

        try:
            result = reader.decrypt("")

            if not result:
                raise RuntimeError(
                    "PDF защищён паролем. "
                    "Не удалось открыть документ."
                )

        except Exception as error:

            raise RuntimeError(
                f"Не удалось расшифровать PDF: {error}"
            )

    print(f"Количество страниц: {len(reader.pages)}")
    print()
    print("Извлечение текста...")

    pages = []

    for number, page in enumerate(
        reader.pages,
        start=1
    ):

        try:

            page_text = page.extract_text() or ""

        except Exception as error:

            print(
                f"Предупреждение: ошибка извлечения "
                f"текста со страницы {number}: {error}"
            )

            page_text = ""

        pages.append({
            "page": number,
            "text": page_text,
        })

        if number % 20 == 0:

            print(
                f"Обработано страниц: "
                f"{number}/{len(reader.pages)}"
            )

    # --------------------------------------------------------
    # Объединение текста
    # --------------------------------------------------------

    full_text = "\n\n".join(
        f"[Страница {page['page']}]\n{page['text']}"
        for page in pages
    )

    if not full_text.strip():

        raise RuntimeError(
            "Текст не удалось извлечь. "
            "Возможно, PDF состоит из изображений "
            "или не содержит текстового слоя."
        )

    pages_with_text = sum(
        1
        for page in pages
        if page["text"].strip()
    )

    empty_pages = [
        page["page"]
        for page in pages
        if not page["text"].strip()
    ]

    print()
    print("РЕЗУЛЬТАТ ИЗВЛЕЧЕНИЯ")
    print("-" * 70)

    print(f"Всего страниц: {len(reader.pages)}")
    print(f"Страниц с текстом: {pages_with_text}")
    print(f"Пустых страниц: {len(empty_pages)}")
    print(f"Извлечено символов: {len(full_text):,}")

    # --------------------------------------------------------
    # Проверка объёма текста
    # --------------------------------------------------------

    if len(full_text) < 1000:

        raise RuntimeError(
            "Извлечено подозрительно мало текста: "
            f"{len(full_text)} символов."
        )

    # --------------------------------------------------------
    # Формирование JSON
    # --------------------------------------------------------

    result = {

        "id": document_id,

        "title": title,

        "source_url": source_url,

        "pdf_url": pdf_url,

        "pages_count": len(reader.pages),

        "extracted_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "extraction_status": "text_extracted",

        "sections": {
            key: ""
            for key in SECTION_KEYS
        },

        "full_text": full_text,

        "extraction_info": {
            "pages_total": len(reader.pages),
            "pages_with_text": pages_with_text,
            "empty_pages": empty_pages,
            "text_length": len(full_text),
            "method": "pypdf",
        },
    }

    # --------------------------------------------------------
    # Сохранение JSON
    # --------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    output_file = (
        OUTPUT_DIR / f"{document_id}.json"
    )

    with output_file.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2
        )

    # --------------------------------------------------------
    # Итоговая проверка сохранённого файла
    # --------------------------------------------------------

    with output_file.open(
        "r",
        encoding="utf-8"
    ) as file:

        saved_data = json.load(file)

    saved_text = saved_data.get("full_text", "")

    if not saved_text.strip():

        raise RuntimeError(
            "Файл сохранён, но поле full_text пустое."
        )

    print()
    print("=" * 70)
    print("ЗАГРУЗКА ЗАВЕРШЕНА")
    print("=" * 70)

    print(f"Документ: {document_id}")
    print(f"Название: {title}")
    print(f"Страниц: {len(reader.pages)}")
    print(f"Символов: {len(saved_text):,}")
    print(f"Файл: {output_file}")
    print("Поле full_text: присутствует")
    print("Проверка сохранения: пройдена")

    if empty_pages:

        print()
        print(
            "ВНИМАНИЕ: страницы без извлечённого текста:"
        )

        print(empty_pages)

    print("=" * 70)

    return output_file


# ============================================================
# Точка входа
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Скачивание клинической рекомендации "
            "и извлечение полного текста из PDF."
        )
    )

    parser.add_argument(
        "--id",
        default=DEFAULT_DOCUMENT_ID,
        help="ID клинической рекомендации"
    )

    parser.add_argument(
        "--title",
        default=DEFAULT_TITLE,
        help="Название клинической рекомендации"
    )

    args = parser.parse_args()

    download_document(
        document_id=args.id,
        title=args.title
    )


if __name__ == "__main__":
    main()
