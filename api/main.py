import json
import math
import os
import re
import time
from collections import defaultdict, deque
from pathlib import Path
from threading import Lock

import snowballstemmer
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "search_index.json"
MODEL = os.getenv("OPENAI_MODEL", "gpt-6-luna")
MAX_QUESTION_LENGTH = 600
MAX_RESULTS = 8
MAX_REQUESTS_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "8"))

SECTION_KEYS = {
    "diagnostics", "complaints_anamnesis", "physical_examination",
    "laboratory_diagnostics", "instrumental_diagnostics", "other_diagnostics",
}
TOKEN_RE = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)
STOP_WORDS = set("""
и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по
только ее мне было вот от меня еще нет о из ему теперь когда даже ну вдруг ли
если уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя
ничего ей может они тут где есть надо для при при этом какие какая какой
диагностика диагностике диагностику исследование исследования исследований
метод методы раздел рекомендация рекомендации клинический клинические
""".split())
stemmer = snowballstemmer.stemmer("russian")

app = FastAPI(title="Clinical Recommendations Assistant", version="1.0.0")
origins = [x.strip() for x in os.getenv(
    "ALLOWED_ORIGINS",
    "https://89158142819.github.io",
).split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

_index = None
_client = None
_rate_lock = Lock()
_rate_events = defaultdict(deque)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=MAX_QUESTION_LENGTH)
    age: str | None = Field(default=None, max_length=30)


def tokenize(text):
    words = [w.lower().replace("ё", "е") for w in TOKEN_RE.findall(str(text or ""))]
    words = [w for w in words if len(w) > 2 and w not in STOP_WORDS]
    return stemmer.stemWords(words)


def load_index():
    global _index
    if _index is None:
        if not INDEX_FILE.exists():
            raise RuntimeError("Поисковый индекс ещё не собран. Проверьте команду сборки на хостинге.")
        _index = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    return _index


def get_client():
    global _client
    if _client is None:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("На сервере не задан OPENAI_API_KEY.")
        _client = OpenAI()
    return _client


def check_rate_limit(request):
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    now = time.time()
    with _rate_lock:
        events = _rate_events[client_ip]
        while events and now - events[0] > 60:
            events.popleft()
        if len(events) >= MAX_REQUESTS_PER_MINUTE:
            raise HTTPException(status_code=429, detail="Слишком много запросов. Попробуйте через минуту.")
        events.append(now)


def search_chunks(question, age=None):
    index = load_index()
    query_tokens = tokenize(question)
    if not query_tokens:
        return []

    chunks = index["chunks"]
    n = len(chunks)
    document_frequency = defaultdict(int)
    for chunk in chunks:
        for token in set(chunk.get("tokens", [])):
            document_frequency[token] += 1

    average_length = sum(len(c.get("tokens", [])) for c in chunks) / max(n, 1)
    query_terms = set(query_tokens)
    scored = []

    for chunk in chunks:
        if age and age.lower() not in chunk.get("age_category", "").lower():
            continue
        tokens = chunk.get("tokens", [])
        if not tokens:
            continue
        frequencies = defaultdict(int)
        for token in tokens:
            frequencies[token] += 1
        score = 0.0
        length_norm = len(tokens) / max(average_length, 1)
        for term in query_terms:
            tf = frequencies.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (n - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
            score += idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * length_norm))
            if term in chunk.get("title_tokens", []):
                score += idf * 2.8
        title = chunk.get("title", "").lower().replace("ё", "е")
        raw_query = question.lower().replace("ё", "е")
        if raw_query and raw_query in title:
            score += 5.0
        if chunk.get("application_status", "").strip().lower() == "применяется":
            score += 0.35
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected = []
    section_counts = defaultdict(int)
    doc_counts = defaultdict(int)
    for score, chunk in scored:
        key = (chunk["id"], chunk["section_key"])
        if section_counts[key] >= 2 or doc_counts[chunk["id"]] >= 4:
            continue
        selected.append((score, chunk))
        section_counts[key] += 1
        doc_counts[chunk["id"]] += 1
        if len(selected) >= MAX_RESULTS:
            break
    return selected


def generate_answer(question, matches):
    if not matches:
        return (
            "В доступной поисковой базе не найдено фрагментов, которые можно уверенно "
            "связать с указанным заболеванием. Попробуйте уточнить название заболевания "
            "или проверить его по каталогу клинических рекомендаций."
        )

    source_blocks = []
    sources = []
    for number, (score, chunk) in enumerate(matches, start=1):
        source_blocks.append(
            f"[ИСТОЧНИК {number}]\n"
            f"Документ: {chunk['title']} (ID {chunk['id']})\n"
            f"Раздел: {chunk['section_label']}\n"
            f"МКБ-10: {chunk.get('icd10') or 'не указан'}\n"
            f"Возраст: {chunk.get('age_category') or 'не указан'}\n"
            f"Статус применения: {chunk.get('application_status') or 'не указан'}\n"
            f"Текст первоисточника:\n{chunk['text']}"
        )
        sources.append({
            "number": number,
            "id": chunk["id"],
            "title": chunk["title"],
            "section": chunk["section_label"],
            "source_url": chunk["source_url"],
            "age_category": chunk.get("age_category", ""),
            "icd10": chunk.get("icd10", ""),
        })

    instructions = """
Ты — справочный помощник по диагностическим разделам официальных клинических рекомендаций Минздрава России.
Отвечай только на основании предоставленных ниже фрагментов первоисточников.
Не используй собственные медицинские знания для добавления исследований, показаний, противопоказаний, сроков или интерпретаций, которых нет в цитируемых фрагментах.
Не ставь диагноз, не назначай лечение и не давай индивидуальных медицинских рекомендаций.
Структурируй ответ по разделам: общие положения; жалобы и анамнез; физикальное обследование; лабораторная диагностика; инструментальная диагностика; иные исследования — показывай только те разделы, для которых есть содержательные сведения.
Различай рекомендованные исследования и исследования, которые выполняются только по показаниям или для дифференциальной диагностики. Не называй исследование обязательным, если первоисточник этого не утверждает. Учитывай статус применения рекомендации: если он не указан или отличается от «Применяется», обязательно предупреди пользователя и не представляй такой документ как действующую рекомендацию.
После каждого существенного утверждения ставь ссылку вида [1] или [2], соответствующую номеру фрагмента.
Если сведения в источниках противоречат друг другу, прямо сообщи об этом и укажи оба источника.
Если релевантных сведений недостаточно, прямо скажи, что в найденных фрагментах клинических рекомендаций ответа нет. Не заполняй пробелы догадками.
В конце добавь короткое примечание: это справочная выжимка, актуальность и применимость проверяют по полной версии официальной рекомендации.
Пиши по-русски, понятно и без избыточных вступлений.
"""
    prompt = f"Вопрос пользователя: {question}\n\nФрагменты официальных клинических рекомендаций:\n\n" + "\n\n".join(source_blocks)
    response = get_client().responses.create(
        model=MODEL,
        instructions=instructions,
        input=prompt,
        max_output_tokens=1600,
        store=False,
    )
    answer = (response.output_text or "").strip()
    if not answer:
        raise RuntimeError("Модель не вернула текст ответа.")
    return answer, sources


@app.get("/")
def root():
    return {"service": "clinical-recommendations-api", "status": "ok", "docs": "/docs"}


@app.get("/health")
def health():
    try:
        index = load_index()
        return {
            "status": "ok",
            "indexed_documents": index.get("indexed_documents", 0),
            "indexed_chunks": index.get("indexed_chunks", 0),
            "generated_at": index.get("generated_at"),
            "model": MODEL,
        }
    except Exception as error:
        raise HTTPException(status_code=503, detail=str(error))


@app.post("/api/answer")
def answer(payload: AskRequest, request: Request):
    check_rate_limit(request)
    question = payload.question.strip()
    if len(question) < 3:
        raise HTTPException(status_code=422, detail="Введите более подробный вопрос.")
    try:
        matches = search_chunks(question, payload.age)
        generated = generate_answer(question, matches)
        if isinstance(generated, tuple):
            answer_text, sources = generated
        else:
            answer_text, sources = generated, []
        return {
            "answer": answer_text,
            "sources": sources,
            "model": MODEL,
            "retrieved_fragments": len(matches),
        }
    except HTTPException:
        raise
    except Exception:
        # Не раскрываем пользователю внутренние детали и секреты сервера.
        raise HTTPException(
            status_code=503,
            detail="Не удалось сформировать ответ. Проверьте доступность сервера и настройки API.",
        )
