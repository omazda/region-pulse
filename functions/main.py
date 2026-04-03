from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field


load_dotenv(override=True)


CATEGORIES: Dict[str, List[str]] = {
    "ЖКХ": [
        "жкх",
        "мусор",
        "тко",
        "контейнер",
        "контейнеры",
        "свалка",
        "отходы",
        "уборка",
        "двор",
        "управляющая компания",
        "ук",
        "тсж",
        "капремонт",
        "лифт",
        "подъезд",
        "тепло",
        "отопление",
        "горячая вода",
        "холодная вода",
        "водоснабжение",
        "канализация",
        "прорыв трубы",
        "авария на теплосетях",
        "электричество",
        "свет отключили",
    ],
    "Дороги и транспорт": [
        "дорога",
        "дороги",
        "яма",
        "ямы",
        "асфальт",
        "гололед",
        "снегопад",
        "пробка",
        "дтп",
        "светофор",
        "разметка",
        "тротуар",
        "остановка",
        "автобус",
        "маршрутка",
        "троллейбус",
        "трамвай",
        "электричка",
        "общественный транспорт",
        "рейс",
        "перекрытие",
        "мост",
    ],
    "Здравоохранение": [
        "больница",
        "поликлиника",
        "врач",
        "врачи",
        "фельдшер",
        "скорая",
        "пациент",
        "медицина",
        "медицин",
        "здравоохранение",
        "очередь к врачу",
        "лекарств",
        "аптека",
        "фап",
        "стационар",
        "роддом",
        "операция",
    ],
    "Образование": [
        "школа",
        "детский сад",
        "садик",
        "учитель",
        "учителя",
        "ученик",
        "ученики",
        "образование",
        "урок",
        "класс",
        "егэ",
        "огэ",
        "директор школы",
        "ремонт школы",
        "закрыли школу",
    ],
    "Экология и ЧС": [
        "экология",
        "выброс",
        "выбросы",
        "загрязнение",
        "запах гари",
        "дым",
        "задымление",
        "пожар",
        "возгорание",
        "мчс",
        "наводнение",
        "подтопление",
        "ураган",
        "чс",
        "аварийный режим",
        "радиация",
        "утечка",
    ],
    "Экономика и промышленность": [
        "завод",
        "предприятие",
        "производство",
        "промышленность",
        "экономика",
        "зарплата",
        "задержка зарплаты",
        "сокращение",
        "увольнение",
        "инвестпроект",
        "инвестиции",
        "бизнес",
        "налог",
        "рабочие места",
        "безработица",
        "цех",
        "фабрика",
    ],
}

LOCATION_DIRECTORY: Dict[str, Dict[str, Optional[str]]] = {
    "ростов": {
        "region": "Ростовская область",
        "city": "Ростов-на-Дону",
        "district": None,
    },
    "ростов-на-дону": {
        "region": "Ростовская область",
        "city": "Ростов-на-Дону",
        "district": None,
    },
    "ростове": {
        "region": "Ростовская область",
        "city": "Ростов-на-Дону",
        "district": None,
    },
    "аксай": {
        "region": "Ростовская область",
        "city": None,
        "district": "Аксайский район",
    },
    "аксайский район": {
        "region": "Ростовская область",
        "city": None,
        "district": "Аксайский район",
    },
    "батайск": {
        "region": "Ростовская область",
        "city": "Батайск",
        "district": None,
    },
    "таганрог": {
        "region": "Ростовская область",
        "city": "Таганрог",
        "district": None,
    },
    "новочеркасск": {
        "region": "Ростовская область",
        "city": "Новочеркасск",
        "district": None,
    },
    "шахты": {
        "region": "Ростовская область",
        "city": "Шахты",
        "district": None,
    },
    "волгодонск": {
        "region": "Ростовская область",
        "city": "Волгодонск",
        "district": None,
    },
    "суворовский": {
        "region": "Ростовская область",
        "city": "Ростов-на-Дону",
        "district": "Суворовский микрорайон",
    },
}

ADDRESS_PATTERNS = [
    r"(ул\.\s*[А-ЯЁ0-9][А-Яа-яЁё0-9\-]*(?:\s+[А-ЯЁ0-9][А-Яа-яЁё0-9\-]*){0,3})",
    r"(улица\s+[А-ЯЁ0-9][А-Яа-яЁё0-9\-]*(?:\s+[А-ЯЁ0-9][А-Яа-яЁё0-9\-]*){0,3})",
    r"(проспект\s+[А-ЯЁ0-9][А-Яа-яЁё0-9\-]*(?:\s+[А-ЯЁ0-9][А-Яа-яЁё0-9\-]*){0,3})",
    r"(пр-т\s*[А-ЯЁ0-9][А-Яа-яЁё0-9\-]*(?:\s+[А-ЯЁ0-9][А-Яа-яЁё0-9\-]*){0,3})",
    r"(пер\.\s*[А-ЯЁ0-9][А-Яа-яЁё0-9\-]*(?:\s+[А-ЯЁ0-9][А-Яа-яЁё0-9\-]*){0,3})",
    r"(переулок\s+[А-ЯЁ0-9][А-Яа-яЁё0-9\-]*(?:\s+[А-ЯЁ0-9][А-Яа-яЁё0-9\-]*){0,3})",
    r"(бул\.\s*[А-ЯЁ0-9][А-Яа-яЁё0-9\-]*(?:\s+[А-ЯЁ0-9][А-Яа-яЁё0-9\-]*){0,3})",
    r"(бульвар\s+[А-ЯЁ0-9][А-Яа-яЁё0-9\-]*(?:\s+[А-ЯЁ0-9][А-Яа-яЁё0-9\-]*){0,3})",
]

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "qwen/qwen3.6-plus"
DEFAULT_PROVIDER = "rules"


class ClassifyCategoryRequest(BaseModel):
    text: str = Field(..., description="Текст сообщения или новости")
    channel_name: str = Field("", description="Название канала или группы")
    channel_description: str = Field("", description="Описание канала или группы")


class ClassifyCategoryResponse(BaseModel):
    category: str
    scores: Dict[str, int]
    matched_keywords: Dict[str, List[str]]
    provider: str = "rules"
    model: Optional[str] = None


class BatchClassifyCategoryRequest(BaseModel):
    items: List[ClassifyCategoryRequest]


class ExtractLocationResponse(BaseModel):
    region: Optional[str]
    city: Optional[str]
    district: Optional[str]
    address: Optional[str]
    provider: str = "rules"
    model: Optional[str] = None


def normalize_text(value: str) -> str:
    return " ".join(value.lower().replace("ё", "е").split())


def contains_keyword(text: str, keyword: str) -> bool:
    normalized_keyword = normalize_text(keyword)
    pattern = (
        r"(?<!\w)"
        + re.escape(normalized_keyword).replace(r"\ ", r"\s+")
        + r"(?!\w)"
    )
    return re.search(pattern, text) is not None


def classify_category(
    text: str, channel_name: str = "", channel_description: str = ""
) -> Dict[str, object]:
    combined_text = normalize_text(f"{text} {channel_name} {channel_description}")
    scores: Dict[str, int] = {}
    matched_keywords: Dict[str, List[str]] = {}

    for category, keywords in CATEGORIES.items():
        found_keywords: List[str] = []
        for keyword in keywords:
            if contains_keyword(combined_text, keyword):
                found_keywords.append(keyword)

        scores[category] = len(found_keywords)
        matched_keywords[category] = found_keywords

    best_category = max(scores, key=scores.get)
    if scores[best_category] == 0:
        best_category = "Не определено"

    return {
        "category": best_category,
        "scores": scores,
        "matched_keywords": matched_keywords,
        "provider": "rules",
        "model": None,
    }


def extract_address(text: str) -> Optional[str]:
    for pattern in ADDRESS_PATTERNS:
        match = re.search(pattern, text)
        if match is not None:
            return match.group(1).strip(" ,.;:")
    return None


def merge_location(
    current: Dict[str, Optional[str]], found: Dict[str, Optional[str]]
) -> Dict[str, Optional[str]]:
    for key in ("region", "city", "district"):
        if current[key] is None and found[key] is not None:
            current[key] = found[key]
    return current


def extract_location(
    text: str, channel_name: str = "", channel_description: str = ""
) -> Dict[str, Optional[str]]:
    combined_text = normalize_text(f"{text} {channel_name} {channel_description}")
    location: Dict[str, Optional[str]] = {
        "region": None,
        "city": None,
        "district": None,
        "address": extract_address(text),
    }

    if contains_keyword(combined_text, "ростовская область"):
        location["region"] = "Ростовская область"

    for alias, normalized_location in LOCATION_DIRECTORY.items():
        if contains_keyword(combined_text, alias):
            location = merge_location(location, normalized_location)

    location["provider"] = "rules"
    location["model"] = None
    return location


def get_provider(explicit_provider: Optional[str]) -> str:
    if explicit_provider is not None:
        return explicit_provider
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
    categories = ", ".join(CATEGORIES.keys())
    messages = [
        {
            "role": "system",
            "content": (
                "Ты сервис категоризации региональных сообщений. "
                "Верни только JSON без пояснений. "
                "Определи ровно одну категорию из фиксированного списка. "
                f"Список категорий: {categories}. "
                "Если категория не подходит, верни 'Не определено'. "
                "Формат ответа: "
                '{"category":"...", "scores":{"ЖКХ":0,"Дороги и транспорт":0,'
                '"Здравоохранение":0,"Образование":0,"Экология и ЧС":0,'
                '"Экономика и промышленность":0},'
                '"matched_keywords":{"ЖКХ":[],"Дороги и транспорт":[],'
                '"Здравоохранение":[],"Образование":[],"Экология и ЧС":[],'
                '"Экономика и промышленность":[]}}'
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
    if category not in CATEGORIES and category != "Не определено":
        raise HTTPException(status_code=502, detail="LLM returned invalid category")

    scores = payload.get("scores")
    matched_keywords = payload.get("matched_keywords")
    if not isinstance(scores, dict):
        payload["scores"] = {name: 0 for name in CATEGORIES}
    if not isinstance(matched_keywords, dict):
        payload["matched_keywords"] = {name: [] for name in CATEGORIES}

    return payload


def extract_location_llm(
    text: str, channel_name: str = "", channel_description: str = ""
) -> Dict[str, Optional[str]]:
    messages = [
        {
            "role": "system",
            "content": (
                "Ты сервис извлечения географии из региональных сообщений Ростовской области. "
                "Верни только JSON без пояснений. "
                "Нужно извлечь region, city, district, address. "
                "Если поле не найдено, верни null. "
                "Нормализуй регион как 'Ростовская область'. "
                "Нормализуй 'Аксай' как district='Аксайский район'. "
                "Нормализуй 'Ростов' и 'Ростов-на-Дону' как city='Ростов-на-Дону'. "
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
                    "location_directory": LOCATION_DIRECTORY,
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


app = FastAPI(
    title="Region Pulse Backend",
    description="API для проверки категоризации региональных сообщений",
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
    return {"categories": list(CATEGORIES.keys())}


@app.get("/api/location-directory")
def get_location_directory() -> Dict[str, List[str]]:
    return {"locations": sorted(LOCATION_DIRECTORY.keys())}


@app.get("/api/provider")
def get_provider_info() -> Dict[str, Optional[str]]:
    provider = get_provider(None)
    model = get_openrouter_model() if provider == "llm" else None
    return {"provider": provider, "model": model}


@app.post("/api/classify-category", response_model=ClassifyCategoryResponse)
def classify_category_endpoint(
    payload: ClassifyCategoryRequest,
    provider: Optional[str] = Query(
        default=None,
        pattern="^(rules|llm)$",
        description="Источник инференса: rules или llm",
    ),
) -> Dict[str, object]:
    selected_provider = get_provider(provider)
    if selected_provider == "llm":
        return classify_category_llm(
            text=payload.text,
            channel_name=payload.channel_name,
            channel_description=payload.channel_description,
        )

    return classify_category(
        text=payload.text,
        channel_name=payload.channel_name,
        channel_description=payload.channel_description,
    )


@app.post("/api/classify-category/batch")
def classify_category_batch(
    payload: BatchClassifyCategoryRequest,
    provider: Optional[str] = Query(
        default=None,
        pattern="^(rules|llm)$",
        description="Источник инференса: rules или llm",
    ),
) -> Dict[str, List[Dict[str, object]]]:
    selected_provider = get_provider(provider)
    return {
        "items": [
            (
                classify_category_llm(
                    text=item.text,
                    channel_name=item.channel_name,
                    channel_description=item.channel_description,
                )
                if selected_provider == "llm"
                else classify_category(
                    text=item.text,
                    channel_name=item.channel_name,
                    channel_description=item.channel_description,
                )
            )
            for item in payload.items
        ]
    }


@app.post("/api/extract-location", response_model=ExtractLocationResponse)
def extract_location_endpoint(
    payload: ClassifyCategoryRequest,
    provider: Optional[str] = Query(
        default=None,
        pattern="^(rules|llm)$",
        description="Источник инференса: rules или llm",
    ),
) -> Dict[str, Optional[str]]:
    selected_provider = get_provider(provider)
    if selected_provider == "llm":
        return extract_location_llm(
            text=payload.text,
            channel_name=payload.channel_name,
            channel_description=payload.channel_description,
        )

    return extract_location(
        text=payload.text,
        channel_name=payload.channel_name,
        channel_description=payload.channel_description,
    )


@app.post("/api/extract-location/batch")
def extract_location_batch(
    payload: BatchClassifyCategoryRequest,
    provider: Optional[str] = Query(
        default=None,
        pattern="^(rules|llm)$",
        description="Источник инференса: rules или llm",
    ),
) -> Dict[str, List[Dict[str, Optional[str]]]]:
    selected_provider = get_provider(provider)
    return {
        "items": [
            (
                extract_location_llm(
                    text=item.text,
                    channel_name=item.channel_name,
                    channel_description=item.channel_description,
                )
                if selected_provider == "llm"
                else extract_location(
                    text=item.text,
                    channel_name=item.channel_name,
                    channel_description=item.channel_description,
                )
            )
            for item in payload.items
        ]
    }
