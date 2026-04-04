from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import os
import re
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Literal, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


load_dotenv(override=True)

DEFAULT_PROVIDER = "gigachat"
FALLBACK_PROVIDER = "local-fallback"
DEFAULT_CHAT_MODEL = "GigaChat-2-Lite"
DEFAULT_EMBEDDINGS_MODEL = "Embeddings-2"
DEFAULT_EMBEDDINGS_FALLBACK_MODEL = "Embeddings"
DEFAULT_SCOPE = "GIGACHAT_API_PERS"
DEFAULT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
DEFAULT_API_BASE_URL = "https://gigachat.devices.sberbank.ru/api/v1"
DEFAULT_CACHE_TTL_SECONDS = 1800
DEFAULT_CACHE_LIMIT = 512
DEFAULT_MAX_CONCURRENCY = 1
SENTIMENT_PREFILTER_MARGIN = 2

CATEGORY_NAMES = [
    "ЖКХ",
    "Дороги и транспорт",
    "Здравоохранение",
    "Образование",
    "Экология и ЧС",
    "Экономика и промышленность",
]
UNKNOWN_CATEGORY = "Не определено"
CATEGORY_SCORES_TEMPLATE = {name: 0 for name in CATEGORY_NAMES}
CATEGORY_KEYWORDS_TEMPLATE = {name: [] for name in CATEGORY_NAMES}

CATEGORY_HINTS: Dict[str, List[str]] = {
    "ЖКХ": ["жкх", "мусор", "тко", "контейнер", "вывоз", "вода", "отопление", "канализация", "свет", "лифт"],
    "Дороги и транспорт": ["дорога", "асфальт", "яма", "пробка", "автобус", "транспорт", "остановка", "светофор"],
    "Здравоохранение": ["больница", "поликлиника", "врач", "терапевт", "скорая", "лекарство", "медицина", "запись"],
    "Образование": ["школа", "садик", "учитель", "класс", "ученик", "университет", "колледж", "урок"],
    "Экология и ЧС": ["экология", "свалка", "загрязнение", "река", "дым", "пожар", "чс", "затопление", "потоп"],
    "Экономика и промышленность": ["завод", "предприятие", "бизнес", "зарплата", "инвестиции", "промышленность", "рынок"],
}

STOPWORDS = {
    "это", "как", "что", "где", "или", "при", "для", "после", "перед", "через",
    "очень", "снова", "вчера", "сегодня", "завтра", "если", "были", "было", "быть",
    "есть", "нет", "уже", "еще", "ещё", "там", "тут", "здесь", "надо", "нужно",
    "районе", "области", "городе", "улице", "домов", "жители", "житель", "сообщают",
    "жалуются", "пишут", "говорят",
}

NEGATIVE_MARKERS = {
    "жалоб", "жалуются", "не работает", "не вывоз", "не могут", "затоп", "потоп", "авар", "проблем",
    "отключ", "гряз", "вонь", "очеред", "переполн", "сорван", "нет записи", "не убира", "сломал",
    "сломан", "сломались", "опасн", "неисправ", "протеч", "нечем дышать", "воняет", "задержк",
}
POSITIVE_MARKERS = {
    "починили", "починили", "открыли", "восстановили", "решили", "улучшили", "устранили",
    "наладили", "убрали", "вывезли", "вывезен", "очистили", "отремонтировали", "заработал",
    "заработала", "заработали", "спасибо", "благодар", "отличн", "хорошая новость",
}
LOW_SIGNAL_KEYWORD_TOKENS = {
    "сегодня", "вчера", "завтра", "неделя", "неделю", "недели", "день", "дня", "дней", "месяц",
    "месяца", "жители", "житель", "люди", "снова", "более", "уже", "несколько", "ближайшие",
    "район", "районе", "область", "области", "город", "городе", "улица", "улице", "дом", "дома",
}
LOCATION_ONLY_TOKENS = {"район", "районе", "область", "области", "город", "городе", "улица", "улице"}
SIGNATURE_PATTERNS = [
    ("срыв вывоза мусора", ("мусор", "тко", "контейнер", "вывоз")),
    ("затопление территории", ("затоп", "потоп", "подтоп")),
    ("отключение горячей воды", ("горяч", "вод", "отключ")),
    ("отключение электричества", ("свет", "электр", "отключ")),
    ("аварийное состояние дороги", ("дорог", "асфальт", "яма")),
    ("задержки общественного транспорта", ("автобус", "маршрут", "транспорт", "останов")),
    ("дефицит записи к врачу", ("записи", "врач", "терапевт", "поликлиник")),
]

LOCATION_ALIASES = [
    ("ростовская область", {"region": "Ростовская область"}),
    ("ростов-на-дону", {"region": "Ростовская область", "city": "Ростов-на-Дону"}),
    ("ростов на дону", {"region": "Ростовская область", "city": "Ростов-на-Дону"}),
    ("ростов", {"region": "Ростовская область", "city": "Ростов-на-Дону"}),
    ("аксайский район", {"region": "Ростовская область", "district": "Аксайский район"}),
    ("аксай", {"region": "Ростовская область", "city": "Аксай"}),
    ("батайск", {"region": "Ростовская область", "city": "Батайск"}),
    ("таганрог", {"region": "Ростовская область", "city": "Таганрог"}),
    ("новочеркасск", {"region": "Ростовская область", "city": "Новочеркасск"}),
    ("шахты", {"region": "Ростовская область", "city": "Шахты"}),
    ("волгодонск", {"region": "Ростовская область", "city": "Волгодонск"}),
    ("азовский район", {"region": "Ростовская область", "district": "Азовский район"}),
    ("мясниковский район", {"region": "Ростовская область", "district": "Мясниковский район"}),
]

DISTRICT_STEMS = {
    "аксайск": "Аксайский район",
    "азовск": "Азовский район",
    "мясниковск": "Мясниковский район",
}

ADDRESS_PATTERNS = [
    r"((?:ул|улица)\.?\s+[А-Яа-яЁё0-9 -]{2,60})",
    r"((?:проспект|пр-т|пр)\.?\s+[А-Яа-яЁё0-9 -]{2,60})",
    r"((?:пер|переулок)\.?\s+[А-Яа-яЁё0-9 -]{2,60})",
    r"((?:бульвар|бул)\.?\s+[А-Яа-яЁё0-9 -]{2,60})",
]


class ClassifyCategoryRequest(BaseModel):
    text: str = Field(..., description="Текст сообщения или новости")
    channel_name: str = Field("", description="Название канала или группы")
    channel_description: str = Field("", description="Описание канала или группы")


class ClassifyCategoryResponse(BaseModel):
    category: str
    scores: Dict[str, int]
    matched_keywords: Dict[str, List[str]]
    provider: str = DEFAULT_PROVIDER
    model: Optional[str] = None


class BatchClassifyCategoryRequest(BaseModel):
    items: List[ClassifyCategoryRequest]


class ExtractLocationResponse(BaseModel):
    region: Optional[str]
    city: Optional[str]
    district: Optional[str]
    address: Optional[str]
    provider: str = DEFAULT_PROVIDER
    model: Optional[str] = None


class ExtractKeyWordsRequest(BaseModel):
    text: str = Field(..., description="Текст сообщения или новости")


class ExtractKeyWordsResponse(BaseModel):
    key_words: List[str]
    provider: str = DEFAULT_PROVIDER
    model: Optional[str] = None


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    precached_prompt_tokens: int = 0


class MessageAnalysisResponse(BaseModel):
    category: str
    scores: Dict[str, int]
    matched_keywords: Dict[str, List[str]]
    key_words: List[str]
    region: Optional[str]
    city: Optional[str]
    district: Optional[str]
    address: Optional[str]
    sentiment: Literal["negative", "neutral", "positive"]
    problem_signature: str
    short_summary: str
    provider: str = DEFAULT_PROVIDER
    model: Optional[str] = None
    analysis_source: Literal["llm", "fallback", "sentiment_prefilter"] = "llm"
    requires_problem_processing: bool = True
    llm_skipped_reason: Optional[str] = None
    cached: bool = False
    usage: Optional[TokenUsage] = None


class AnalyzeMessagesBatchResponse(BaseModel):
    items: List[MessageAnalysisResponse]


class TokenCountRequest(BaseModel):
    inputs: List[str] = Field(..., min_length=1)
    model: Optional[str] = None


class TokenCountItem(BaseModel):
    index: int
    tokens: int
    characters: int


class TokenCountResponse(BaseModel):
    provider: str = DEFAULT_PROVIDER
    model: str
    items: List[TokenCountItem]
    total_tokens: int
    total_characters: int


class ProviderInfoResponse(BaseModel):
    provider: str
    model: str
    embeddings_model: str
    max_concurrency: int
    cache_ttl_seconds: int


class ProblemSourceInput(BaseModel):
    id: Optional[str] = None
    text: str = Field(..., description="Текст публикации, жалобы или сообщения")
    channel_name: str = ""
    channel_description: str = ""
    source_name: Optional[str] = None
    source_type: Optional[str] = None
    source_url: Optional[str] = None
    published_at: Optional[datetime] = None


class ProblemCardsBuildRequest(BaseModel):
    items: List[ProblemSourceInput] = Field(..., min_length=1)
    top_k: int = Field(10, ge=1, le=50)
    similarity_threshold: float = Field(0.78, gt=0.0, lt=1.5)
    time_window_days: int = Field(14, ge=1, le=90)
    summarization_items: int = Field(6, ge=2, le=12)
    llm_item_analysis: bool = True
    llm_item_limit: int = Field(30, ge=0, le=200)
    llm_cluster_review: bool = True
    llm_cluster_review_limit: int = Field(8, ge=0, le=40)
    negative_only: bool = True


class TrendPoint(BaseModel):
    date: date
    mentions: int


class ProblemSourcePreview(BaseModel):
    id: str
    channel_name: str = ""
    source_name: Optional[str] = None
    source_type: Optional[str] = None
    source_url: Optional[str] = None
    published_at: Optional[datetime] = None
    snippet: str


class ProblemCardResponse(BaseModel):
    card_id: str
    rank_score: float
    title: str
    summary: str
    category: str
    key_words: List[str]
    region: Optional[str]
    city: Optional[str]
    district: Optional[str]
    address: Optional[str]
    mentions_count: int
    unique_sources_count: int
    independent_sources_count: int
    duplicate_like_count: int
    affected_locations_count: int
    negative_ratio: float
    first_seen_at: Optional[datetime]
    last_seen_at: Optional[datetime]
    peak_date: Optional[date]
    peak_mentions: int
    trend_direction: Literal["up", "down", "flat"]
    trend_points: List[TrendPoint]
    problem_signature: str
    cluster_reviewed_by_llm: bool = False
    source_ids: List[str]
    sources: List[ProblemSourcePreview]


class ProblemCardsBuildResponse(BaseModel):
    generated_at: datetime
    provider: str
    model: str
    embeddings_model: str
    total_clusters: int
    processed_items_count: int = 0
    ignored_non_negative_count: int = 0
    llm_item_analyses_used: int
    llm_cluster_reviews_used: int
    cards: List[ProblemCardResponse]


@dataclass
class CacheEntry:
    value: Dict[str, Any]
    expires_at: float


@dataclass
class PreparedProblemItem:
    source: ProblemSourceInput
    item_id: str
    normalized_text: str
    category_hint: str
    category_scores: Dict[str, int]
    key_words: List[str]
    sentiment: Literal["negative", "neutral", "positive"]
    location: Dict[str, Optional[str]]
    problem_signature: str
    short_summary: str
    embedding: List[float]
    fingerprint: str
    analysis_source: Literal["llm", "heuristic", "sentiment_prefilter"]


@dataclass
class ProblemCluster:
    items: List[PreparedProblemItem] = field(default_factory=list)
    centroid: List[float] = field(default_factory=list)
    reviewed_by_llm: bool = False


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_text(value: str) -> str:
    lowered = value.lower().replace("ё", "е")
    lowered = re.sub(r"[^\w\s-]+", " ", lowered, flags=re.UNICODE)
    return " ".join(lowered.split())


def get_provider(_: Optional[str] = None) -> str:
    value = os.getenv("REGION_PULSE_PROVIDER", DEFAULT_PROVIDER).strip().lower()
    if value in {"", "llm", "openrouter"}:
        return DEFAULT_PROVIDER
    return value


def get_chat_model() -> str:
    return os.getenv("GIGACHAT_MODEL", DEFAULT_CHAT_MODEL)


def get_embeddings_model() -> str:
    return os.getenv("GIGACHAT_EMBEDDINGS_MODEL", DEFAULT_EMBEDDINGS_MODEL)


def get_cache_ttl_seconds() -> int:
    return max(60, int(os.getenv("ANALYSIS_CACHE_TTL_SECONDS", DEFAULT_CACHE_TTL_SECONDS)))


def get_cache_limit() -> int:
    return max(32, int(os.getenv("ANALYSIS_CACHE_LIMIT", DEFAULT_CACHE_LIMIT)))


def get_max_concurrency() -> int:
    return max(1, int(os.getenv("GIGACHAT_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY)))


def get_gigachat_scope() -> str:
    return os.getenv("GIGACHAT_SCOPE", DEFAULT_SCOPE)


def get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def use_gigachat_embeddings() -> bool:
    return get_bool_env("GIGACHAT_USE_EMBEDDINGS", True)


def get_tls_verify() -> str | bool:
    if not get_bool_env("GIGACHAT_VERIFY_SSL", True):
        return False

    for env_name in ("GIGACHAT_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        value = os.getenv(env_name)
        if value:
            return value
    return True


def build_basic_auth_key() -> Optional[str]:
    for env_name in ("GIGACHAT_AUTH_KEY", "GIGACHAT_CREDENTIALS", "OPENROUTER_API_KEY"):
        value = os.getenv(env_name)
        if value:
            return value.strip()

    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    if client_id and client_secret:
        raw = f"{client_id}:{client_secret}".encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

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


def safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+", value)
        if match:
            return int(match.group(0))
    return default


def clamp_score(value: Any) -> int:
    return max(0, min(100, safe_int(value)))


def normalize_location_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().split())
    return normalized or None


def ensure_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def extract_address(text: str) -> Optional[str]:
    for pattern in ADDRESS_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return " ".join(match.group(1).strip(" ,.;").split())
    return None


def extract_location_hints(
    text: str,
    channel_name: str = "",
    channel_description: str = "",
) -> Dict[str, Optional[str]]:
    combined = " ".join(part for part in [text, channel_name, channel_description] if part)
    normalized = normalize_text(combined)
    location = {"region": None, "city": None, "district": None, "address": extract_address(combined)}

    for alias, payload in sorted(LOCATION_ALIASES, key=lambda item: len(item[0]), reverse=True):
        if alias in normalized:
            for field_name, field_value in payload.items():
                location[field_name] = field_value

    for stem, district_name in DISTRICT_STEMS.items():
        if stem in normalized and "район" in normalized and not location["district"]:
            location["region"] = location["region"] or "Ростовская область"
            location["district"] = district_name

    if "ростовской области" in normalized and not location["region"]:
        location["region"] = "Ростовская область"

    return location


def extract_tokens(text: str) -> List[str]:
    tokens = re.findall(r"[а-яa-z0-9-]{3,}", normalize_text(text), flags=re.IGNORECASE)
    return [token for token in tokens if token not in STOPWORDS]


def fallback_keywords(text: str, limit: int = 5) -> List[str]:
    counts = Counter(extract_tokens(text))
    return [word for word, _ in counts.most_common(limit)]


def heuristic_category_scores(text: str, channel_name: str = "", channel_description: str = "") -> Dict[str, int]:
    combined = normalize_text(" ".join(part for part in [text, channel_name, channel_description] if part))
    scores = {name: 0 for name in CATEGORY_NAMES}

    for category, hints in CATEGORY_HINTS.items():
        score = 0
        for hint in hints:
            if hint in combined:
                score += 22 if " " in hint else 14
        scores[category] = min(score, 100)

    return scores


def best_category_from_scores(scores: Dict[str, int]) -> str:
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ordered or ordered[0][1] <= 0:
        return UNKNOWN_CATEGORY
    return ordered[0][0]


def collect_marker_hits(normalized: str, markers: set[str]) -> List[str]:
    hits: List[str] = []
    for marker in markers:
        if marker in normalized:
            hits.append(marker)
    return hits


def analyze_sentiment_signal(text: str) -> Dict[str, Any]:
    normalized = normalize_text(text)
    negative_hits = collect_marker_hits(normalized, NEGATIVE_MARKERS)
    positive_hits = collect_marker_hits(normalized, POSITIVE_MARKERS)
    negative_score = sum(2 if " " in marker else 1 for marker in negative_hits)
    positive_score = sum(2 if " " in marker else 1 for marker in positive_hits)

    if negative_score > positive_score:
        sentiment: Literal["negative", "neutral", "positive"] = "negative"
    elif positive_score >= max(2, negative_score + SENTIMENT_PREFILTER_MARGIN):
        sentiment = "positive"
    elif negative_score == positive_score == 0:
        sentiment = "neutral"
    else:
        sentiment = "neutral"

    return {
        "sentiment": sentiment,
        "negative_score": negative_score,
        "positive_score": positive_score,
        "negative_hits": negative_hits,
        "positive_hits": positive_hits,
    }


def should_skip_llm_for_positive(signal: Dict[str, Any]) -> bool:
    return (
        signal.get("sentiment") == "positive"
        and safe_int(signal.get("negative_score")) == 0
        and safe_int(signal.get("positive_score")) >= 2
    )


def estimate_sentiment(text: str) -> Literal["negative", "neutral", "positive"]:
    return analyze_sentiment_signal(text)["sentiment"]


def short_summary_fallback(text: str) -> str:
    cleaned = " ".join(text.strip().split())
    if len(cleaned) <= 180:
        return cleaned
    return f"{cleaned[:177].rstrip()}..."


def build_problem_signature(text: str, key_words: List[str]) -> str:
    normalized = normalize_text(text)
    for signature, patterns in SIGNATURE_PATTERNS:
        if sum(1 for pattern in patterns if pattern in normalized) >= 2:
            return signature
    cleaned_keywords = sanitize_keywords(key_words)
    if cleaned_keywords:
        return " ".join(cleaned_keywords[:3])
    tokens = extract_tokens(text)
    return " ".join(tokens[:5]) or "локальная проблема"


def is_low_signal_keyword(value: str) -> bool:
    normalized = normalize_text(value)
    tokens = [token for token in extract_tokens(normalized) if token]
    if not tokens:
        return True
    if set(tokens).issubset(LOW_SIGNAL_KEYWORD_TOKENS):
        return True
    if len(tokens) <= 3 and any(part in normalized.split() for part in LOCATION_ONLY_TOKENS):
        topical_matches = sum(1 for hints in CATEGORY_HINTS.values() for hint in hints if hint in normalized)
        if topical_matches == 0:
            return True
    return False


def sanitize_keywords(value: Any) -> List[str]:
    if isinstance(value, str):
        raw_items = re.split(r"[,;\n]+", value)
    elif isinstance(value, list):
        raw_items = value
    else:
        return []
    result: List[str] = []
    for item in raw_items:
        if not isinstance(item, str):
            continue
        normalized = " ".join(item.strip().strip(".,;:!?\"'«»").split())
        lowered = normalize_text(normalized)
        if not normalized or is_low_signal_keyword(normalized):
            continue
        if lowered and lowered not in {normalize_text(existing) for existing in result}:
            result.append(lowered)
    return result[:5]


def normalize_problem_signature(
    value: Any,
    text: str,
    key_words: List[str],
) -> str:
    signature = " ".join(str(value or "").strip().strip(".,;:!?\"'«»").split())
    normalized = normalize_text(signature)
    canonical = build_problem_signature(text, key_words)
    canonical_tokens = extract_tokens(canonical)
    if not signature:
        return canonical
    if len(normalized.split()) > 6 or any(token in normalized for token in ("район", "город", "область", "аксай", "ростов", "батайск")):
        return canonical
    if canonical_tokens and token_overlap_score(extract_tokens(normalized), canonical_tokens) < 0.34:
        return canonical
    return normalized


def signature_similarity_score(left: str, right: str) -> float:
    left_normalized = normalize_text(left)
    right_normalized = normalize_text(right)
    if not left_normalized or not right_normalized:
        return 0.0
    if left_normalized == right_normalized:
        return 1.0
    return token_overlap_score(extract_tokens(left_normalized), extract_tokens(right_normalized))


def merge_category_scores(
    fallback_scores: Dict[str, int],
    llm_scores: Dict[str, Any],
) -> Dict[str, int]:
    merged: Dict[str, int] = {}
    for name in CATEGORY_NAMES:
        fallback_score = clamp_score(fallback_scores.get(name, 0))
        llm_score = clamp_score(llm_scores.get(name, fallback_score))
        merged[name] = clamp_score(round(fallback_score * 0.45 + llm_score * 0.55))
    return merged


def reconcile_category(
    fallback_category: str,
    fallback_scores: Dict[str, int],
    llm_category: Any,
    merged_scores: Dict[str, int],
    llm_scores: Dict[str, Any],
) -> str:
    final_category = best_category_from_scores(merged_scores)
    if final_category == UNKNOWN_CATEGORY:
        final_category = fallback_category

    if (
        fallback_category in CATEGORY_NAMES
        and clamp_score(fallback_scores.get(fallback_category, 0)) >= 90
        and llm_category in CATEGORY_NAMES
        and llm_category != fallback_category
        and clamp_score(llm_scores.get(fallback_category, 0)) <= 40
    ):
        return fallback_category

    if llm_category in CATEGORY_NAMES and final_category == UNKNOWN_CATEGORY:
        return llm_category

    return final_category


def sanitize_matched_keywords(
    value: Any,
    category: str,
    key_words: List[str],
) -> Dict[str, List[str]]:
    result = {name: [] for name in CATEGORY_NAMES}
    if isinstance(value, dict):
        for name in CATEGORY_NAMES:
            result[name] = sanitize_keywords(value.get(name))

    if category in CATEGORY_NAMES and not result[category]:
        result[category] = key_words[:]

    return result


def normalize_usage(value: Any) -> Optional[TokenUsage]:
    if not isinstance(value, dict):
        return None
    return TokenUsage(
        prompt_tokens=max(0, safe_int(value.get("prompt_tokens"))),
        completion_tokens=max(0, safe_int(value.get("completion_tokens"))),
        total_tokens=max(0, safe_int(value.get("total_tokens"))),
        precached_prompt_tokens=max(0, safe_int(value.get("precached_prompt_tokens"))),
    )


def resolve_location(fields: List[Dict[str, Optional[str]]]) -> Dict[str, Optional[str]]:
    def resolve_one(field_name: str) -> Optional[str]:
        values = [item.get(field_name) for item in fields if item.get(field_name)]
        if not values:
            return None
        counts = Counter(values)
        if len(counts) == 1:
            return values[0]
        top = counts.most_common(2)
        if top[0][1] >= 2 and (len(top) == 1 or top[0][1] > top[1][1]):
            return top[0][0]
        return None

    return {
        "region": resolve_one("region"),
        "city": resolve_one("city"),
        "district": resolve_one("district"),
        "address": resolve_one("address"),
    }


def location_overlap_score(
    item_location: Dict[str, Optional[str]],
    cluster_location: Dict[str, Optional[str]],
) -> float:
    score = 0.0
    for field_name, bonus, penalty in (
        ("district", 0.08, -0.18),
        ("city", 0.06, -0.15),
        ("region", 0.03, -0.12),
    ):
        item_value = item_location.get(field_name)
        cluster_value = cluster_location.get(field_name)
        if item_value and cluster_value:
            score += bonus if item_value == cluster_value else penalty
    return score


def cosine_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def average_embeddings(vectors: List[List[float]]) -> List[float]:
    if not vectors:
        return []
    width = len(vectors[0])
    result = [0.0] * width
    for vector in vectors:
        for index, value in enumerate(vector):
            result[index] += value
    return [value / len(vectors) for value in result]


def local_hashed_embedding(text: str, size: int = 64) -> List[float]:
    vector = [0.0] * size
    for token in extract_tokens(text):
        index = int(hashlib.sha1(token.encode("utf-8")).hexdigest(), 16) % size
        vector[index] += 1.0
    return vector


def build_item_id(source: ProblemSourceInput, index: int) -> str:
    if source.id:
        return source.id
    payload = f"{index}:{source.channel_name}:{source.source_url}:{source.text[:120]}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def build_fingerprint(text: str) -> str:
    return hashlib.sha1(normalize_text(text).encode("utf-8")).hexdigest()[:20]


def cluster_time_distance_days(
    item_dt: Optional[datetime],
    cluster_dt: Optional[datetime],
) -> Optional[float]:
    if item_dt is None or cluster_dt is None:
        return None
    return abs((item_dt - cluster_dt).total_seconds()) / 86400


def build_trend_points(items: List[PreparedProblemItem]) -> List[TrendPoint]:
    counts: Counter[date] = Counter()
    for item in items:
        published_at = ensure_datetime(item.source.published_at)
        if published_at is not None:
            counts[published_at.date()] += 1
    return [TrendPoint(date=day, mentions=counts[day]) for day in sorted(counts)]


def detect_trend_direction(points: List[TrendPoint]) -> Literal["up", "down", "flat"]:
    if len(points) < 2:
        return "flat"
    if points[-1].mentions > points[0].mentions:
        return "up"
    if points[-1].mentions < points[0].mentions:
        return "down"
    return "flat"


def location_label(location: Dict[str, Optional[str]]) -> Optional[str]:
    for field_name in ("district", "city", "region", "address"):
        value = location.get(field_name)
        if value:
            return value
    return None


def build_problem_title(
    category: str,
    location: Dict[str, Optional[str]],
    key_words: List[str],
    signature: str,
) -> str:
    topic = signature or (key_words[0] if key_words else "Проблема")
    location_suffix = location_label(location)
    if location_suffix:
        return f"{topic.capitalize()} ({location_suffix})"
    if category != UNKNOWN_CATEGORY:
        return f"{topic.capitalize()} ({category})"
    return topic.capitalize()


def build_problem_summary_fallback(
    items: List[PreparedProblemItem],
    category: str,
    location: Dict[str, Optional[str]],
    key_words: List[str],
) -> str:
    mentions_count = len(items)
    sources_count = len({item.source.source_name or item.source.channel_name or item.source.source_url or item.item_id for item in items})
    location_suffix = location_label(location)
    keywords_part = ", ".join(key_words[:3]) if key_words else "схожей тематикой"
    base = f"Зафиксировано {mentions_count} упоминаний из {sources_count} источников"
    if category != UNKNOWN_CATEGORY:
        base += f" по теме «{category}»"
    if location_suffix:
        base += f" в локации «{location_suffix}»"
    return f"{base}. Основные сигналы: {keywords_part}."


def make_cache_key(text: str, channel_name: str, channel_description: str) -> str:
    payload = json.dumps(
        {
            "text": normalize_text(text),
            "channel_name": normalize_text(channel_name),
            "channel_description": normalize_text(channel_description),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def token_overlap_score(left_tokens: List[str], right_tokens: List[str]) -> float:
    left_set = {token for token in left_tokens if token}
    right_set = {token for token in right_tokens if token}
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


class GigaChatService:
    def __init__(self) -> None:
        timeout = httpx.Timeout(connect=20.0, read=120.0, write=20.0, pool=20.0)
        self._client = httpx.AsyncClient(timeout=timeout, verify=get_tls_verify())
        self._auth_lock = asyncio.Lock()
        self._request_semaphore = asyncio.Semaphore(get_max_concurrency())
        self._access_token: Optional[str] = None
        self._access_token_expires_at: float = 0.0
        self._analysis_cache: Dict[str, CacheEntry] = {}

    async def close(self) -> None:
        await self._client.aclose()

    async def _refresh_access_token(self, force: bool = False) -> str:
        now_ts = utc_now().timestamp()
        if not force and self._access_token and now_ts < self._access_token_expires_at - 60:
            return self._access_token

        async with self._auth_lock:
            now_ts = utc_now().timestamp()
            if not force and self._access_token and now_ts < self._access_token_expires_at - 60:
                return self._access_token

            auth_key = build_basic_auth_key()
            if not auth_key:
                raise HTTPException(status_code=503, detail="GigaChat authorization key is not configured")

            response = await self._client.post(
                os.getenv("GIGACHAT_AUTH_URL", DEFAULT_AUTH_URL),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "RqUID": str(uuid.uuid4()),
                    "Authorization": f"Basic {auth_key}",
                },
                data={"scope": get_gigachat_scope()},
            )

            if response.status_code >= 400:
                raise HTTPException(
                    status_code=502,
                    detail=f"GigaChat auth error ({response.status_code}): {response.text}",
                )

            body = response.json()
            access_token = body.get("access_token")
            expires_at = safe_int(body.get("expires_at"))
            if not access_token or not expires_at:
                raise HTTPException(status_code=502, detail="GigaChat auth response is incomplete")

            self._access_token = access_token
            self._access_token_expires_at = float(expires_at)
            return access_token

    async def _authorized_post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        base_url = os.getenv("GIGACHAT_API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")
        retryable_statuses = {429, 500, 502, 503, 504}

        for attempt in range(3):
            token = await self._refresh_access_token(force=attempt == 1)
            try:
                async with self._request_semaphore:
                    response = await self._client.post(
                        f"{base_url}{path}",
                        headers={
                            "Accept": "application/json",
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {token}",
                        },
                        json=payload,
                    )
            except httpx.HTTPError as error:
                if attempt == 2:
                    raise HTTPException(status_code=502, detail=f"GigaChat transport error: {error}") from error
                await asyncio.sleep(attempt + 1)
                continue

            if response.status_code == 401 and attempt < 2:
                await self._refresh_access_token(force=True)
                continue

            if response.status_code in retryable_statuses and attempt < 2:
                await asyncio.sleep(attempt + 1)
                continue

            if response.status_code >= 400:
                raise HTTPException(
                    status_code=502,
                    detail=f"GigaChat error ({response.status_code}): {response.text}",
                )

            return response.json()

        raise HTTPException(status_code=502, detail="GigaChat request failed after retries")

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 320,
        temperature: float = 0.0001,
    ) -> Dict[str, Any]:
        body = await self._authorized_post(
            "/chat/completions",
            {
                "model": get_chat_model(),
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "repetition_penalty": 1.05,
            },
        )
        choices = body.get("choices") or []
        if not choices:
            raise HTTPException(status_code=502, detail="GigaChat response has no choices")

        message = choices[0].get("message") or {}
        return {
            "content": message.get("content", ""),
            "model": body.get("model", get_chat_model()),
            "usage": normalize_usage(body.get("usage")),
        }

    async def create_embeddings(self, texts: List[str]) -> Dict[str, Any]:
        models_to_try = [get_embeddings_model()]
        if DEFAULT_EMBEDDINGS_FALLBACK_MODEL not in models_to_try:
            models_to_try.append(DEFAULT_EMBEDDINGS_FALLBACK_MODEL)

        last_error: Optional[HTTPException] = None
        for model_name in models_to_try:
            try:
                body = await self._authorized_post(
                    "/embeddings",
                    {"model": model_name, "input": texts},
                )
                data = body.get("data") or []
                vectors = [item.get("embedding", []) for item in data]
                if len(vectors) != len(texts):
                    raise HTTPException(status_code=502, detail="GigaChat embeddings response is incomplete")
                return {"vectors": vectors, "model": body.get("model", model_name)}
            except HTTPException as error:
                last_error = error
                if model_name == models_to_try[-1]:
                    raise

        if last_error is not None:
            raise last_error
        raise HTTPException(status_code=502, detail="GigaChat embeddings request failed")

    async def count_tokens(self, inputs: List[str], model: Optional[str] = None) -> Dict[str, Any]:
        body = await self._authorized_post(
            "/tokens/count",
            {"model": model or get_chat_model(), "input": inputs},
        )
        return {"items": body, "model": model or get_chat_model()}

    def _analysis_from_fallback(
        self,
        text: str,
        channel_name: str = "",
        channel_description: str = "",
    ) -> Dict[str, Any]:
        scores = heuristic_category_scores(text, channel_name, channel_description)
        category = best_category_from_scores(scores)
        key_words = sanitize_keywords(fallback_keywords(text)) or fallback_keywords(text)
        location = extract_location_hints(text, channel_name, channel_description)
        signature = build_problem_signature(text, key_words)
        sentiment = estimate_sentiment(text)
        return {
            "category": category,
            "scores": scores,
            "matched_keywords": sanitize_matched_keywords({}, category, key_words),
            "key_words": key_words,
            "region": location["region"],
            "city": location["city"],
            "district": location["district"],
            "address": location["address"],
            "sentiment": sentiment,
            "problem_signature": signature,
            "short_summary": short_summary_fallback(text),
            "provider": FALLBACK_PROVIDER,
            "model": None,
            "analysis_source": "fallback",
            "requires_problem_processing": sentiment == "negative",
            "llm_skipped_reason": None,
            "cached": False,
            "usage": None,
        }

    async def analyze_message(
        self,
        text: str,
        channel_name: str = "",
        channel_description: str = "",
    ) -> Dict[str, Any]:
        cache_key = make_cache_key(text, channel_name, channel_description)
        now_ts = utc_now().timestamp()
        cached_entry = self._analysis_cache.get(cache_key)
        if cached_entry and cached_entry.expires_at > now_ts:
            cached = json.loads(json.dumps(cached_entry.value, ensure_ascii=False))
            cached["cached"] = True
            return cached

        heuristics = self._analysis_from_fallback(text, channel_name, channel_description)
        sentiment_signal = analyze_sentiment_signal(text)
        if should_skip_llm_for_positive(sentiment_signal):
            skipped = json.loads(json.dumps(heuristics, ensure_ascii=False))
            skipped["category"] = UNKNOWN_CATEGORY
            skipped["scores"] = dict(CATEGORY_SCORES_TEMPLATE)
            skipped["matched_keywords"] = {name: [] for name in CATEGORY_NAMES}
            skipped["key_words"] = []
            skipped["problem_signature"] = "позитивный сигнал"
            skipped["analysis_source"] = "sentiment_prefilter"
            skipped["requires_problem_processing"] = False
            skipped["llm_skipped_reason"] = "positive_sentiment_prefilter"
            self._analysis_cache[cache_key] = CacheEntry(value=skipped, expires_at=now_ts + get_cache_ttl_seconds())
            return skipped

        top_categories = sorted(heuristics["scores"].items(), key=lambda item: item[1], reverse=True)[:2]
        category_hints = [name for name, score in top_categories if score > 0]
        location_hints = {
            "region": heuristics["region"],
            "city": heuristics["city"],
            "district": heuristics["district"],
            "address": heuristics["address"],
        }

        messages = [
            {
                "role": "system",
                "content": (
                    "Ты анализируешь обращения граждан и региональные публикации. Верни только JSON без пояснений. "
                    "Схема ответа: "
                    '{"category":"...",'
                    '"scores":{"ЖКХ":0,"Дороги и транспорт":0,"Здравоохранение":0,"Образование":0,"Экология и ЧС":0,"Экономика и промышленность":0},'
                    '"matched_keywords":{"ЖКХ":[],"Дороги и транспорт":[],"Здравоохранение":[],"Образование":[],"Экология и ЧС":[],"Экономика и промышленность":[]},'
                    '"key_words":["..."],"location":{"region":null,"city":null,"district":null,"address":null},'
                    '"sentiment":"negative","problem_signature":"...","short_summary":"..."} '
                    "Выбери ровно одну категорию из фиксированного списка. "
                    "scores верни целыми числами 0..100. key_words верни 2-5 коротких фраз. "
                    "problem_signature сделай короткой нормализованной формулировкой 3-8 слов. "
                    "short_summary сделай одним коротким предложением до 180 символов. "
                    "Не выдумывай адрес или локацию, неизвестные поля location заполняй null. "
                    "Подсказки пользователя могут быть неполными или ошибочными: опирайся в первую очередь на сам текст."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "text": text,
                        "channel_name": channel_name,
                        "channel_description": channel_description,
                        "hints": {
                            "likely_categories": category_hints,
                            "location": location_hints,
                            "key_words": heuristics["key_words"],
                            "sentiment": heuristics["sentiment"],
                            "negative_hits": sentiment_signal["negative_hits"][:4],
                            "positive_hits": sentiment_signal["positive_hits"][:4],
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ]

        try:
            raw = await self.chat_completion(messages, max_tokens=220)
            payload = parse_json_from_llm(raw["content"])
        except (HTTPException, ValueError):
            return heuristics

        location_payload = payload.get("location") if isinstance(payload.get("location"), dict) else {}
        key_words = sanitize_keywords(payload.get("key_words")) or heuristics["key_words"]
        scores_value = payload.get("scores") if isinstance(payload.get("scores"), dict) else {}
        scores = merge_category_scores(heuristics["scores"], scores_value)

        category = reconcile_category(
            heuristics["category"],
            heuristics["scores"],
            payload.get("category"),
            scores,
            scores_value,
        )

        sentiment = payload.get("sentiment")
        if sentiment not in {"negative", "neutral", "positive"}:
            sentiment = heuristics["sentiment"]
        if sentiment_signal["negative_score"] > sentiment_signal["positive_score"] and sentiment == "positive":
            sentiment = "negative"

        short_summary = short_summary_fallback(str(payload.get("short_summary") or text))
        signature = normalize_problem_signature(payload.get("problem_signature"), text, key_words)

        location = {
            "region": normalize_location_value(location_payload.get("region") or payload.get("region") or heuristics["region"]),
            "city": normalize_location_value(location_payload.get("city") or payload.get("city") or heuristics["city"]),
            "district": normalize_location_value(location_payload.get("district") or payload.get("district") or heuristics["district"]),
            "address": normalize_location_value(location_payload.get("address") or payload.get("address") or heuristics["address"]),
        }

        result = {
            "category": category,
            "scores": scores,
            "matched_keywords": sanitize_matched_keywords(payload.get("matched_keywords"), category, key_words),
            "key_words": key_words,
            "region": location["region"],
            "city": location["city"],
            "district": location["district"],
            "address": location["address"],
            "sentiment": sentiment,
            "problem_signature": signature,
            "short_summary": short_summary,
            "provider": DEFAULT_PROVIDER,
            "model": raw["model"],
            "analysis_source": "llm",
            "requires_problem_processing": sentiment == "negative",
            "llm_skipped_reason": None,
            "cached": False,
            "usage": raw["usage"].model_dump() if raw["usage"] is not None else None,
        }

        self._analysis_cache[cache_key] = CacheEntry(value=result, expires_at=now_ts + get_cache_ttl_seconds())
        if len(self._analysis_cache) > get_cache_limit():
            expired_keys = [key for key, entry in self._analysis_cache.items() if entry.expires_at <= now_ts]
            for key in expired_keys:
                self._analysis_cache.pop(key, None)
            while len(self._analysis_cache) > get_cache_limit():
                oldest_key = next(iter(self._analysis_cache))
                self._analysis_cache.pop(oldest_key, None)

        return json.loads(json.dumps(result, ensure_ascii=False))

    async def summarize_problem_cluster(
        self,
        items: List[PreparedProblemItem],
        location: Dict[str, Optional[str]],
        category_hint: str,
        key_words_hint: List[str],
        summarization_items: int,
    ) -> Dict[str, Any]:
        representatives = sorted(
            items,
            key=lambda item: (
                ensure_datetime(item.source.published_at) or datetime.min.replace(tzinfo=timezone.utc),
                len(item.source.text),
            ),
            reverse=True,
        )[:summarization_items]

        messages = [
            {
                "role": "system",
                "content": (
                    "Ты собираешь карточку региональной проблемы. Верни только JSON без пояснений. "
                    'Схема: {"title":"...","summary":"...","category":"...","key_words":["..."],'
                    '"location":{"region":null,"city":null,"district":null,"address":null}} '
                    "title до 90 символов. summary 2-3 коротких предложения до 320 символов. "
                    "category должна быть одной из фиксированных категорий. Не добавляй фактов, которых нет в публикациях."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "category_hint": category_hint,
                        "key_words_hint": key_words_hint,
                        "location_hint": location,
                        "items": [
                            {
                                "published_at": ensure_datetime(item.source.published_at).isoformat()
                                if ensure_datetime(item.source.published_at)
                                else None,
                                "source": item.source.source_name or item.source.channel_name or item.source.source_url,
                                "problem_signature": item.problem_signature,
                                "text": item.short_summary,
                            }
                            for item in representatives
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ]

        try:
            raw = await self.chat_completion(messages, max_tokens=260, temperature=0.05)
            payload = parse_json_from_llm(raw["content"])
        except (HTTPException, ValueError):
            return {}

        location_payload = payload.get("location") if isinstance(payload.get("location"), dict) else {}
        return {
            "title": " ".join(str(payload.get("title") or "").strip().split()),
            "summary": short_summary_fallback(str(payload.get("summary") or "")),
            "category": payload.get("category"),
            "key_words": sanitize_keywords(payload.get("key_words")),
            "location": {
                "region": normalize_location_value(location_payload.get("region")),
                "city": normalize_location_value(location_payload.get("city")),
                "district": normalize_location_value(location_payload.get("district")),
                "address": normalize_location_value(location_payload.get("address")),
            },
        }

    async def prepare_problem_item(
        self,
        source: ProblemSourceInput,
        index: int,
        embedding: List[float],
        use_llm: bool,
    ) -> PreparedProblemItem:
        fallback_scores = heuristic_category_scores(source.text, source.channel_name, source.channel_description)
        fallback_category = best_category_from_scores(fallback_scores)
        fallback_keywords_value = fallback_keywords(source.text)
        fallback_location = extract_location_hints(source.text, source.channel_name, source.channel_description)
        fallback_sentiment = estimate_sentiment(source.text)
        fallback_signature = build_problem_signature(source.text, fallback_keywords_value)

        analysis_source: Literal["llm", "heuristic", "sentiment_prefilter"] = "heuristic"
        analysis: Dict[str, Any] = {}
        if use_llm:
            analysis = await self.analyze_message(source.text, source.channel_name, source.channel_description)
            if analysis.get("analysis_source") == "llm":
                analysis_source = "llm"
            elif analysis.get("analysis_source") == "sentiment_prefilter":
                analysis_source = "sentiment_prefilter"

        category_hint = analysis.get("category")
        if category_hint not in CATEGORY_NAMES:
            category_hint = fallback_category

        scores = analysis.get("scores") if isinstance(analysis.get("scores"), dict) else fallback_scores
        key_words = sanitize_keywords(analysis.get("key_words")) or fallback_keywords_value
        location = {
            "region": normalize_location_value(analysis.get("region")) or fallback_location["region"],
            "city": normalize_location_value(analysis.get("city")) or fallback_location["city"],
            "district": normalize_location_value(analysis.get("district")) or fallback_location["district"],
            "address": normalize_location_value(analysis.get("address")) or fallback_location["address"],
        }
        sentiment = analysis.get("sentiment") if analysis.get("sentiment") in {"negative", "neutral", "positive"} else fallback_sentiment
        signature = normalize_problem_signature(analysis.get("problem_signature"), source.text, key_words) or fallback_signature
        short_summary = short_summary_fallback(str(analysis.get("short_summary") or source.text))

        return PreparedProblemItem(
            source=source,
            item_id=build_item_id(source, index),
            normalized_text=normalize_text(source.text),
            category_hint=category_hint,
            category_scores=scores,
            key_words=key_words,
            sentiment=sentiment,
            location=location,
            problem_signature=signature,
            short_summary=short_summary,
            embedding=embedding,
            fingerprint=build_fingerprint(source.text),
            analysis_source=analysis_source,
        )

    async def review_cluster_merge(
        self,
        left_cluster: ProblemCluster,
        right_cluster: ProblemCluster,
    ) -> bool:
        left_items = sorted(left_cluster.items, key=lambda item: len(item.source.text), reverse=True)[:2]
        right_items = sorted(right_cluster.items, key=lambda item: len(item.source.text), reverse=True)[:2]

        messages = [
            {
                "role": "system",
                "content": (
                    "Ты решаешь, относятся ли две группы публикаций к одной и той же региональной проблеме. "
                    "Верни только JSON без пояснений в формате "
                    '{"same_problem":true,"confidence":0,"shared_location":false,"reason":"..."} '
                    "same_problem=true только если публикации описывают один и тот же инцидент или устойчивую проблему "
                    "в одной локации или в тесно связанной локации. "
                    "Если это просто одна категория, но разные сюжеты, верни false. "
                    "confidence верни целым числом 0..100."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "cluster_a": [
                            {
                                "category": item.category_hint,
                                "location": item.location,
                                "problem_signature": item.problem_signature,
                                "text": item.short_summary,
                            }
                            for item in left_items
                        ],
                        "cluster_b": [
                            {
                                "category": item.category_hint,
                                "location": item.location,
                                "problem_signature": item.problem_signature,
                                "text": item.short_summary,
                            }
                            for item in right_items
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ]

        try:
            raw = await self.chat_completion(messages, max_tokens=120, temperature=0.01)
            payload = parse_json_from_llm(raw["content"])
        except (HTTPException, ValueError):
            return False

        confidence = clamp_score(payload.get("confidence"))
        return bool(payload.get("same_problem")) and confidence >= 60

    async def build_problem_cards(self, payload: ProblemCardsBuildRequest) -> Dict[str, Any]:
        try:
            if use_gigachat_embeddings():
                embeddings_raw = await self.create_embeddings([item.text for item in payload.items])
                vectors = embeddings_raw["vectors"]
                embeddings_model = embeddings_raw["model"]
            else:
                raise HTTPException(status_code=0, detail="GigaChat embeddings disabled")
        except HTTPException:
            vectors = [local_hashed_embedding(item.text) for item in payload.items]
            embeddings_model = "local-hash"
        llm_indexes: set[int] = set()
        if payload.llm_item_analysis and payload.llm_item_limit > 0:
            ranked_indexes = sorted(
                range(len(payload.items)),
                key=lambda index: ensure_datetime(payload.items[index].published_at) or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
            llm_indexes = set(ranked_indexes[: payload.llm_item_limit])
        prepared_items = await asyncio.gather(
            *[
                self.prepare_problem_item(source, index, vectors[index], index in llm_indexes)
                for index, source in enumerate(payload.items)
            ]
        )
        llm_item_analyses_used = sum(1 for item in prepared_items if item.analysis_source == "llm")
        ignored_non_negative_count = sum(1 for item in prepared_items if item.sentiment != "negative")
        if payload.negative_only:
            prepared_items = [item for item in prepared_items if item.sentiment == "negative"]
        processed_items_count = len(prepared_items)

        if not prepared_items:
            return {
                "generated_at": utc_now(),
                "provider": DEFAULT_PROVIDER,
                "model": get_chat_model(),
                "embeddings_model": embeddings_model,
                "total_clusters": 0,
                "processed_items_count": 0,
                "ignored_non_negative_count": ignored_non_negative_count,
                "llm_item_analyses_used": llm_item_analyses_used,
                "llm_cluster_reviews_used": 0,
                "cards": [],
            }

        prepared_items.sort(key=lambda item: ensure_datetime(item.source.published_at) or datetime.min.replace(tzinfo=timezone.utc))

        clusters: List[ProblemCluster] = []
        for item in prepared_items:
            best_cluster: Optional[ProblemCluster] = None
            best_score = -1.0

            for cluster in clusters:
                cluster_location = resolve_location([cluster_item.location for cluster_item in cluster.items])
                cluster_signatures = [cluster_item.problem_signature for cluster_item in cluster.items if cluster_item.problem_signature]
                cluster_signature = Counter(cluster_signatures).most_common(1)[0][0] if cluster_signatures else ""
                cluster_time = max(
                    (ensure_datetime(cluster_item.source.published_at) for cluster_item in cluster.items if ensure_datetime(cluster_item.source.published_at)),
                    default=None,
                )
                item_time = ensure_datetime(item.source.published_at)
                distance_days = cluster_time_distance_days(item_time, cluster_time)
                if distance_days is not None and distance_days > payload.time_window_days:
                    continue

                similarity = cosine_similarity(item.embedding, cluster.centroid)
                signature_similarity = signature_similarity_score(item.problem_signature, cluster_signature)
                category_bonus = 0.05 if item.category_hint != UNKNOWN_CATEGORY and any(
                    cluster_item.category_hint == item.category_hint for cluster_item in cluster.items
                ) else 0.0
                location_score = location_overlap_score(item.location, cluster_location)
                combined_score = max(
                    similarity + category_bonus + location_score,
                    signature_similarity + category_bonus + location_score,
                )
                if combined_score > payload.similarity_threshold and combined_score > best_score:
                    best_cluster = cluster
                    best_score = combined_score

            if best_cluster is None:
                clusters.append(ProblemCluster(items=[item], centroid=item.embedding[:]))
            else:
                best_cluster.items.append(item)
                best_cluster.centroid = average_embeddings([cluster_item.embedding for cluster_item in best_cluster.items])

        llm_cluster_reviews_used = 0
        if payload.llm_cluster_review and payload.llm_cluster_review_limit > 0 and len(clusters) > 1:
            reviews_left = payload.llm_cluster_review_limit
            merged = True
            while merged and reviews_left > 0:
                merged = False
                candidates: List[tuple[float, int, int]] = []

                for left_index in range(len(clusters)):
                    for right_index in range(left_index + 1, len(clusters)):
                        left_cluster = clusters[left_index]
                        right_cluster = clusters[right_index]
                        centroid_similarity = cosine_similarity(left_cluster.centroid, right_cluster.centroid)
                        if centroid_similarity < payload.similarity_threshold - 0.08:
                            continue

                        left_keywords = [keyword for item in left_cluster.items for keyword in item.key_words[:3]]
                        right_keywords = [keyword for item in right_cluster.items for keyword in item.key_words[:3]]
                        overlap = token_overlap_score(left_keywords, right_keywords)
                        left_location = resolve_location([item.location for item in left_cluster.items])
                        right_location = resolve_location([item.location for item in right_cluster.items])
                        combined = centroid_similarity + overlap * 0.12 + location_overlap_score(left_location, right_location)
                        if combined >= payload.similarity_threshold - 0.02:
                            candidates.append((combined, left_index, right_index))

                candidates.sort(reverse=True)
                for _, left_index, right_index in candidates:
                    if reviews_left <= 0:
                        break
                    if left_index >= len(clusters) or right_index >= len(clusters):
                        continue

                    left_cluster = clusters[left_index]
                    right_cluster = clusters[right_index]
                    left_cluster.reviewed_by_llm = True
                    right_cluster.reviewed_by_llm = True
                    llm_cluster_reviews_used += 1
                    reviews_left -= 1

                    if await self.review_cluster_merge(left_cluster, right_cluster):
                        left_cluster.items.extend(right_cluster.items)
                        left_cluster.centroid = average_embeddings([item.embedding for item in left_cluster.items])
                        left_cluster.reviewed_by_llm = True
                        clusters.pop(right_index)
                        merged = True
                        break

        cards: List[Dict[str, Any]] = []
        for cluster in clusters:
            cluster_items = sorted(
                cluster.items,
                key=lambda item: ensure_datetime(item.source.published_at) or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
            category_votes = Counter(item.category_hint for item in cluster_items if item.category_hint != UNKNOWN_CATEGORY)
            category_hint = category_votes.most_common(1)[0][0] if category_votes else UNKNOWN_CATEGORY

            all_keywords: Counter[str] = Counter()
            for item in cluster_items:
                all_keywords.update(item.key_words)
            key_words_hint = [word for word, _ in all_keywords.most_common(5)]
            location = resolve_location([item.location for item in cluster_items])
            llm_summary: Dict[str, Any] = {}
            if len(cluster_items) > 1:
                llm_summary = await self.summarize_problem_cluster(
                    items=cluster_items,
                    location=location,
                    category_hint=category_hint,
                    key_words_hint=key_words_hint,
                    summarization_items=payload.summarization_items,
                )

            llm_location = llm_summary.get("location") if isinstance(llm_summary.get("location"), dict) else {}
            observed_location_values = {
                field_name: {
                    item.location.get(field_name)
                    for item in cluster_items
                    if item.location.get(field_name)
                }
                for field_name in ("region", "city", "district", "address")
            }

            def resolve_summary_location(field_name: str) -> Optional[str]:
                llm_value = llm_location.get(field_name)
                observed_value = location.get(field_name)
                if observed_value:
                    if llm_value and llm_value in observed_location_values[field_name]:
                        return llm_value
                    return observed_value
                if llm_value and (not observed_location_values[field_name] or llm_value in observed_location_values[field_name]):
                    return llm_value
                return None

            final_location = {
                "region": resolve_summary_location("region"),
                "city": resolve_summary_location("city"),
                "district": resolve_summary_location("district"),
                "address": resolve_summary_location("address"),
            }
            final_category = llm_summary.get("category")
            if final_category not in CATEGORY_NAMES:
                final_category = category_hint
            final_key_words = llm_summary.get("key_words") or key_words_hint
            signature = cluster_items[0].problem_signature if cluster_items else "локальная проблема"
            title = llm_summary.get("title") or build_problem_title(final_category, final_location, final_key_words, signature)
            summary = llm_summary.get("summary") or (
                cluster_items[0].short_summary
                if len(cluster_items) == 1
                else build_problem_summary_fallback(cluster_items, final_category, final_location, final_key_words)
            )

            independent_sources = {
                item.source.source_name or item.source.channel_name or item.source.source_url or item.item_id
                for item in cluster_items
            }
            duplicate_like_count = len(cluster_items) - len({item.fingerprint for item in cluster_items})
            affected_locations = {
                item.location.get("district") or item.location.get("city") or item.location.get("region")
                for item in cluster_items
                if item.location.get("district") or item.location.get("city") or item.location.get("region")
            }
            trend_points = build_trend_points(cluster_items)
            peak_point = max(trend_points, key=lambda point: point.mentions) if trend_points else None
            negative_ratio = round(sum(1 for item in cluster_items if item.sentiment == "negative") / max(1, len(cluster_items)), 2)
            first_seen = min(
                (ensure_datetime(item.source.published_at) for item in cluster_items if ensure_datetime(item.source.published_at)),
                default=None,
            )
            last_seen = max(
                (ensure_datetime(item.source.published_at) for item in cluster_items if ensure_datetime(item.source.published_at)),
                default=None,
            )
            recency_bonus = 0.0
            if last_seen is not None:
                age_days = max(0.0, (utc_now() - last_seen).total_seconds() / 86400)
                recency_bonus = max(0.0, 3.0 - min(age_days, 3.0))

            rank_score = round(
                len(cluster_items) * 1.7 + len(independent_sources) * 2.2 + len(affected_locations) * 0.8 + negative_ratio * 2.0 + recency_bonus,
                2,
            )

            card_id = hashlib.sha1(
                json.dumps(
                    {"title": title, "location": final_location, "source_ids": [item.item_id for item in cluster_items]},
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()[:16]

            cards.append(
                {
                    "card_id": card_id,
                    "rank_score": rank_score,
                    "title": title,
                    "summary": summary,
                    "category": final_category,
                    "key_words": final_key_words[:5],
                    "region": final_location["region"],
                    "city": final_location["city"],
                    "district": final_location["district"],
                    "address": final_location["address"],
                    "mentions_count": len(cluster_items),
                    "unique_sources_count": len(independent_sources),
                    "independent_sources_count": len(independent_sources),
                    "duplicate_like_count": duplicate_like_count,
                    "affected_locations_count": len(affected_locations),
                    "negative_ratio": negative_ratio,
                    "first_seen_at": first_seen,
                    "last_seen_at": last_seen,
                    "peak_date": peak_point.date if peak_point else None,
                    "peak_mentions": peak_point.mentions if peak_point else 0,
                    "trend_direction": detect_trend_direction(trend_points),
                    "trend_points": [point.model_dump() for point in trend_points],
                    "problem_signature": signature,
                    "cluster_reviewed_by_llm": cluster.reviewed_by_llm,
                    "source_ids": [item.item_id for item in cluster_items],
                    "sources": [
                        {
                            "id": item.item_id,
                            "channel_name": item.source.channel_name,
                            "source_name": item.source.source_name,
                            "source_type": item.source.source_type,
                            "source_url": item.source.source_url,
                            "published_at": ensure_datetime(item.source.published_at),
                            "snippet": item.short_summary,
                        }
                        for item in cluster_items[: min(len(cluster_items), 8)]
                    ],
                }
            )

        cards.sort(key=lambda item: item["rank_score"], reverse=True)
        return {
            "generated_at": utc_now(),
            "provider": DEFAULT_PROVIDER,
            "model": get_chat_model(),
            "embeddings_model": embeddings_model,
            "total_clusters": len(cards),
            "processed_items_count": processed_items_count,
            "ignored_non_negative_count": ignored_non_negative_count,
            "llm_item_analyses_used": llm_item_analyses_used,
            "llm_cluster_reviews_used": llm_cluster_reviews_used,
            "cards": cards[: payload.top_k],
        }


_service: Optional[GigaChatService] = None


def get_service() -> GigaChatService:
    global _service
    if _service is None:
        _service = GigaChatService()
    return _service


async def call_gigachat(messages: List[Dict[str, str]], max_tokens: int = 320) -> Dict[str, Any]:
    return await get_service().chat_completion(messages=messages, max_tokens=max_tokens)


async def analyze_message_llm(text: str, channel_name: str = "", channel_description: str = "") -> Dict[str, Any]:
    return await get_service().analyze_message(text, channel_name, channel_description)


async def classify_category_llm(text: str, channel_name: str = "", channel_description: str = "") -> Dict[str, Any]:
    result = await analyze_message_llm(text, channel_name, channel_description)
    return {
        "category": result["category"],
        "scores": result["scores"],
        "matched_keywords": result["matched_keywords"],
        "provider": result["provider"],
        "model": result["model"],
    }


async def extract_location_llm(text: str, channel_name: str = "", channel_description: str = "") -> Dict[str, Any]:
    result = await analyze_message_llm(text, channel_name, channel_description)
    return {
        "region": result["region"],
        "city": result["city"],
        "district": result["district"],
        "address": result["address"],
        "provider": result["provider"],
        "model": result["model"],
    }


async def extract_key_words_llm(text: str) -> Dict[str, Any]:
    result = await analyze_message_llm(text)
    return {
        "key_words": result["key_words"],
        "provider": result["provider"],
        "model": result["model"],
    }


async def count_tokens_llm(inputs: List[str], model: Optional[str] = None) -> Dict[str, Any]:
    raw = await get_service().count_tokens(inputs=inputs, model=model)
    items = [
        {"index": index, "tokens": safe_int(item.get("tokens")), "characters": safe_int(item.get("characters"))}
        for index, item in enumerate(raw["items"])
    ]
    return {
        "provider": DEFAULT_PROVIDER,
        "model": raw["model"],
        "items": items,
        "total_tokens": sum(item["tokens"] for item in items),
        "total_characters": sum(item["characters"] for item in items),
    }


async def build_problem_cards_llm(payload: ProblemCardsBuildRequest) -> Dict[str, Any]:
    return await get_service().build_problem_cards(payload)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        global _service
        if _service is not None:
            await _service.close()
            _service = None


app = FastAPI(
    title="Region Pulse Backend",
    description="API для анализа региональных сообщений через GigaChat",
    version="0.2.0",
    lifespan=lifespan,
)


@app.get("/")
async def root() -> Dict[str, str]:
    return {"message": "Region Pulse API is running", "docs": "/docs", "health": "/api/health"}


@app.get("/api/health")
async def healthcheck() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/categories")
async def get_categories() -> Dict[str, List[str]]:
    return {"categories": CATEGORY_NAMES}


@app.get("/api/provider", response_model=ProviderInfoResponse)
async def get_provider_info() -> Dict[str, Any]:
    return {
        "provider": get_provider(),
        "model": get_chat_model(),
        "embeddings_model": get_embeddings_model(),
        "max_concurrency": get_max_concurrency(),
        "cache_ttl_seconds": get_cache_ttl_seconds(),
    }


@app.post("/api/analyze-message", response_model=MessageAnalysisResponse)
async def analyze_message_endpoint(payload: ClassifyCategoryRequest) -> Dict[str, Any]:
    return await analyze_message_llm(payload.text, payload.channel_name, payload.channel_description)


@app.post("/api/analyze-message/batch", response_model=AnalyzeMessagesBatchResponse)
async def analyze_message_batch_endpoint(payload: BatchClassifyCategoryRequest) -> Dict[str, List[Dict[str, Any]]]:
    items = await asyncio.gather(
        *[
            analyze_message_llm(item.text, item.channel_name, item.channel_description)
            for item in payload.items
        ]
    )
    return {"items": items}


@app.post("/api/extract-key-words", response_model=ExtractKeyWordsResponse)
async def extract_key_words_endpoint(payload: ExtractKeyWordsRequest) -> Dict[str, Any]:
    return await extract_key_words_llm(payload.text)


@app.post("/api/classify-category", response_model=ClassifyCategoryResponse)
async def classify_category_endpoint(payload: ClassifyCategoryRequest) -> Dict[str, Any]:
    return await classify_category_llm(payload.text, payload.channel_name, payload.channel_description)


@app.post("/api/classify-category/batch")
async def classify_category_batch(payload: BatchClassifyCategoryRequest) -> Dict[str, List[Dict[str, Any]]]:
    items = await asyncio.gather(
        *[
            classify_category_llm(item.text, item.channel_name, item.channel_description)
            for item in payload.items
        ]
    )
    return {"items": items}


@app.post("/api/extract-location", response_model=ExtractLocationResponse)
async def extract_location_endpoint(payload: ClassifyCategoryRequest) -> Dict[str, Any]:
    return await extract_location_llm(payload.text, payload.channel_name, payload.channel_description)


@app.post("/api/extract-location/batch")
async def extract_location_batch(payload: BatchClassifyCategoryRequest) -> Dict[str, List[Dict[str, Any]]]:
    items = await asyncio.gather(
        *[
            extract_location_llm(item.text, item.channel_name, item.channel_description)
            for item in payload.items
        ]
    )
    return {"items": items}


@app.post("/api/token-count", response_model=TokenCountResponse)
async def token_count_endpoint(payload: TokenCountRequest) -> Dict[str, Any]:
    return await count_tokens_llm(payload.inputs, payload.model)


@app.post("/api/problem-cards/build", response_model=ProblemCardsBuildResponse)
async def build_problem_cards_endpoint(payload: ProblemCardsBuildRequest) -> Dict[str, Any]:
    return await build_problem_cards_llm(payload)
