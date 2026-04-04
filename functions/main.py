from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


load_dotenv(override=True)


CATEGORY_NAMES = [
    "ЖКХ",
    "Дороги и транспорт",
    "Здравоохранение",
    "Образование",
    "Экология и ЧС",
    "Экономика и промышленность",
]

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "qwen/qwen3.6-plus"
DEFAULT_PROVIDER = "llm"


class ClassifyCategoryRequest(BaseModel):
    text: str = Field(..., description="Текст сообщения или новости")
    channel_name: str = Field("", description="Название канала или группы")
    channel_description: str = Field("", description="Описание канала или группы")


class ClassifyCategoryResponse(BaseModel):
    category: str
    scores: Dict[str, int]
    matched_keywords: Dict[str, List[str]]
    provider: str = "openrouter"
    model: Optional[str] = None


class BatchClassifyCategoryRequest(BaseModel):
    items: List[ClassifyCategoryRequest]


class ExtractLocationResponse(BaseModel):
    region: Optional[str]
    city: Optional[str]
    district: Optional[str]
    address: Optional[str]
    provider: str = "openrouter"
    model: Optional[str] = None


class ExtractKeyWordsRequest(BaseModel):
    text: str = Field(..., description="Текст сообщения или новости")


class ExtractKeyWordsResponse(BaseModel):
    key_words: List[str]
    provider: str = "openrouter"
    model: Optional[str] = None


def normalize_text(value: str) -> str:
    return " ".join(value.lower().replace("ё", "е").split())


def get_provider(_: Optional[str] = None) -> str:
    return os.getenv("REGION_PULSE_PROVIDER", DEFAULT_PROVIDER)


def get_openrouter_model() -> str:
    return os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)


def parse_json_from_llm(content: str) -> Dict[str, object]:
    stripped = content.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, re.DOTALL)
    if fenced_match is not None:
        return json.loads(fenced_match.group(1))

    object_match = re.search(r"(\{.*\})", stripped, re.DOTALL)
    if object_match is not None:
        return json.loads(object_match.group(1))

    raise ValueError("LLM response is not valid JSON")


def call_openrouter(messages: List[Dict[str, str]]) -> Dict[str, object]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENROUTER_API_KEY is not configured",
        )

    model = get_openrouter_model()
    app_url = os.getenv("OPENROUTER_APP_URL", "http://localhost:8000")
    app_name = os.getenv("OPENROUTER_APP_NAME", "region-pulse")

    response = httpx.post(
        OPENROUTER_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": app_url,
            "X-Title": app_name,
        },
        json={
            "model": model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        },
        timeout=60.0,
    )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"OpenRouter error: {response.text}",
        )

    body = response.json()
    content = body["choices"][0]["message"]["content"]

    try:
        payload = parse_json_from_llm(content)
    except ValueError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    payload["provider"] = "openrouter"
    payload["model"] = body.get("model", model)
    return payload


def classify_category_llm(
    text: str, channel_name: str = "", channel_description: str = ""
) -> Dict[str, object]:
    categories = ", ".join(CATEGORY_NAMES)
    messages = [
        {
            "role": "system",
            "content": (
                "Ты сервис категоризации региональных сообщений. "
                "Верни только JSON без пояснений. "
                "Определи ровно одну категорию из фиксированного списка. "
                f"Список категорий: {categories}. "
                "Если категория не подходит, верни 'Не определено'. "
                "Верни объект с полями category, scores, matched_keywords. "
                "Для scores верни все категории из списка с целыми числами от 0 до 100. "
                "Для matched_keywords верни объект, где ключи это категории, а значения это массивы строк."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "text": text,
                    "channel_name": channel_name,
                    "channel_description": channel_description,
                },
                ensure_ascii=False,
            ),
        },
    ]
    payload = call_openrouter(messages)

    category = payload.get("category")
    if category not in CATEGORY_NAMES and category != "Не определено":
        raise HTTPException(status_code=502, detail="LLM returned invalid category")

    scores = payload.get("scores")
    matched_keywords = payload.get("matched_keywords")

    if not isinstance(scores, dict):
        scores = {name: 0 for name in CATEGORY_NAMES}

    if not isinstance(matched_keywords, dict):
        matched_keywords = {name: [] for name in CATEGORY_NAMES}

    normalized_scores = {
        name: int(scores.get(name, 0)) if str(scores.get(name, 0)).lstrip("-").isdigit() else 0
        for name in CATEGORY_NAMES
    }
    normalized_keywords = {
        name: [
            str(keyword).strip()
            for keyword in matched_keywords.get(name, [])
            if isinstance(keyword, str) and str(keyword).strip()
        ]
        if isinstance(matched_keywords.get(name, []), list)
        else []
        for name in CATEGORY_NAMES
    }

    return {
        "category": category,
        "scores": normalized_scores,
        "matched_keywords": normalized_keywords,
        "provider": payload.get("provider", "openrouter"),
        "model": payload.get("model", get_openrouter_model()),
    }


def extract_location_llm(
    text: str, channel_name: str = "", channel_description: str = ""
) -> Dict[str, Optional[str]]:
    messages = [
        {
            "role": "system",
            "content": (
                "Ты сервис извлечения географии из региональных сообщений. "
                "Верни только JSON без пояснений. "
                "Нужно извлечь region, city, district, address. "
                "Если поле не найдено, верни null. "
                "Если в тексте встречаются Ростов, Ростов-на-Дону, Аксай, Батайск, Таганрог, "
                "Новочеркасск, Шахты, Волгодонск или районы Ростовской области, нормализуй значения. "
                'Формат ответа: {"region":null,"city":null,"district":null,"address":null}'
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "text": text,
                    "channel_name": channel_name,
                    "channel_description": channel_description,
                },
                ensure_ascii=False,
            ),
        },
    ]
    payload = call_openrouter(messages)

    return {
        "region": payload.get("region"),
        "city": payload.get("city"),
        "district": payload.get("district"),
        "address": payload.get("address"),
        "provider": payload.get("provider", "openrouter"),
        "model": payload.get("model", get_openrouter_model()),
    }


def extract_key_words_llm(text: str) -> Dict[str, object]:
    messages = [
        {
            "role": "system",
            "content": (
                "Ты сервис извлечения ключевых слов из коротких региональных сообщений. "
                "Верни только JSON без пояснений. "
                "Нужно вернуть массив key_words из 2-5 коротких ключевых слов или фраз. "
                "Выделяй только самые важные сущности проблемы или события. "
                "Не включай служебные слова, даты, вводные конструкции и случайный шум. "
                'Формат ответа: {"key_words":["...", "..."]}'
            ),
        },
        {
            "role": "user",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
    ]
    payload = call_openrouter(messages)
    key_words = payload.get("key_words")

    if not isinstance(key_words, list):
        raise HTTPException(status_code=502, detail="LLM returned invalid key_words")

    normalized_key_words = [
        str(keyword).strip()
        for keyword in key_words
        if isinstance(keyword, str) and str(keyword).strip()
    ]

    return {
        "key_words": normalized_key_words[:5],
        "provider": payload.get("provider", "openrouter"),
        "model": payload.get("model", get_openrouter_model()),
    }


app = FastAPI(
    title="Region Pulse Backend",
    description="API для анализа региональных сообщений через LLM",
    version="0.1.0",
)


@app.get("/")
def root() -> Dict[str, str]:
    return {
        "message": "Region Pulse API is running",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health")
def healthcheck() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/categories")
def get_categories() -> Dict[str, List[str]]:
    return {"categories": CATEGORY_NAMES}


@app.get("/api/provider")
def get_provider_info() -> Dict[str, Optional[str]]:
    return {"provider": "llm", "model": get_openrouter_model()}


@app.post("/api/extract-key-words", response_model=ExtractKeyWordsResponse)
def extract_key_words_endpoint(payload: ExtractKeyWordsRequest) -> Dict[str, object]:
    return extract_key_words_llm(payload.text)


@app.post("/api/classify-category", response_model=ClassifyCategoryResponse)
def classify_category_endpoint(payload: ClassifyCategoryRequest) -> Dict[str, object]:
    return classify_category_llm(
        text=payload.text,
        channel_name=payload.channel_name,
        channel_description=payload.channel_description,
    )


@app.post("/api/classify-category/batch")
def classify_category_batch(
    payload: BatchClassifyCategoryRequest,
) -> Dict[str, List[Dict[str, object]]]:
    return {
        "items": [
            classify_category_llm(
                text=item.text,
                channel_name=item.channel_name,
                channel_description=item.channel_description,
            )
            for item in payload.items
        ]
    }


@app.post("/api/extract-location", response_model=ExtractLocationResponse)
def extract_location_endpoint(
    payload: ClassifyCategoryRequest,
) -> Dict[str, Optional[str]]:
    return extract_location_llm(
        text=payload.text,
        channel_name=payload.channel_name,
        channel_description=payload.channel_description,
    )


@app.post("/api/extract-location/batch")
def extract_location_batch(
    payload: BatchClassifyCategoryRequest,
) -> Dict[str, List[Dict[str, Optional[str]]]]:
    return {
        "items": [
            extract_location_llm(
                text=item.text,
                channel_name=item.channel_name,
                channel_description=item.channel_description,
            )
            for item in payload.items
        ]
    }
