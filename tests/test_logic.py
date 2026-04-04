from fastapi import HTTPException

from functions.main import (
    CATEGORY_NAMES,
    classify_category_llm,
    extract_key_words_llm,
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


def test_classify_category_llm_normalizes_missing_fields(monkeypatch) -> None:
    monkeypatch.setattr(
        "functions.main.call_openrouter",
        lambda messages: {
            "category": "ЖКХ",
            "provider": "openrouter",
            "model": "qwen/qwen3.6-plus",
        },
    )

    result = classify_category_llm("Тест")

    assert result["category"] == "ЖКХ"
    assert result["scores"] == {name: 0 for name in CATEGORY_NAMES}
    assert result["matched_keywords"] == {name: [] for name in CATEGORY_NAMES}


def test_classify_category_llm_rejects_invalid_category(monkeypatch) -> None:
    monkeypatch.setattr(
        "functions.main.call_openrouter",
        lambda messages: {
            "category": "Спорт",
            "scores": {},
            "matched_keywords": {},
            "provider": "openrouter",
            "model": "qwen/qwen3.6-plus",
        },
    )

    try:
        classify_category_llm("Тест")
        assert False, "Expected HTTPException"
    except HTTPException as error:
        assert error.status_code == 502


def test_extract_location_llm_returns_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "functions.main.call_openrouter",
        lambda messages: {
            "region": "Ростовская область",
            "city": "Ростов-на-Дону",
            "district": "Аксайский район",
            "address": "ул. Большая Садовая",
            "provider": "openrouter",
            "model": "qwen/qwen3.6-plus",
        },
    )

    result = extract_location_llm("Тест")

    assert result["district"] == "Аксайский район"
    assert result["address"] == "ул. Большая Садовая"


def test_extract_key_words_llm_limits_and_cleans_output(monkeypatch) -> None:
    monkeypatch.setattr(
        "functions.main.call_openrouter",
        lambda messages: {
            "key_words": [" мусор ", "", "переполнены", "контейнеры", "жалобы", "ЖКХ"],
            "provider": "openrouter",
            "model": "qwen/qwen3.6-plus",
        },
    )

    result = extract_key_words_llm("Тест")

    assert result["key_words"] == [
        "мусор",
        "переполнены",
        "контейнеры",
        "жалобы",
        "ЖКХ",
    ]
