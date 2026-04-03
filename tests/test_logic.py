from functions.main import (
    classify_category,
    contains_keyword,
    extract_location,
    normalize_text,
)


def test_normalize_text_normalizes_case_and_spaces() -> None:
    assert normalize_text("  Ёлка   И   ДВОР  ") == "елка и двор"


def test_contains_keyword_uses_word_boundaries() -> None:
    assert contains_keyword("новости тсж района", "тсж") is True
    assert contains_keyword("закупки региона", "ук") is False


def test_classify_category_returns_housing_category() -> None:
    result = classify_category(
        text="В Аксайском районе пятый день не вывозят мусор, контейнеры переполнены",
        channel_name="Ростов новости",
        channel_description="Новости аксайского района и суворовского ТСЖ",
    )

    assert result["category"] == "ЖКХ"
    assert result["scores"]["ЖКХ"] > 0
    assert "мусор" in result["matched_keywords"]["ЖКХ"]


def test_classify_category_uses_channel_context() -> None:
    result = classify_category(
        text="Жители жалуются на качество обслуживания",
        channel_name="ТСЖ Суворовский",
        channel_description="Обсуждаем управляющую компанию и двор",
    )

    assert result["category"] == "ЖКХ"
    assert "тсж" in result["matched_keywords"]["ЖКХ"]


def test_classify_category_returns_undefined_when_no_matches() -> None:
    result = classify_category(
        text="В регионе прошел фестиваль уличной еды",
        channel_name="Афиша Ростова",
        channel_description="Культурные события и досуг",
    )

    assert result["category"] == "Не определено"


def test_extract_location_normalizes_district_and_city() -> None:
    result = extract_location(
        text="В Аксайском районе на ул. Большая Садовая пятый день не вывозят мусор",
        channel_name="Ростов новости",
        channel_description="Новости аксайского района и суворовского ТСЖ",
    )

    assert result["region"] == "Ростовская область"
    assert result["city"] == "Ростов-на-Дону"
    assert result["district"] == "Аксайский район"
    assert result["address"] == "ул. Большая Садовая"


def test_extract_location_returns_nulls_when_location_missing() -> None:
    result = extract_location(
        text="Жители обсуждают качество обслуживания без указания адреса",
        channel_name="Городские новости",
        channel_description="Локальные события",
    )

    assert result == {
        "region": None,
        "city": None,
        "district": None,
        "address": None,
    }
