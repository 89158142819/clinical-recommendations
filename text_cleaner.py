import re
from collections import Counter
from functools import lru_cache


PAGE_LABEL_RE = re.compile(
    r"^\s*(?:\[?\s*(?:страница|стр\.?|page)\s*\d+\s*\]?)\s*$",
    re.IGNORECASE,
)

PAGE_NUMBER_RE = re.compile(r"^\s*(?:\d{1,4}|[-–—]\s*\d{1,4}\s*[-–—])\s*$")


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

        # Каждая строка учитывается не более одного раза на страницу.
        page_candidates = set(lines[:2] + lines[-2:])
        candidates.extend(page_candidates)

    counts = Counter(
        _line_key(line)
        for line in candidates
        if len(_line_key(line)) >= 5
    )

    threshold = max(2, int(page_count * 0.50 + 0.999))
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
    text = repair_split_words(text)
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


# Морфологическая проверка помогает восстанавливать слова, которые PDF
# разбил пробелом внутри слова: «подозрение м», «ул ьтразвукового».
try:
    import pymorphy3
except ImportError:
    pymorphy3 = None


@lru_cache(maxsize=1)
def _get_morph_analyzer():
    if pymorphy3 is None:
        return None
    try:
        return pymorphy3.MorphAnalyzer()
    except Exception:
        return None


@lru_cache(maxsize=50000)
def _morphology_has_analyzer(word, accepted_analyzers):
    if not word or not re.fullmatch(r"[а-яё]+", word, re.IGNORECASE):
        return False

    analyzer = _get_morph_analyzer()
    if analyzer is None:
        return False

    try:
        parses = analyzer.parse(word.lower())
    except Exception:
        return False

    for parsed in parses:
        if getattr(parsed, "score", 0) < 0.5:
            continue

        for method in getattr(parsed, "methods_stack", ()):
            analyzer_method = method[0] if method else None
            if (
                analyzer_method
                and type(analyzer_method).__name__ in accepted_analyzers
            ):
                return True

    return False


@lru_cache(maxsize=50000)
def _is_dictionary_word(word):
    # Однобуквенные самостоятельные русские слова ограничены этим набором.
    # Буква «й» и другие обломки не должны считаться отдельными словами.
    if len(word) == 1 and word.lower() not in {"а", "в", "и", "к", "о", "с", "у", "я"}:
        return False

    return _morphology_has_analyzer(
        word,
        frozenset({"DictionaryAnalyzer"}),
    )


@lru_cache(maxsize=50000)
def _is_valid_joined_word(word):
    # Для объединённой формы допускаем словарные формы и распознавание
    # по известным окончаниям, но не произвольные догадки анализатора.
    return _morphology_has_analyzer(
        word,
        frozenset({"DictionaryAnalyzer", "KnownSuffixAnalyzer"}),
    )


def repair_split_words(text):
    """
    Восстанавливает части слов, разделённые пробелом при извлечении PDF.

    Объединение выполняется только если:
    - одна из частей короткая (1–3 буквы), то есть похожа на фрагмент слова;
    - обе части по отдельности не являются самостоятельными словами;
      исключение — короткий фрагмент, который вместе с соседней частью
      образует подтверждённую морфологическим словарём форму;
    - объединённая форма распознаётся русским морфологическим анализатором.

    Обычные сочетания вроде «в процессе», «с пациентом», «по показаниям»
    сохраняются.
    """
    if not text:
        return text

    token_pair = re.compile(
        r"(?<![А-Яа-яЁё])"
        r"(?P<left>[А-Яа-яЁё]+)"
        r"(?P<separator>[ \t]+)"
        r"(?P<right>[А-Яа-яЁё]+)"
        r"(?![А-Яа-яЁё])",
        re.IGNORECASE,
    )

    expanded_prepositions = {
        ("в", "о"): "во",
        ("с", "о"): "со",
        ("к", "о"): "ко",
        ("из", "о"): "изо",
        ("от", "о"): "ото",
        ("под", "о"): "подо",
        ("над", "о"): "надо",
    }

    def replace_pair(match):
        left = match.group("left")
        right = match.group("right")
        left_lower = left.lower()
        right_lower = right.lower()

        expanded = expanded_prepositions.get((left_lower, right_lower))
        if expanded:
            if left.isupper() and right.isupper():
                return expanded.upper()
            if left[:1].isupper():
                return expanded.capitalize()
            return expanded

        # Не рассматриваем два длинных самостоятельных токена:
        # это резко снижает риск склеивания соседних слов.
        if len(left) > 3 and len(right) > 3:
            return match.group(0)

        # Если обе части являются словами, сохраняем исходный пробел.
        if _is_dictionary_word(left_lower) and _is_dictionary_word(right_lower):
            return match.group(0)

        joined = left + right
        if _is_valid_joined_word(joined.lower()):
            return joined

        return match.group(0)

    previous = None
    current = text

    # Повторные проходы нужны для последовательностей из нескольких
    # фрагментов, например «п о краю» -> «по краю».
    for _ in range(3):
        if current == previous:
            break
        previous = current
        current = token_pair.sub(replace_pair, current)

    return current
