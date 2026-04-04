from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from base64 import b64encode
from typing import Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
import httpx
from pydantic import BaseModel, Field

load_dotenv(override=True)


CATEGORY_NAMES = [
    "ЖКХ",
    "Дороги и транспорт",
    "Здравоохранение",
    "Образование",
    "Экология и ЧС",
    "Экономика и промышленность",
    "Социальная защита и выплаты",
    "Благоустройство и городская среда",
    "Безопасность и правопорядок",
    "Госуслуги и обращения граждан",
    "Жилье и строительство",
]

DEFAULT_GIGACHAT_MODEL = "GigaChat-2"
DEFAULT_GIGACHAT_BASE_URL = "https://gigachat.devices.sberbank.ru/api/v1"
DEFAULT_GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
DEFAULT_GIGACHAT_SCOPE = "GIGACHAT_API_PERS"
DEFAULT_PROVIDER = "llm"
TOKEN_EXPIRY_BUFFER_SECONDS = 60

_gigachat_token_cache: Dict[str, object] = {"access_token": None, "expires_at": 0}
_gigachat_token_lock = asyncio.Lock()


class ClassifyCategoryRequest(BaseModel):
    text: str = Field(..., description="Текст сообщения или новости")
    channel_name: str = Field("", description="Название канала или группы")
    channel_description: str = Field("", description="Описание канала или группы")


class ClassifyCategoryResponse(BaseModel):
    category: str
    matched_keywords: Dict[str, List[str]]
    provider: str = "gigachat"
    model: Optional[str] = None


class BatchClassifyCategoryRequest(BaseModel):
    items: List[ClassifyCategoryRequest]


class ExtractLocationResponse(BaseModel):
    region: Optional[str]
    city: Optional[str]
    district: Optional[str]
    address: Optional[str]
    provider: str = "gigachat"
    model: Optional[str] = None


class ExtractKeyWordsRequest(BaseModel):
    text: str = Field(..., description="Текст сообщения или новости")


class ExtractKeyWordsResponse(BaseModel):
    key_words: List[str]
    provider: str = "gigachat"
    model: Optional[str] = None


def normalize_text(value: str) -> str:
    return " ".join(value.lower().replace("ё", "е").split())


def get_provider(_: Optional[str] = None) -> str:
    return os.getenv("REGION_PULSE_PROVIDER", DEFAULT_PROVIDER)


def get_gigachat_model() -> str:
    return os.getenv("GIGACHAT_MODEL", DEFAULT_GIGACHAT_MODEL)


def get_gigachat_base_url() -> str:
    return os.getenv("GIGACHAT_BASE_URL", DEFAULT_GIGACHAT_BASE_URL)


def get_gigachat_auth_url() -> str:
    return os.getenv("GIGACHAT_AUTH_URL", DEFAULT_GIGACHAT_AUTH_URL)


def get_gigachat_scope() -> str:
    return os.getenv("GIGACHAT_SCOPE", DEFAULT_GIGACHAT_SCOPE)


def get_gigachat_timeout() -> float:
    return float(os.getenv("GIGACHAT_TIMEOUT", "60"))


def get_gigachat_verify_ssl_certs() -> bool:
    return os.getenv("GIGACHAT_VERIFY_SSL_CERTS", "false").lower() == "true"


def get_gigachat_credentials() -> Optional[str]:
    credentials = os.getenv("GIGACHAT_CREDENTIALS")
    if credentials:
        return credentials

    client_id = os.getenv("GIGACHAT_CLIENT_ID") or os.getenv("client_id")
    client_secret = os.getenv("GIGACHAT_CLIENT_SECRET") or os.getenv("client_secret")
    if client_id and client_secret:
        raw_credentials = f"{client_id}:{client_secret}"
        return b64encode(raw_credentials.encode("utf-8")).decode("ascii")

    return None


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


async def get_gigachat_access_token() -> str:
    access_token = os.getenv("GIGACHAT_ACCESS_TOKEN") or os.getenv("access_token")
    credentials = get_gigachat_credentials()
    user = os.getenv("GIGACHAT_USER")
    password = os.getenv("GIGACHAT_PASSWORD")

    if not any([access_token, credentials, user and password]):
        raise HTTPException(
            status_code=503,
            detail=(
                "GigaChat credentials are not configured. "
                "Set GIGACHAT_CREDENTIALS, GIGACHAT_CLIENT_ID/GIGACHAT_CLIENT_SECRET, "
                "GIGACHAT_ACCESS_TOKEN, access_token, or GIGACHAT_USER/GIGACHAT_PASSWORD."
            ),
        )

    if access_token:
        return access_token

    cached_token = _gigachat_token_cache.get("access_token")
    cached_expires_at = int(_gigachat_token_cache.get("expires_at", 0))
    if cached_token and cached_expires_at > int(time.time()) + TOKEN_EXPIRY_BUFFER_SECONDS:
        return str(cached_token)

    if user and password:
        raise HTTPException(
            status_code=503,
            detail="GigaChat username/password auth is not implemented in this service",
        )

    async with _gigachat_token_lock:
        cached_token = _gigachat_token_cache.get("access_token")
        cached_expires_at = int(_gigachat_token_cache.get("expires_at", 0))
        if cached_token and cached_expires_at > int(time.time()) + TOKEN_EXPIRY_BUFFER_SECONDS:
            return str(cached_token)

        try:
            async with httpx.AsyncClient(
                verify=get_gigachat_verify_ssl_certs(),
                timeout=get_gigachat_timeout(),
            ) as client:
                response = await client.post(
                    get_gigachat_auth_url(),
                    headers={
                        "Authorization": f"Basic {credentials}",
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json",
                        "RqUID": str(uuid.uuid4()),
                    },
                    data={"scope": get_gigachat_scope()},
                )
        except httpx.ConnectError as error:
            raise HTTPException(
                status_code=502,
                detail=(
                    "GigaChat auth connection error. "
                    "Check internet access, DNS/VPN availability, and auth host reachability. "
                    f"Original error: {error}"
                ),
            ) from error
        except httpx.HTTPError as error:
            raise HTTPException(
                status_code=502,
                detail=f"GigaChat auth HTTP error: {error}",
            ) from error

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"GigaChat auth error: {response.text}",
            )

        body = response.json()
        token = body.get("access_token")
        expires_at = int(body.get("expires_at", 0))
        if not token:
            raise HTTPException(
                status_code=502,
                detail="GigaChat auth response does not contain access_token",
            )

        _gigachat_token_cache["access_token"] = token
        _gigachat_token_cache["expires_at"] = expires_at
        return str(token)


async def call_gigachat(messages: List[Dict[str, str]]) -> Dict[str, object]:
    model = get_gigachat_model()
    access_token = await get_gigachat_access_token()

    try:
        async with httpx.AsyncClient(
            verify=get_gigachat_verify_ssl_certs(),
            timeout=get_gigachat_timeout(),
        ) as client:
            response = await client.post(
                f"{get_gigachat_base_url().rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0,
                },
            )
    except httpx.ConnectError as error:
        raise HTTPException(
            status_code=502,
            detail=(
                "GigaChat connection error. "
                "Check internet access, DNS/VPN availability, and GigaChat host reachability. "
                f"Original error: {error}"
            ),
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=502,
            detail=f"GigaChat HTTP error: {error}",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Unexpected GigaChat client error: {error}",
        ) from error

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"GigaChat error: {response.text}",
        )

    body = response.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise HTTPException(
            status_code=502,
            detail="GigaChat returned an unexpected response format",
        ) from error

    try:
        payload = parse_json_from_llm(content)
    except ValueError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    payload["provider"] = "gigachat"
    payload["model"] = body.get("model", model)
    return payload


async def classify_category_llm(
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
                "Верни объект с полями category и matched_keywords. "
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
    payload = await call_gigachat(messages)

    category = payload.get("category")
    if category not in CATEGORY_NAMES and category != "Не определено":
        raise HTTPException(status_code=502, detail="LLM returned invalid category")

    matched_keywords = payload.get("matched_keywords")

    if not isinstance(matched_keywords, dict):
        matched_keywords = {name: [] for name in CATEGORY_NAMES}
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
        "matched_keywords": normalized_keywords,
        "provider": payload.get("provider", "gigachat"),
        "model": payload.get("model", get_gigachat_model()),
    }


async def extract_location_llm(
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
    payload = await call_gigachat(messages)

    return {
        "region": payload.get("region"),
        "city": payload.get("city"),
        "district": payload.get("district"),
        "address": payload.get("address"),
        "provider": payload.get("provider", "gigachat"),
        "model": payload.get("model", get_gigachat_model()),
    }


async def extract_key_words_llm(text: str) -> Dict[str, object]:
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
    payload = await call_gigachat(messages)
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
        "provider": payload.get("provider", "gigachat"),
        "model": payload.get("model", get_gigachat_model()),
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
    return {"provider": "llm", "model": get_gigachat_model()}


@app.post("/api/extract-key-words", response_model=ExtractKeyWordsResponse)
async def extract_key_words_endpoint(payload: ExtractKeyWordsRequest) -> Dict[str, object]:
    return await extract_key_words_llm(payload.text)


@app.post("/api/classify-category", response_model=ClassifyCategoryResponse)
async def classify_category_endpoint(payload: ClassifyCategoryRequest) -> Dict[str, object]:
    return await classify_category_llm(
        text=payload.text,
        channel_name=payload.channel_name,
        channel_description=payload.channel_description,
    )


@app.post("/api/classify-category/batch")
async def classify_category_batch(
    payload: BatchClassifyCategoryRequest,
) -> Dict[str, List[Dict[str, object]]]:
    return {
        "items": [
            await classify_category_llm(
                text=item.text,
                channel_name=item.channel_name,
                channel_description=item.channel_description,
            )
            for item in payload.items
        ]
    }


@app.post("/api/extract-location", response_model=ExtractLocationResponse)
async def extract_location_endpoint(
    payload: ClassifyCategoryRequest,
) -> Dict[str, Optional[str]]:
    return await extract_location_llm(
        text=payload.text,
        channel_name=payload.channel_name,
        channel_description=payload.channel_description,
    )


@app.post("/api/extract-location/batch")
async def extract_location_batch(
    payload: BatchClassifyCategoryRequest,
) -> Dict[str, List[Dict[str, Optional[str]]]]:
    return {
        "items": [
            await extract_location_llm(
                text=item.text,
                channel_name=item.channel_name,
                channel_description=item.channel_description,
            )
            for item in payload.items
        ]
    }
