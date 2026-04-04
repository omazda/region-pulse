# Region Pulse

Backend для анализа региональных сообщений на `FastAPI`, теперь с провайдером `GigaChat`.

Что умеет сервис:

- классифицировать сообщения по отрасли;
- извлекать географию и ключевые слова;
- делать объединённый анализ одного сообщения за один LLM-вызов;
- считать токены перед отправкой больших батчей;
- собирать карточки проблем через embeddings + кластеризацию + суммаризацию;
- автоматически получать и обновлять `access_token`.

## Стек

- `FastAPI`
- `httpx`
- `python-dotenv`
- `pytest`

## Переменные окружения

Минимальный пример `.env`:

```env
REGION_PULSE_PROVIDER=gigachat
GIGACHAT_MODEL=GigaChat-2-Lite
GIGACHAT_EMBEDDINGS_MODEL=Embeddings-2
GIGACHAT_SCOPE=GIGACHAT_API_PERS
CLIENT_ID=...
CLIENT_SECRET=...
# Если сертификат уже доверен системой, строка ниже не нужна.
# GIGACHAT_CA_BUNDLE=D:\region-pulse\certs\russian_trusted_root_ca_pem.crt
# Только для локальной диагностики, небезопасно для production:
# GIGACHAT_VERIFY_SSL=false
```

Поддерживаются варианты авторизации:

- `GIGACHAT_AUTH_KEY` или `GIGACHAT_CREDENTIALS`
- либо пара `CLIENT_ID` + `CLIENT_SECRET`
- для мягкой миграции также читается старый `OPENROUTER_API_KEY`, если там лежит basic key от GigaChat

Полезные опции:

- `ANALYSIS_CACHE_TTL_SECONDS` — TTL кэша анализа одного сообщения
- `ANALYSIS_CACHE_LIMIT` — лимит записей в кэше
- `GIGACHAT_MAX_CONCURRENCY` — число одновременных запросов
- `GIGACHAT_VERIFY_SSL=false` — отключает TLS-проверку для локальной диагностики

Важно:

- для `ngw.devices.sberbank.ru:9443` обычно нужен корневой сертификат Минцифры / доверенный CA bundle;
- если корневой сертификат уже установлен в системе и доверен, `GIGACHAT_CA_BUNDLE` можно не указывать;
- для быстрой диагностики можно включить `GIGACHAT_VERIFY_SSL=false`, но это отключает проверку TLS и не подходит для production;
- по документации GigaChat у физлиц обычно доступен один одновременный поток, поэтому по умолчанию стоит `1`.

## Запуск

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn functions.main:app --reload
```

## Основные эндпоинты

- `GET /`
- `GET /api/health`
- `GET /api/categories`
- `GET /api/provider`
- `POST /api/analyze-message`
- `POST /api/analyze-message/batch`
- `POST /api/classify-category`
- `POST /api/classify-category/batch`
- `POST /api/extract-location`
- `POST /api/extract-location/batch`
- `POST /api/extract-key-words`
- `POST /api/token-count`
- `POST /api/problem-cards/build`

## Почему это экономнее для GigaChat-2-Lite

- классификация, ключевые слова и география собираются одним вызовом вместо трёх;
- результаты анализа кэшируются по нормализованному тексту;
- карточки проблем строятся через embeddings, LLM-анализ элементов батча, LLM-review спорных слияний и суммаризацию кластера;
- если GigaChat временно недоступен, одиночный анализ падает в локальные эвристики, а карточки проблем могут собираться на локальных hash-embeddings.

## Как проверить руками

Сценарий 1. Проверить, что анализ реально идёт через LLM:

```bash
curl -X POST http://127.0.0.1:8000/api/analyze-message ^
  -H "Content-Type: application/json" ^
  -d "{\"text\":\"В Аксайском районе уже неделю не вывозят мусор, контейнеры переполнены\",\"channel_name\":\"Аксай Новости\",\"channel_description\":\"Жалобы жителей\"}"
```

Что смотреть в ответе:

- `provider` должен быть `gigachat`
- `analysis_source` должен быть `llm`
- `category` ожидаемо должен быть `ЖКХ`
- `district` или `region` должны быть заполнены

Сценарий 2. Проверить кэш:

- отправьте тот же запрос второй раз
- в ответе должно стать `cached=true`

Сценарий 3. Проверить сборку карточек проблем:

```bash
curl -X POST http://127.0.0.1:8000/api/problem-cards/build ^
  -H "Content-Type: application/json" ^
  -d @answer_example.json
```

Что смотреть в ответе:

- `total_clusters` должен быть больше 0
- `llm_item_analyses_used` должен быть больше 0
- `cards[0].mentions_count` должен быть больше 1 для повторяющейся проблемы
- `cards[0].summary` должен быть не пустым

Сценарий 4. Проверить расход токенов перед батчем:

```bash
curl -X POST http://127.0.0.1:8000/api/token-count ^
  -H "Content-Type: application/json" ^
  -d "{\"inputs\":[\"В Аксайском районе не вывозят мусор\",\"Нет записи к терапевту в поликлинике\"]}"
```

Это удобно, чтобы быстро оценить бюджет перед большими прогонами.

## Тесты

```bash
python -m pytest -q
```

## Отдельный скрипт для токена

Есть утилита `get_access_tocken.py`. Она не нужна самому backend, но удобна для ручной проверки авторизации:

```bash
python get_access_tocken.py
```
