from __future__ import annotations
import re

from typing import Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field


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


class ClassifyCategoryRequest(BaseModel):
    text: str = Field(..., description="Текст сообщения или новости")
    channel_name: str = Field("", description="Название канала или группы")
    channel_description: str = Field(
        "", description="Описание канала или группы"
    )


class ClassifyCategoryResponse(BaseModel):
    category: str
    scores: Dict[str, int]
    matched_keywords: Dict[str, List[str]]


class BatchClassifyCategoryRequest(BaseModel):
    items: List[ClassifyCategoryRequest]


class ExtractLocationResponse(BaseModel):
    region: Optional[str]
    city: Optional[str]
    district: Optional[str]
    address: Optional[str]


def normalize_text(value: str) -> str:
    return " ".join(value.lower().replace("ё", "е").split())


def contains_keyword(text: str, keyword: str) -> bool:
    normalized_keyword = normalize_text(keyword)
    pattern = r"(?<!\w)" + re.escape(normalized_keyword).replace(r"\ ", r"\s+") + r"(?!\w)"
    return re.search(pattern, text) is not None


def classify_category(
    text: str, channel_name: str = "", channel_description: str = ""
) -> Dict[str, object]:
    combined_text = normalize_text(
        f"{text} {channel_name} {channel_description}"
    )
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
    combined_text = normalize_text(
        f"{text} {channel_name} {channel_description}"
    )
    location = {
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

    return location


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


@app.post("/api/classify-category", response_model=ClassifyCategoryResponse)
def classify_category_endpoint(
    payload: ClassifyCategoryRequest,
) -> Dict[str, object]:
    return classify_category(
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
            classify_category(
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
    return extract_location(
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
            extract_location(
                text=item.text,
                channel_name=item.channel_name,
                channel_description=item.channel_description,
            )
            for item in payload.items
        ]
    }
