
import argparse
import io
import json
import re
import time
from pathlib import Path

import requests
from pypdf import PdfReader


API_URL = (
    "https://apicr.minzdrav.gov.ru/API.ashx"
    "?op=GetClinrecPdf&id={}"
)

OUTPUT = Path("output/catalog_discovered.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def extract_title(pdf_bytes):
    """Пытается определить название по первым страницам PDF."""

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))

        text = ""

        for page in reader.pages[:3]:
            text += "\n" + (page.extract_text() or "")

        lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in text.splitlines()
        ]

        excluded = [
            "клинические рекомендации",
            "министерство здравоохранения",
            "российская федерация",
            "москва",
            "утверждено",
            "протокол",
            "год"
        ]

        for line in lines:
            lower = line.lower()

            if len(line) < 5 or len(line) > 150:
                continue

            if any(word in lower for word in excluded):
                continue

            if not re.search(r"[А-Яа-яЁё]", line):
                continue

            return line

        return "Название требует проверки"

    except Exception:
        return "Название требует проверки"


def check_document(document_id):
    """Проверяет наличие PDF по идентификатору и версии."""

    url = API_URL.format(document_id)

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        if response.status_code != 200:
            return None

        content = response.content

        if not content.startswith(b"%PDF"):
            return None

        title = extract_title(content)

        return {
            "id": document_id,
            "title": title,
            "pdf_url": url,
            "source_url": (
                "https://cr.minzdrav.gov.ru/view-cr/"
                + document_id
            )
        }

    except requests.RequestException as error:
        print(
            f"Ошибка при проверке {document_id}: {error}"
        )
        return None


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--min-id",
        type=int,
        default=740
    )

    parser.add_argument(
        "--max-id",
        type=int,
        default=755
    )

    parser.add_argument(
        "--min-ver",
        type=int,
        default=1
    )

    parser.add_argument(
        "--max-ver",
        type=int,
        default=5
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=0.6
    )

    args = parser.parse_args()

    OUTPUT.parent.mkdir(exist_ok=True)

    documents = []

    total = (
        (args.max_id - args.min_id + 1)
        * (args.max_ver - args.min_ver + 1)
    )

    checked = 0

    print("Начинаем поиск рекомендаций.")
    print("Всего проверок:", total)

    for number in range(args.min_id, args.max_id + 1):

        for version in range(
            args.min_ver,
            args.max_ver + 1
        ):

            document_id = f"{number}_{version}"

            result = check_document(document_id)

            checked += 1

            if result:
                documents.append(result)

                print(
                    f"[НАЙДЕН] {document_id}: "
                    f"{result['title']}"
                )
            else:
                print(
                    f"[НЕ НАЙДЕН] {document_id}"
                )

            time.sleep(args.delay)

    result = {
        "source": "https://cr.minzdrav.gov.ru/clin-rec",
        "search_method": "PDF endpoint ID/version scan",
        "checked": checked,
        "found": len(documents),
        "documents": documents
    }

    OUTPUT.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print("\nПоиск завершён.")
    print("Проверено:", checked)
    print("Найдено PDF:", len(documents))
    print("Результат:", OUTPUT)


if __name__ == "__main__":
    main()
