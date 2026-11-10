import re
import unicodedata
from collections import Counter


PAGE_LABEL_RE = re.compile(
    r"^\s*(?:\[?\s*(?:страница|стр\.?|page)\s*\d+\s*\]?)\s*$",
    re.IGNORECASE,
)

PAGE_NUMBER_RE = re.compile(r"^\s*(?:\d{1,4}|[-–—]\s*\d{1,4}\s*[-–—])\s*$")

BULLET_RE = re.compile(r"^\s*(?:[•●▪◦‣⁃]|[-–—]\s+|\d+[.)]\s+|[а-яёА-ЯЁ][.)]\s+)")


def _normalize_line(line):
    line = line.replace("\u00a0", " ")
    line = line.replace("\u202f", " ")
    line = line.replace("\u00ad", "")
    line = line.replace("\u200b", "")
    line = line.replace("\ufeff", "")
    line = re.sub(r"[\t ]+", " ", line)
    return line.strip()


def _line_key(line):
    value = line.lower().replace("ё", "е")
    value = re.sub(r"\d+", "#", value)
    value = re.sub(r"\s+", " ", value)
    return re.sub(r"[^а-яa-z# ]", "", value).strip()


def _collect_repeated_margins(pages):
    candidates = []
    page_count = len(pages)

    for page in pages:
        lines = [
            _normalize_line(line)
            for line in str(page.get("text") or "").splitlines()
        ]
        lines = [line for line in lines if line]
        if not lines:
            continue

        candidates.extend(lines[:2])
        candidates.extend(lines[-2:])

    counts = Counter(
        _line_key(line)
        for line in candidates
        if len(_line_key(line)) >= 5
    )

    threshold = max(3, int(page_count * 0.30 + 0.999))
    return {
        key for key, count in counts.items()
        if count >= threshold
    }


def clean_page_text(page_text, repeated_margins=None):
    repeated_margins = repeated_margins or set()
    raw_lines = str(page_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [_normalize_line(line) for line in raw_lines]

    # Удаляем служебные метки страниц, одиночные номера страниц
    # по краям страницы и повторяющиеся колонтитулы.
    kept = []
    nonempty_positions = [
        index for index, line in enumerate(lines) if line
    ]
    first_positions = set(nonempty_positions[:2])
    last_positions = set(nonempty_positions[-2:])

    for index, line in enumerate(lines):
        if not line:
            kept.append("")
            continue

        if PAGE_LABEL_RE.match(line):
            continue

        if _line_key(line) in repeated_margins:
            continue

        if index in first_positions | last_positions and PAGE_NUMBER_RE.match(line):
            continue

        kept.append(line)

    # Склеиваем слова, разорванные переносом строки в PDF.
    text = "\n".join(kept)
    text = re.sub(r"(?<=[А-Яа-яЁё])-\s*\n\s*(?=[а-яё])", "", text)

    # Нормализуем пробелы вокруг пунктуации и лишние пустые строки,
    # но сохраняем абзацы и отдельные строки списков.
    normalized_lines = []
    for line in text.split("\n"):
        line = _normalize_line(line)
        if line:
            line = re.sub(r"\s+([,.;:!?%)\]])", r"\1", line)
            line = re.sub(r"([(])\s+", r"\1", line)
        normalized_lines.append(line)

    text = "\n".join(normalized_lines)
    text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    return text.strip()


def clean_extracted_pages(pages):
    repeated_margins = _collect_repeated_margins(pages)
    cleaned_pages = []

    for page in pages:
        cleaned = clean_page_text(
            page.get("text", ""),
            repeated_margins=repeated_margins,
        )
        if cleaned:
            cleaned_pages.append(cleaned)

    return "\n\n".join(cleaned_pages), sorted(repeated_margins)


def clean_full_text(text):
    # Поддержка ранее сохранённых исходных JSON с метками страниц.
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    page_pattern = re.compile(
        r"(?im)^\s*\[?\s*(?:страница|стр\.?|page)\s*\d+\s*\]?\s*$"
    )

    if page_pattern.search(text):
        raw_pages = page_pattern.split(text)
        pages = [{"text": part} for part in raw_pages if part.strip()]
        cleaned, _ = clean_extracted_pages(pages)
        return cleaned

    # Без меток страниц удаляем только номера на внешних краях текста,
    # чтобы не затронуть нумерованные медицинские перечни внутри.
    return clean_page_text(text)
