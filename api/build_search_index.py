import json
import re
from pathlib import Path

import snowballstemmer

ROOT = Path(__file__).resolve().parent.parent
SITE_DATA = ROOT / "site-data"
CATALOG_FILE = SITE_DATA / "recommendations.json"
OUTPUT_FILE = Path(__file__).resolve().parent / "search_index.json"

SECTIONS = [
    ("diagnostics", "Диагностика: общие положения"),
    ("complaints_anamnesis", "Жалобы и анамнез"),
    ("physical_examination", "Физикальное обследование"),
    ("laboratory_diagnostics", "Лабораторная диагностика"),
    ("instrumental_diagnostics", "Инструментальная диагностика"),
    ("other_diagnostics", "Иные диагностические исследования"),
]
TOKEN_RE = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)
stemmer = snowballstemmer.stemmer("russian")
STOP_WORDS = set("""
и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по
только ее мне было вот от меня еще нет о из ему теперь когда даже ну вдруг ли
если уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя
ничего ей может они тут где есть надо для при при этом какие какая какой
диагностика диагностике диагностику исследование исследования исследований
метод методы раздел рекомендация рекомендации клинический клинические
""".split())


def tokenize(text):
    words = [w.lower().replace("ё", "е") for w in TOKEN_RE.findall(str(text or ""))]
    words = [w for w in words if len(w) > 2 and w not in STOP_WORDS]
    return stemmer.stemWords(words)


def split_chunks(text, limit=1500):
    text = str(text or "").replace("\r", "\n")
    paragraphs = [re.sub(r"[ \t]+", " ", p).strip() for p in text.split("\n") if p.strip()]
    chunks, current = [], ""
    for paragraph in paragraphs:
        if len(paragraph) > limit:
            if current:
                chunks.append(current)
                current = ""
            sentences = re.split(r"(?<=[.!?])\s+", paragraph)
            part = ""
            for sentence in sentences:
                if len(part) + len(sentence) + 1 <= limit:
                    part = (part + " " + sentence).strip()
                else:
                    if part:
                        chunks.append(part)
                    while len(sentence) > limit:
                        chunks.append(sentence[:limit])
                        sentence = sentence[limit:]
                    part = sentence
            if part:
                current = part
            continue
        if len(current) + len(paragraph) + 2 <= limit:
            current = (current + "\n" + paragraph).strip()
        else:
            if current:
                chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return chunks


def main():
    if not CATALOG_FILE.exists():
        raise FileNotFoundError(f"Не найден каталог: {CATALOG_FILE}")

    catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    recommendations = catalog.get("recommendations", [])
    chunks = []
    skipped = []

    for item in recommendations:
        document_id = str(item.get("id", "")).strip()
        relative = str(item.get("document_file", "")).strip()
        if not document_id or not relative:
            skipped.append(document_id or "без ID")
            continue

        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            skipped.append(document_id)
            continue

        document_path = SITE_DATA / relative_path
        if not document_path.exists():
            skipped.append(document_id)
            continue

        try:
            document = json.loads(document_path.read_text(encoding="utf-8"))
        except Exception:
            skipped.append(document_id)
            continue

        sections = document.get("sections") or {}
        title = str(item.get("title") or document.get("title") or document_id)
        source_url = f"https://cr.minzdrav.gov.ru/view-cr/{document_id}"

        for key, label in SECTIONS:
            section_text = str(sections.get(key) or "").strip()
            if not section_text:
                continue

            for part_number, chunk in enumerate(split_chunks(section_text), start=1):
                tokens = tokenize(title + " " + label + " " + chunk)
                if not tokens:
                    continue
                chunks.append({
                    "id": document_id,
                    "title": title,
                    "icd10": str(item.get("icd10") or ""),
                    "age_category": str(item.get("age_category") or ""),
                    "application_status": str(item.get("application_status") or ""),
                    "source_url": source_url,
                    "section_key": key,
                    "section_label": label,
                    "part": part_number,
                    "text": chunk,
                    "tokens": tokens,
                    "title_tokens": tokenize(title + " " + item.get("icd10", "")),
                })

    if not chunks:
        raise RuntimeError("Индекс пуст: не найдено ни одного диагностического фрагмента.")

    payload = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "catalog_total": len(recommendations),
        "indexed_chunks": len(chunks),
        "indexed_documents": len({c["id"] for c in chunks}),
        "skipped_documents": skipped,
        "chunks": chunks,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Создан индекс: {len(chunks)} фрагментов, {payload['indexed_documents']} документов.")
    print(f"Пропущено документов: {len(skipped)}")


if __name__ == "__main__":
    main()
