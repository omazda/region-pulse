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


def test_location_directory_endpoint() -> None:
    response = client.get("/api/location-directory")

    assert response.status_code == 200
    assert "аксай" in response.json()["locations"]


def test_provider_info_endpoint_defaults_to_rules() -> None:
    response = client.get("/api/provider")

    assert response.status_code == 200
    assert response.json()["provider"] == "rules"


def test_classify_category_endpoint() -> None:
    response = client.post(
        "/api/classify-category",
        json={
            "text": "На центральной улице огромные ямы и пробки",
            "channel_name": "Новости дорог",
            "channel_description": "Проблемы транспорта города",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "Дороги и транспорт"
    assert body["scores"]["Дороги и транспорт"] > 0


def test_batch_classify_category_endpoint() -> None:
    response = client.post(
        "/api/classify-category/batch",
        json={
            "items": [
                {
                    "text": "В поликлинике снова огромная очередь к врачу",
                    "channel_name": "Медицина региона",
                    "channel_description": "",
                },
                {
                    "text": "На заводе сообщили о сокращении сотрудников",
                    "channel_name": "Промышленный вестник",
                    "channel_description": "",
                },
            ]
        },
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["category"] == "Здравоохранение"
    assert items[1]["category"] == "Экономика и промышленность"


def test_extract_location_endpoint() -> None:
    response = client.post(
        "/api/extract-location",
        json={
            "text": "В Аксайском районе на ул. Большая Садовая переполнены контейнеры",
            "channel_name": "Ростов новости",
            "channel_description": "Новости аксайского района",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["region"] == "Ростовская область"
    assert body["district"] == "Аксайский район"
    assert body["address"] == "ул. Большая Садовая"


def test_extract_location_batch_endpoint() -> None:
    response = client.post(
        "/api/extract-location/batch",
        json={
            "items": [
                {
                    "text": "В Ростове на проспект Буденновский образовалась пробка",
                    "channel_name": "Транспорт города",
                    "channel_description": "",
                },
                {
                    "text": "Жители обсуждают фестиваль еды",
                    "channel_name": "Афиша",
                    "channel_description": "",
                },
            ]
        },
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["city"] == "Ростов-на-Дону"
    assert items[0]["address"] == "проспект Буденновский"
    assert items[1] == {
        "region": None,
        "city": None,
        "district": None,
        "address": None,
        "provider": "rules",
        "model": None,
    }


def test_classify_category_endpoint_uses_llm_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        "functions.main.classify_category_llm",
        lambda text, channel_name="", channel_description="": {
            "category": "ЖКХ",
            "scores": {
                "ЖКХ": 0,
                "Дороги и транспорт": 0,
                "Здравоохранение": 0,
                "Образование": 0,
                "Экология и ЧС": 0,
                "Экономика и промышленность": 0,
            },
            "matched_keywords": {
                "ЖКХ": [],
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
        "/api/classify-category?provider=llm",
        json={
            "text": "Тест",
            "channel_name": "",
            "channel_description": "",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "openrouter"
    assert body["model"] == "qwen/qwen3.6-plus"


def test_extract_location_endpoint_uses_llm_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        "functions.main.extract_location_llm",
        lambda text, channel_name="", channel_description="": {
            "region": "Ростовская область",
            "city": "Ростов-на-Дону",
            "district": None,
            "address": "ул. Большая Садовая",
            "provider": "openrouter",
            "model": "qwen/qwen3.6-plus",
        },
    )

    response = client.post(
        "/api/extract-location?provider=llm",
        json={
            "text": "Тест",
            "channel_name": "",
            "channel_description": "",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "openrouter"
    assert body["address"] == "ул. Большая Садовая"
