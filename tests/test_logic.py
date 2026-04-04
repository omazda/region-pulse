import asyncio

from functions.main import (
    CATEGORY_NAMES,
    GigaChatService,
    ProblemCardsBuildRequest,
    ProblemSourceInput,
    build_basic_auth_key,
    extract_location_hints,
    get_tls_verify,
    heuristic_category_scores,
    local_hashed_embedding,
    normalize_text,
    parse_json_from_llm,
    sanitize_keywords,
)


def test_normalize_text_normalizes_case_and_spaces() -> None:
    assert normalize_text("  Ёлка   И   ДВОР  ") == "елка и двор"


def test_parse_json_from_llm_accepts_plain_json() -> None:
    assert parse_json_from_llm('{"key":"value"}') == {"key": "value"}


def test_parse_json_from_llm_accepts_fenced_json() -> None:
    content = '```json\n{"key":"value"}\n```'

    assert parse_json_from_llm(content) == {"key": "value"}


def test_build_basic_auth_key_uses_client_pair(monkeypatch) -> None:
    monkeypatch.delenv("GIGACHAT_AUTH_KEY", raising=False)
    monkeypatch.delenv("GIGACHAT_CREDENTIALS", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("CLIENT_ID", "client")
    monkeypatch.setenv("CLIENT_SECRET", "secret")

    assert build_basic_auth_key() == "Y2xpZW50OnNlY3JldA=="


def test_get_tls_verify_can_disable_ssl_verification(monkeypatch) -> None:
    monkeypatch.delenv("GIGACHAT_CA_BUNDLE", raising=False)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    monkeypatch.setenv("GIGACHAT_VERIFY_SSL", "false")

    assert get_tls_verify() is False


def test_sanitize_keywords_filters_time_and_location_noise() -> None:
    keywords = sanitize_keywords(["Аксайском районе", "неделю", "не вывозят мусор", "контейнеры"])

    assert keywords == ["не вывозят мусор", "контейнеры"]


def test_heuristic_category_scores_detects_housing_problem() -> None:
    scores = heuristic_category_scores("Жители жалуются: мусор не вывозят уже неделю")

    assert scores["ЖКХ"] > 0
    assert max(scores, key=scores.get) == "ЖКХ"


def test_extract_location_hints_detects_aksay_district() -> None:
    location = extract_location_hints("В Аксайском районе на ул. Ленина затопило двор")

    assert location["region"] == "Ростовская область"
    assert location["district"] == "Аксайский район"


def test_analyze_message_skips_positive_posts_before_llm(monkeypatch) -> None:
    service = GigaChatService()

    async def fail_chat_completion(*args, **kwargs):
        raise AssertionError("LLM should not be called for positive messages")

    monkeypatch.setattr(service, "chat_completion", fail_chat_completion)

    result = asyncio.run(
        service.analyze_message("Спасибо, мусор наконец вывезли, двор убрали и стало чисто")
    )
    asyncio.run(service.close())

    assert result["sentiment"] == "positive"
    assert result["analysis_source"] == "sentiment_prefilter"
    assert result["requires_problem_processing"] is False
    assert result["llm_skipped_reason"] == "positive_sentiment_prefilter"


def test_local_hashed_embedding_is_stable() -> None:
    first = local_hashed_embedding("не вывозят мусор в аксайском районе")
    second = local_hashed_embedding("не вывозят мусор в аксайском районе")

    assert first == second
    assert len(first) == 64


def test_service_build_problem_cards_clusters_similar_items(monkeypatch) -> None:
    service = GigaChatService()

    async def fake_create_embeddings(texts):
        return {
            "vectors": [
                [1.0, 0.0],
                [0.97, 0.03],
                [-1.0, 0.0],
            ],
            "model": "Embeddings",
        }

    async def fake_summarize_problem_cluster(items, location, category_hint, key_words_hint, summarization_items):
        return {}

    monkeypatch.setattr(service, "create_embeddings", fake_create_embeddings)
    monkeypatch.setattr(service, "summarize_problem_cluster", fake_summarize_problem_cluster)

    payload = ProblemCardsBuildRequest(
        items=[
            ProblemSourceInput(
                id="1",
                text="В Аксайском районе не вывозят мусор уже неделю",
                channel_name="Аксай Новости",
                published_at="2026-04-04T00:00:00+00:00",
            ),
            ProblemSourceInput(
                id="2",
                text="Контейнеры переполнены, вывоз мусора сорван",
                channel_name="ЖКХ Ростов",
                published_at="2026-04-05T00:00:00+00:00",
            ),
            ProblemSourceInput(
                id="3",
                text="Нет записи к терапевту в поликлинике",
                channel_name="Медицина Дон",
                published_at="2026-04-05T00:00:00+00:00",
            ),
        ],
        llm_item_analysis=False,
        llm_cluster_review=False,
    )

    result = asyncio.run(service.build_problem_cards(payload))
    asyncio.run(service.close())

    assert result["total_clusters"] == 2
    assert result["llm_item_analyses_used"] == 0
    assert result["llm_cluster_reviews_used"] == 0
    top_card = result["cards"][0]
    assert top_card["mentions_count"] == 2
    assert top_card["category"] in CATEGORY_NAMES
    assert top_card["region"] == "Ростовская область"


def test_service_build_problem_cards_uses_llm_item_analysis_when_enabled(monkeypatch) -> None:
    service = GigaChatService()

    async def fake_create_embeddings(texts):
        return {"vectors": [[1.0, 0.0]], "model": "Embeddings"}

    async def fake_analyze_message(text, channel_name="", channel_description=""):
        return {
            "category": "ЖКХ",
            "scores": {name: (100 if name == "ЖКХ" else 0) for name in CATEGORY_NAMES},
            "matched_keywords": {name: ([] if name != "ЖКХ" else ["мусор"]) for name in CATEGORY_NAMES},
            "key_words": ["мусор", "контейнеры"],
            "region": "Ростовская область",
            "city": None,
            "district": "Аксайский район",
            "address": None,
            "sentiment": "negative",
            "problem_signature": "не вывозят мусор",
            "short_summary": "Жители жалуются на срыв вывоза мусора.",
            "provider": "gigachat",
            "model": "GigaChat-2-Lite",
            "analysis_source": "llm",
            "cached": False,
            "usage": None,
        }

    async def fake_summarize_problem_cluster(items, location, category_hint, key_words_hint, summarization_items):
        return {}

    monkeypatch.setattr(service, "create_embeddings", fake_create_embeddings)
    monkeypatch.setattr(service, "analyze_message", fake_analyze_message)
    monkeypatch.setattr(service, "summarize_problem_cluster", fake_summarize_problem_cluster)

    payload = ProblemCardsBuildRequest(
        items=[
            ProblemSourceInput(
                id="1",
                text="В Аксайском районе уже неделю не вывозят мусор",
                channel_name="Аксай Новости",
                published_at="2026-04-04T00:00:00+00:00",
            )
        ],
        llm_item_analysis=True,
        llm_item_limit=5,
        llm_cluster_review=False,
    )

    result = asyncio.run(service.build_problem_cards(payload))
    asyncio.run(service.close())

    assert result["llm_item_analyses_used"] == 1
    assert result["cards"][0]["category"] == "ЖКХ"
def test_service_build_problem_cards_filters_positive_items(monkeypatch) -> None:
    service = GigaChatService()

    async def fake_create_embeddings(texts):
        return {
            "vectors": [
                [1.0, 0.0],
                [0.9, 0.1],
            ],
            "model": "Embeddings",
        }

    async def fake_analyze_message(text, channel_name="", channel_description=""):
        if "Спасибо" in text:
            return {
                "category": "Р–РљРҐ",
                "scores": {name: (100 if name == "Р–РљРҐ" else 0) for name in CATEGORY_NAMES},
                "matched_keywords": {name: ([] if name != "Р–РљРҐ" else ["СѓР±СЂР°Р»Рё РјСѓСЃРѕСЂ"]) for name in CATEGORY_NAMES},
                "key_words": ["СѓР±СЂР°Р»Рё РјСѓСЃРѕСЂ"],
                "region": "Р РѕСЃС‚РѕРІСЃРєР°СЏ РѕР±Р»Р°СЃС‚СЊ",
                "city": "РђРєСЃР°Р№",
                "district": "РђРєСЃР°Р№СЃРєРёР№ СЂР°Р№РѕРЅ",
                "address": None,
                "sentiment": "positive",
                "problem_signature": "СѓР±СЂР°Р»Рё РјСѓСЃРѕСЂ",
                "short_summary": "Р–РёС‚РµР»Рё Р±Р»Р°РіРѕРґР°СЂСЏС‚ Р·Р° СѓР±РѕСЂРєСѓ РјСѓСЃРѕСЂР°.",
                "provider": "local-fallback",
                "model": None,
                "analysis_source": "sentiment_prefilter",
                "requires_problem_processing": False,
                "llm_skipped_reason": "positive_sentiment_prefilter",
                "cached": False,
                "usage": None,
            }
        return {
            "category": "Р–РљРҐ",
            "scores": {name: (100 if name == "Р–РљРҐ" else 0) for name in CATEGORY_NAMES},
            "matched_keywords": {name: ([] if name != "Р–РљРҐ" else ["РЅРµ РІС‹РІРѕР·СЏС‚ РјСѓСЃРѕСЂ"]) for name in CATEGORY_NAMES},
            "key_words": ["РЅРµ РІС‹РІРѕР·СЏС‚ РјСѓСЃРѕСЂ", "РєРѕРЅС‚РµР№РЅРµСЂС‹"],
            "region": "Р РѕСЃС‚РѕРІСЃРєР°СЏ РѕР±Р»Р°СЃС‚СЊ",
            "city": "РђРєСЃР°Р№",
            "district": "РђРєСЃР°Р№СЃРєРёР№ СЂР°Р№РѕРЅ",
            "address": None,
            "sentiment": "negative",
            "problem_signature": "СЃСЂС‹РІ РІС‹РІРѕР·Р° РјСѓСЃРѕСЂР°",
            "short_summary": "Р’ РђРєСЃР°Р№СЃРєРѕРј СЂР°Р№РѕРЅРµ РЅРµ РІС‹РІРѕР·СЏС‚ РјСѓСЃРѕСЂ.",
            "provider": "gigachat",
            "model": "GigaChat-2",
            "analysis_source": "llm",
            "requires_problem_processing": True,
            "llm_skipped_reason": None,
            "cached": False,
            "usage": None,
        }

    async def fake_summarize_problem_cluster(items, location, category_hint, key_words_hint, summarization_items):
        return {}

    monkeypatch.setattr(service, "create_embeddings", fake_create_embeddings)
    monkeypatch.setattr(service, "analyze_message", fake_analyze_message)
    monkeypatch.setattr(service, "summarize_problem_cluster", fake_summarize_problem_cluster)

    payload = ProblemCardsBuildRequest(
        items=[
            ProblemSourceInput(
                id="1",
                text="Р’ РђРєСЃР°Р№СЃРєРѕРј СЂР°Р№РѕРЅРµ РЅРµ РІС‹РІРѕР·СЏС‚ РјСѓСЃРѕСЂ СѓР¶Рµ РЅРµСЃРєРѕР»СЊРєРѕ РґРЅРµР№",
                channel_name="РђРєСЃР°Р№ РќРѕРІРѕСЃС‚Рё",
                published_at="2026-04-04T00:00:00+00:00",
            ),
            ProblemSourceInput(
                id="2",
                text="Спасибо, мусор вывезли и двор убрали",
                channel_name="РђРєСЃР°Р№ РќРѕРІРѕСЃС‚Рё",
                published_at="2026-04-04T01:00:00+00:00",
            ),
        ],
        llm_item_analysis=True,
        llm_item_limit=5,
        llm_cluster_review=False,
        negative_only=True,
    )

    result = asyncio.run(service.build_problem_cards(payload))
    asyncio.run(service.close())

    assert result["ignored_non_negative_count"] == 1
    assert result["processed_items_count"] == 1
    assert result["total_clusters"] == 1
    assert result["cards"][0]["mentions_count"] == 1
