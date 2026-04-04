import asyncio

from fastapi import HTTPException

from functions.main import (
    CATEGORY_NAMES,
    classify_category_llm,
    extract_key_words_llm,
    get_gigachat_credentials,
    extract_location_llm,
    normalize_text,
    parse_json_from_llm,
)


def test_normalize_text_normalizes_case_and_spaces() -> None:
    assert normalize_text("  Ёлка   И   ДВОР  ") == "елка и двор"


def test_parse_json_from_llm_accepts_plain_json() -> None:
    assert parse_json_from_llm('{"key":"value"}') == {"key": "value"}


def test_parse_json_from_llm_accepts_fenced_json() -> None:
    content = '```json\n{"key":"value"}\n```'

    assert parse_json_from_llm(content) == {"key": "value"}


def test_get_gigachat_credentials_builds_base64_from_client_pair(monkeypatch) -> None:
    monkeypatch.delenv("GIGACHAT_CREDENTIALS", raising=False)
    monkeypatch.delenv("GIGACHAT_CLIENT_ID", raising=False)
    monkeypatch.delenv("GIGACHAT_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("client_id", "client")
    monkeypatch.setenv("client_secret", "secret")

    assert get_gigachat_credentials() == "Y2xpZW50OnNlY3JldA=="


def test_classify_category_llm_normalizes_missing_fields(monkeypatch) -> None:
    async def mock_call_gigachat(messages):
        return {
            "category": "ЖКХ",
            "provider": "gigachat",
            "model": "GigaChat-2",
        }

    monkeypatch.setattr(
        "functions.main.call_gigachat",
        mock_call_gigachat,
    )

    result = asyncio.run(classify_category_llm("Тест"))

    assert result["category"] == "ЖКХ"
    assert result["matched_keywords"] == {name: [] for name in CATEGORY_NAMES}


def test_classify_category_llm_rejects_invalid_category(monkeypatch) -> None:
    async def mock_call_gigachat(messages):
        return {
            "category": "Спорт",
            "matched_keywords": {},
            "provider": "gigachat",
            "model": "GigaChat-2",
        }

    monkeypatch.setattr(
        "functions.main.call_gigachat",
        mock_call_gigachat,
    )

    try:
        asyncio.run(classify_category_llm("Тест"))
        assert False, "Expected HTTPException"
    except HTTPException as error:
        assert error.status_code == 502


def test_extract_location_llm_returns_payload(monkeypatch) -> None:
    async def mock_call_gigachat(messages):
        return {
            "region": "Ростовская область",
            "city": "Ростов-на-Дону",
            "district": "Аксайский район",
            "address": "ул. Большая Садовая",
            "provider": "gigachat",
            "model": "GigaChat-2",
        }

    monkeypatch.setattr(
        "functions.main.call_gigachat",
        mock_call_gigachat,
    )

    result = asyncio.run(extract_location_llm("Тест"))

    assert result["district"] == "Аксайский район"
    assert result["address"] == "ул. Большая Садовая"


def test_extract_key_words_llm_limits_and_cleans_output(monkeypatch) -> None:
    async def mock_call_gigachat(messages):
        return {
            "key_words": [" мусор ", "", "переполнены", "контейнеры", "жалобы", "ЖКХ"],
            "provider": "gigachat",
            "model": "GigaChat-2",
        }

    monkeypatch.setattr(
        "functions.main.call_gigachat",
        mock_call_gigachat,
    )

    result = asyncio.run(extract_key_words_llm("Тест"))

    assert result["key_words"] == [
        "мусор",
        "переполнены",
        "контейнеры",
        "жалобы",
        "ЖКХ",
    ]
