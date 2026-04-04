from fastapi.testclient import TestClient

from functions.main import app


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


def test_provider_info_endpoint_returns_llm() -> None:
    response = client.get("/api/provider")

    assert response.status_code == 200
    assert response.json()["provider"] == "llm"


def test_classify_category_endpoint_uses_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        "functions.main.classify_category_llm",
        lambda text, channel_name="", channel_description="": {
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
            "provider": "openrouter",
            "model": "qwen/qwen3.6-plus",
        },
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
    assert body["provider"] == "openrouter"


def test_batch_classify_category_endpoint_uses_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        "functions.main.classify_category_llm",
        lambda text, channel_name="", channel_description="": {
            "category": "ЖКХ" if "мусор" in text.lower() else "Здравоохранение",
            "scores": {
                "ЖКХ": 100 if "мусор" in text.lower() else 0,
                "Дороги и транспорт": 0,
                "Здравоохранение": 100 if "врач" in text.lower() else 0,
                "Образование": 0,
                "Экология и ЧС": 0,
                "Экономика и промышленность": 0,
            },
            "matched_keywords": {
                "ЖКХ": ["мусор"] if "мусор" in text.lower() else [],
                "Дороги и транспорт": [],
                "Здравоохранение": ["врач"] if "врач" in text.lower() else [],
                "Образование": [],
                "Экология и ЧС": [],
                "Экономика и промышленность": [],
            },
            "provider": "openrouter",
            "model": "qwen/qwen3.6-plus",
        },
    )

    response = client.post(
        "/api/classify-category/batch",
        json={
            "items": [
                {
                    "text": "Мусор не вывозят",
                    "channel_name": "",
                    "channel_description": "",
                },
                {
                    "text": "Нет записи к врачу",
                    "channel_name": "",
                    "channel_description": "",
                },
            ]
        },
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["category"] == "ЖКХ"
    assert items[1]["category"] == "Здравоохранение"


def test_extract_location_endpoint_uses_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        "functions.main.extract_location_llm",
        lambda text, channel_name="", channel_description="": {
            "region": "Ростовская область",
            "city": "Ростов-на-Дону",
            "district": "Аксайский район",
            "address": "ул. Большая Садовая",
            "provider": "openrouter",
            "model": "qwen/qwen3.6-plus",
        },
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
    assert body["provider"] == "openrouter"


def test_extract_location_batch_endpoint_uses_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        "functions.main.extract_location_llm",
        lambda text, channel_name="", channel_description="": {
            "region": "Ростовская область",
            "city": "Ростов-на-Дону" if "ростове" in text.lower() else None,
            "district": None,
            "address": "проспект Буденновский" if "буденновский" in text.lower() else None,
            "provider": "openrouter",
            "model": "qwen/qwen3.6-plus",
        },
    )

    response = client.post(
        "/api/extract-location/batch",
        json={
            "items": [
                {
                    "text": "В Ростове на проспект Буденновский образовалась пробка",
                    "channel_name": "",
                    "channel_description": "",
                },
                {
                    "text": "Жители обсуждают фестиваль еды",
                    "channel_name": "",
                    "channel_description": "",
                },
            ]
        },
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["city"] == "Ростов-на-Дону"
    assert items[1]["address"] is None


def test_extract_key_words_endpoint_uses_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        "functions.main.extract_key_words_llm",
        lambda text: {
            "key_words": ["мусор", "переполнены"],
            "provider": "openrouter",
            "model": "qwen/qwen3.6-plus",
        },
    )

    response = client.post(
        "/api/extract-key-words",
        json={"text": "В Аксайском районе не вывозят мусор"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["key_words"] == ["мусор", "переполнены"]
    assert body["provider"] == "openrouter"
