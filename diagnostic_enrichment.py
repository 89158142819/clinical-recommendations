import re


METHOD = "diagnostic_enrichment_v1"

POSITIVE_RE = re.compile(
    r"(?i)(?<![а-яё])(?:рекомендуется|рекомендовано|рекомендована|"
    r"рекомендованы|рекомендовать|рекомендуют|целесообразно|"
    r"показано|показан|показана|показаны|следует|необходимо)(?![а-яё])"
)
NEGATIVE_RE = re.compile(
    r"(?i)(?<![а-яё])(?:не\s+рекомендуется|не\s+рекомендовано|"
    r"не\s+рекомендована|не\s+рекомендованы|нецелесообразно|"
    r"противопоказано|противопоказан|противопоказана|"
    r"нет\s+необходимости|не\s+имеет\s+смысла|"
    r"рекомендуется\s+не\s+выполнять|следует\s+воздержаться|"
    r"воздержаться|отказаться)(?![а-яё])"
)
ACTION_RE = re.compile(
    r"(?i)\b(?:выполнение|проведение|определение|исследование|"
    r"выполнять|выполнить|проводить|провести|определять|определить|назначение|контроль|"
    r"оценка|измерение|взятие|сдача)\b"
)
CONDITION_RE = re.compile(
    r"(?i)\b(?:всем\s+пациентам|всем\s+детям|пациентам|"
    r"детям|у\s+пациентов|у\s+детей|при\s+наличии|при\s+подозрении|"
    r"при\s+необходимости|при\s+отсутствии|после|до|перед|"
    r"во\s+время|в\s+процессе|на\s+фоне|каждые|ежегодно|"
    r"для\s+оценки|для\s+определения|для\s+уточнения|"
    r"с\s+целью|с\s+цели|если)\b"
)
PURPOSE_RE = re.compile(
    r"(?i)\b(?:с\s+целью|с\s+цели|для\s+оценки|для\s+определения|"
    r"для\s+уточнения|для\s+выявления|для\s+диагностики|"
    r"для\s+подтверждения|для\s+исключения)\b"
)
LEVEL_RE = re.compile(
    r"(?i)\s*(?:Уровень\s+убедительности\s+рекомендаций?|"
    r"УДД\s*\d+\s*[;,]?\s*УУР|УУР\s*[A-ZА-ЯЁ0-9])[\s\S]*$"
)
REFERENCE_RE = re.compile(r"\s*(?:\[[\d\s,;.\-–—]+\]|\(\s*\[[\d\s,;.\-–—]+\]\s*\))")
SPACE_RE = re.compile(r"\s+")


def _clean(value):
    value = str(value or "").replace("\u00a0", " ")
    value = SPACE_RE.sub(" ", value).strip()
    value = LEVEL_RE.sub("", value).strip()
    value = REFERENCE_RE.sub("", value).strip()
    return value.strip(" \t\r\n;,:—–-.")


def _split_clauses(value):
    text = _clean(value)
    if not text:
        return []

    # Разделяем только там, где после точки с запятой или конца предложения
    # начинается новая самостоятельная рекомендательная формулировка.
    starts = list(re.finditer(
        r"(?i)(?:(?<=[;])\s+|(?<=[.!?])\s+)"
        r"(?=(?:(?:не\s+)?рекоменду|нецелесообраз|противопоказ|"
        r"целесообраз|показан|следует|необходимо|нет\s+необходимости|"
        r"воздержаться|отказаться))",
        text
    ))
    if not starts:
        return [text]

    result = []
    cursor = 0
    for match in starts:
        part = _clean(text[cursor:match.start()])
        if part:
            result.append(part)
        cursor = match.end()
    tail = _clean(text[cursor:])
    if tail:
        result.append(tail)

    # Разделяем исходный блок только при наличии обеих полярностей.
    # Иначе точки с запятой внутри перечней и условий не должны создавать
    # дополнительные карточки.
    verdicts = {_verdict(part) for part in result}
    if "recommended" not in verdicts or "not_recommended" not in verdicts:
        return [text]

    # Не дробим один блок на несколько карточек, если полярность
    # соседних рекомендаций совпадает. Разделяем только разные вердикты.
    merged = []
    for part in result:
        if merged and _verdict(merged[-1]) == _verdict(part):
            merged[-1] = _clean(merged[-1] + "; " + part)
        else:
            merged.append(part)

    return merged or [text]


def _verdict(value):
    negative = list(NEGATIVE_RE.finditer(value))
    positive_text = NEGATIVE_RE.sub(" ", value)
    positive = list(POSITIVE_RE.finditer(positive_text))
    if negative and not positive:
        return "not_recommended"
    if positive and not negative:
        return "recommended"
    if negative and positive:
        return "mixed"
    return "unknown"


def _find_action_start(value):
    match = ACTION_RE.search(value)
    if match:
        return match.start()
    return None


def _extract_title_and_conditions(value):
    text = _clean(value)
    if not text:
        return "", "", ""

    purpose = ""
    purpose_match = PURPOSE_RE.search(text)
    if purpose_match:
        purpose = _clean(text[purpose_match.start():])
        text_before_purpose = text[:purpose_match.start()].strip()
    else:
        text_before_purpose = text

    recommendation_matches = list(POSITIVE_RE.finditer(text_before_purpose))
    negative_matches = list(NEGATIVE_RE.finditer(text_before_purpose))
    matches = recommendation_matches + negative_matches
    if matches:
        verb = min(matches, key=lambda item: item.start())
        prefix = text_before_purpose[:verb.start()].strip(" ,;:")
        tail = text_before_purpose[verb.end():].strip(" ,;:")
    else:
        prefix = ""
        tail = text_before_purpose

    action_start = _find_action_start(tail)
    if action_start is not None:
        conditions_after_verb = tail[:action_start].strip(" ,;:")
        title_source = tail[action_start:]
        action = ACTION_RE.match(title_source)
        if action:
            title_source = title_source[action.end():].strip(" ,;:")
    else:
        conditions_after_verb = ""
        title_source = tail

    # Название заканчивается перед условием назначения.
    condition_match = CONDITION_RE.search(title_source)
    if condition_match:
        title = title_source[:condition_match.start()].strip(" ,;:")
        conditions_after_title = title_source[condition_match.start():].strip(" ,;:")
    else:
        title = title_source.strip(" ,;:")
        conditions_after_title = ""

    # Для конструкции «следующих исследований: ...» сохраняем перечень
    # как единый исходный набор названий, не обрезая его по первому пункту.
    title = re.sub(
        r"(?i)^(?:следующих\s+)?(?:лабораторных\s+)?(?:диагностических\s+)?исследований\s*:\s*",
        "",
        title
    ).strip()
    title = _clean(title)

    conditions = _clean(" ".join(
        part for part in (prefix, conditions_after_verb, conditions_after_title)
        if part
    ))
    return title, conditions, purpose


def _category_from_text(category, value):
    if category in ("laboratory", "instrumental", "other"):
        return category

    text = value.lower()
    if re.search(r"\b(?:узи|экг|кт|мрт|рентген|сонограф|эндоскоп|спирометр|томограф)\w*", text):
        return "instrumental"
    if re.search(r"\b(?:анализ|уровень|антител|крови|мочи|сыворотк|гормон|коагулограмм)\w*", text):
        return "laboratory"
    return "other"


def _normalise_title(value):
    value = _clean(value).lower().replace("ё", "е")
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"[^а-яa-z0-9]+", " ", value)
    return SPACE_RE.sub(" ", value).strip()


def enrich_diagnostic_summary(summary):
    if not isinstance(summary, dict):
        return summary

    category_keys = ("laboratory", "instrumental", "other")
    enriched = {key: [] for key in category_keys}
    seen = {}

    for category in category_keys:
        items = summary.get(category, [])
        if not isinstance(items, list):
            continue

        for original in items:
            if not isinstance(original, dict):
                continue

            source_text = str(original.get("text") or original.get("source_excerpt") or "").strip()
            if not source_text:
                continue

            clauses = _split_clauses(source_text)
            if not clauses:
                clauses = [source_text]

            for clause in clauses:
                verdict = _verdict(clause)
                title, conditions, purpose = _extract_title_and_conditions(clause)
                resolved_category = _category_from_text(category, title or clause)

                item = dict(original)
                item.update({
                    "category": resolved_category,
                    "verdict": verdict,
                    "study_title": title,
                    "conditions": conditions,
                    "purpose": purpose,
                    "source_text": source_text,
                    "recommendation_text": clause,
                    "text": source_text,
                    "extraction_method": METHOD,
                })

                key = (
                    resolved_category,
                    verdict,
                    _normalise_title(title) or _normalise_title(clause),
                )
                if key in seen:
                    existing = seen[key]
                    old_conditions = existing.get("conditions", "")
                    if conditions and conditions not in old_conditions:
                        existing["conditions"] = _clean(
                            "; ".join(part for part in (old_conditions, conditions) if part)
                        )
                    old_purpose = existing.get("purpose", "")
                    if purpose and purpose not in old_purpose:
                        existing["purpose"] = _clean(
                            "; ".join(part for part in (old_purpose, purpose) if part)
                        )
                    sources = existing.setdefault("source_texts", [])
                    if source_text not in sources:
                        sources.append(source_text)
                    continue

                item["source_texts"] = [source_text]
                seen[key] = item
                enriched[resolved_category].append(item)

    result = dict(summary)
    result.update(enriched)
    result["method"] = "recommendation_blocks_v7"
    result["enrichment_method"] = METHOD
    result["counts"] = {key: len(enriched[key]) for key in category_keys}
    all_items = [item for key in category_keys for item in enriched[key]]
    result["status"] = (
        "review_required"
        if any(item.get("boundary_status") in ("review_required", "incomplete")
               or item.get("verdict") == "unknown"
               for item in all_items)
        else "extracted" if all_items else "not_extracted"
    )
    return result
