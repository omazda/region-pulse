from datetime import datetime, timezone
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from functions.main import app, get_chat_model


client = TestClient(app)


def test_root_endpoint() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["message"] == "Region Pulse API is running"


def test_health_endpoint() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_categories_endpoint() -> None:
    response = client.get("/api/categories")

    assert response.status_code == 200
    assert "ЖКХ" in response.json()["categories"]


def test_provider_info_endpoint_returns_gigachat() -> None:
    response = client.get("/api/provider")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "gigachat"
    assert body["model"] == get_chat_model()


def test_analyze_message_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "functions.main.analyze_message_llm",
        AsyncMock(
            return_value={
                "category": "ЖКХ",
                "scores": {
                    "ЖКХ": 92,
                    "Дороги и транспорт": 8,
                    "Здравоохранение": 0,
                    "Образование": 0,
                    "Экология и ЧС": 14,
                    "Экономика и промышленность": 0,
                },
                "matched_keywords": {
                    "ЖКХ": ["мусор", "контейнеры"],
                    "Дороги и транспорт": [],
                    "Здравоохранение": [],
                    "Образование": [],
                    "Экология и ЧС": [],
                    "Экономика и промышленность": [],
                },
                "key_words": ["мусор", "контейнеры", "вывоз"],
                "region": "Ростовская область",
                "city": None,
                "district": "Аксайский район",
                "address": None,
                "sentiment": "negative",
                "problem_signature": "не вывозят мусор",
                "short_summary": "Жители жалуются на переполненные контейнеры и срыв графика вывоза.",
                "provider": "gigachat",
                "model": "GigaChat-2-Lite",
                "cached": False,
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 45,
                    "total_tokens": 165,
                    "precached_prompt_tokens": 0,
                },
            }
        ),
    )

    response = client.post(
        "/api/analyze-message",
        json={
            "text": "В Аксайском районе уже неделю не вывозят мусор",
            "channel_name": "Ростов новости",
            "channel_description": "",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "ЖКХ"
    assert body["district"] == "Аксайский район"
    assert body["provider"] == "gigachat"


def test_classify_category_endpoint_uses_async_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        "functions.main.classify_category_llm",
        AsyncMock(
            return_value={
                "category": "ЖКХ",
                "scores": {
                    "ЖКХ": 100,
                    "Дороги и транспорт": 0,
                    "Здравоохранение": 0,
                    "Образование": 0,
                    "Экология и ЧС": 0,
                    "Экономика и промышленность": 0,
                },
                "matched_keywords": {
                    "ЖКХ": ["мусор", "контейнеры"],
                    "Дороги и транспорт": [],
                    "Здравоохранение": [],
                    "Образование": [],
                    "Экология и ЧС": [],
                    "Экономика и промышленность": [],
                },
                "provider": "gigachat",
                "model": "GigaChat-2-Lite",
            }
        ),
    )

    response = client.post(
        "/api/classify-category",
        json={
            "text": "В Аксайском районе пятый день не вывозят мусор",
            "channel_name": "Ростов новости",
            "channel_description": "",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "ЖКХ"
    assert body["provider"] == "gigachat"


def test_batch_classify_category_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "functions.main.classify_category_llm",
        AsyncMock(
            side_effect=[
                {
                    "category": "ЖКХ",
                    "scores": {
                        "ЖКХ": 100,
                        "Дороги и транспорт": 0,
                        "Здравоохранение": 0,
                        "Образование": 0,
                        "Экология и ЧС": 0,
                        "Экономика и промышленность": 0,
                    },
                    "matched_keywords": {name: ([] if name != "ЖКХ" else ["мусор"]) for name in [
                        "ЖКХ",
                        "Дороги и транспорт",
                        "Здравоохранение",
                        "Образование",
                        "Экология и ЧС",
                        "Экономика и промышленность",
                    ]},
                    "provider": "gigachat",
                    "model": "GigaChat-2-Lite",
                },
                {
                    "category": "Здравоохранение",
                    "scores": {
                        "ЖКХ": 0,
                        "Дороги и транспорт": 0,
                        "Здравоохранение": 100,
                        "Образование": 0,
                        "Экология и ЧС": 0,
                        "Экономика и промышленность": 0,
                    },
                    "matched_keywords": {name: ([] if name != "Здравоохранение" else ["врач"]) for name in [
                        "ЖКХ",
                        "Дороги и транспорт",
                        "Здравоохранение",
                        "Образование",
                        "Экология и ЧС",
                        "Экономика и промышленность",
                    ]},
                    "provider": "gigachat",
                    "model": "GigaChat-2-Lite",
                },
            ]
        ),
    )

    response = client.post(
        "/api/classify-category/batch",
        json={
            "items": [
                {"text": "Мусор не вывозят", "channel_name": "", "channel_description": ""},
                {"text": "Нет записи к врачу", "channel_name": "", "channel_description": ""},
            ]
        },
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["category"] == "ЖКХ"
    assert items[1]["category"] == "Здравоохранение"


def test_extract_location_endpoint_uses_async_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        "functions.main.extract_location_llm",
        AsyncMock(
            return_value={
                "region": "Ростовская область",
                "city": "Ростов-на-Дону",
                "district": "Аксайский район",
                "address": "ул. Большая Садовая",
                "provider": "gigachat",
                "model": "GigaChat-2-Lite",
            }
        ),
    )

    response = client.post(
        "/api/extract-location",
        json={
            "text": "В Аксайском районе на ул. Большая Садовая переполнены контейнеры",
            "channel_name": "",
            "channel_description": "",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["district"] == "Аксайский район"
    assert body["provider"] == "gigachat"


def test_extract_key_words_endpoint_uses_async_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        "functions.main.extract_key_words_llm",
        AsyncMock(
            return_value={
                "key_words": ["мусор", "контейнеры"],
                "provider": "gigachat",
                "model": "GigaChat-2-Lite",
            }
        ),
    )

    response = client.post(
        "/api/extract-key-words",
        json={"text": "В Аксайском районе не вывозят мусор"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["key_words"] == ["мусор", "контейнеры"]
    assert body["provider"] == "gigachat"


def test_problem_cards_build_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "functions.main.build_problem_cards_llm",
        AsyncMock(
            return_value={
                "generated_at": datetime(2026, 4, 4, tzinfo=timezone.utc),
                "provider": "gigachat",
                "model": "GigaChat-2-Lite",
                "embeddings_model": "Embeddings",
                "total_clusters": 1,
                "llm_item_analyses_used": 1,
                "llm_cluster_reviews_used": 0,
                "cards": [
                    {
                        "card_id": "card-1",
                        "rank_score": 9.2,
                        "title": "Не вывозят мусор в Аксайском районе",
                        "summary": "Жители нескольких населенных пунктов жалуются на срыв вывоза отходов.",
                        "category": "ЖКХ",
                        "key_words": ["мусор", "вывоз", "контейнеры"],
                        "region": "Ростовская область",
                        "city": None,
                        "district": "Аксайский район",
                        "address": None,
                        "mentions_count": 2,
                        "unique_sources_count": 2,
                        "independent_sources_count": 2,
                        "duplicate_like_count": 0,
                        "affected_locations_count": 1,
                        "negative_ratio": 1.0,
                        "first_seen_at": "2026-04-02T00:00:00+00:00",
                        "last_seen_at": "2026-04-04T00:00:00+00:00",
                        "peak_date": "2026-04-04",
                        "peak_mentions": 2,
                        "trend_direction": "up",
                        "trend_points": [{"date": "2026-04-04", "mentions": 2}],
                        "problem_signature": "не вывозят мусор",
                        "cluster_reviewed_by_llm": False,
                        "source_ids": ["src-1", "src-2"],
                        "sources": [
                            {
                                "id": "src-1",
                                "channel_name": "Аксай Новости",
                                "source_name": None,
                                "source_type": "telegram",
                                "source_url": "https://example.com/1",
                                "published_at": "2026-04-04T00:00:00+00:00",
                                "snippet": "Контейнеры не вывозились уже 10 дней.",
                            }
                        ],
                    }
                ],
            }
        ),
    )

    response = client.post(
        "/api/problem-cards/build",
        json={
            "items": [
                {
                    "id": "src-1",
                    "text": "Контейнеры не вывозились уже 10 дней",
                    "channel_name": "Аксай Новости",
                    "source_type": "telegram",
                    "source_url": "https://example.com/1",
                    "published_at": "2026-04-04T00:00:00+00:00",
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_clusters"] == 1
    assert body["cards"][0]["category"] == "ЖКХ"
