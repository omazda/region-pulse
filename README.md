# Region Pulse

LLM-only backend для анализа региональных сообщений, новостей и обращений граждан.

Сервис использует модель через OpenRouter и умеет:

- классифицировать сообщение по категории;
- извлекать географию из текста;
- выделять ключевые слова;
- обрабатывать одиночные и batch-запросы;
- отдавать HTTP API и Swagger-документацию.

## Что Умеет API

### Классификация

`POST /api/classify-category`

Возвращает:

- `category` — итоговая категория;
- `scores` — оценка уверенности по каждой категории;
- `matched_keywords` — ключевые слова, связанные с категориями;
- `provider` — источник ответа, сейчас `openrouter`;
- `model` — имя модели.

Поддерживаемые категории:

- `ЖКХ`
- `Дороги и транспорт`
- `Здравоохранение`
- `Образование`
- `Экология и ЧС`
- `Экономика и промышленность`

### Извлечение Географии

`POST /api/extract-location`

Возвращает:

- `region`
- `city`
- `district`
- `address`
- `provider`
- `model`

### Ключевые Слова

`POST /api/extract-key-words`

Возвращает:

- `key_words`
- `provider`
- `model`

## Стек

- `FastAPI`
- `Pydantic`
- `httpx`
- `python-dotenv`
- `pytest`

## Структура Проекта

```text
region-pulse/
├── functions/
│   └── main.py
├── tests/
│   ├── test_api.py
│   └── test_logic.py
├── .env
├── .gitignore
├── pytest.ini
├── README.md
└── requirements.txt
```

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Настройка `.env`

Минимальный пример:

```env
OPENROUTER_API_KEY=your_api_key
REGION_PULSE_PROVIDER=llm
OPENROUTER_MODEL=qwen/qwen3.6-plus:free
OPENROUTER_APP_URL=http://localhost:8000
OPENROUTER_APP_NAME=region-pulse
```

Переменные:

- `OPENROUTER_API_KEY` — ключ OpenRouter;
- `REGION_PULSE_PROVIDER` — текущий режим, сейчас должен быть `llm`;
- `OPENROUTER_MODEL` — модель для вызова;
- `OPENROUTER_APP_URL` — ваш локальный URL приложения;
- `OPENROUTER_APP_NAME` — имя приложения для заголовков OpenRouter.

Важно:

- проект сейчас работает только через LLM;
- локального `rules`-режима больше нет;
- `.env` не должен попадать в git.

## Запуск

```bash
.venv/bin/uvicorn functions.main:app --reload
```

После запуска:

- root: `http://127.0.0.1:8000/`
- docs: `http://127.0.0.1:8000/docs`
- health: `http://127.0.0.1:8000/api/health`

## Эндпоинты

- `GET /`
- `GET /api/health`
- `GET /api/provider`
- `GET /api/categories`
- `POST /api/classify-category`
- `POST /api/classify-category/batch`
- `POST /api/extract-location`
- `POST /api/extract-location/batch`
- `POST /api/extract-key-words`

## Примеры Запросов

### `POST /api/classify-category`

```json
{
  "text": "В Аксайском районе пятый день не вывозят мусор, контейнеры переполнены",
  "channel_name": "Ростов новости",
  "channel_description": "Новости района"
}
```

Пример ответа:

```json
{
  "category": "ЖКХ",
  "scores": {
    "ЖКХ": 95,
    "Дороги и транспорт": 5,
    "Здравоохранение": 0,
    "Образование": 0,
    "Экология и ЧС": 10,
    "Экономика и промышленность": 0
  },
  "matched_keywords": {
    "ЖКХ": ["мусор", "контейнеры"],
    "Дороги и транспорт": [],
    "Здравоохранение": [],
    "Образование": [],
    "Экология и ЧС": [],
    "Экономика и промышленность": []
  },
  "provider": "openrouter",
  "model": "qwen/qwen3.6-plus:free"
}
```

### `POST /api/extract-location`

```json
{
  "text": "В Аксайском районе на ул. Большая Садовая переполнены контейнеры",
  "channel_name": "Ростов новости",
  "channel_description": "Новости района"
}
```

Пример ответа:

```json
{
  "region": "Ростовская область",
  "city": null,
  "district": "Аксайский район",
  "address": "ул. Большая Садовая",
  "provider": "openrouter",
  "model": "qwen/qwen3.6-plus:free"
}
```

### `POST /api/extract-key-words`

```json
{
  "text": "В Аксайском районе пятый день не вывозят мусор, контейнеры переполнены"
}
```

Пример ответа:

```json
{
  "key_words": ["мусор", "переполнены", "контейнеры"],
  "provider": "openrouter",
  "model": "qwen/qwen3.6-plus:free"
}
```

### `POST /api/classify-category/batch`

```json
{
  "items": [
    {
      "text": "Мусор не вывозят уже неделю",
      "channel_name": "Новости",
      "channel_description": ""
    },
    {
      "text": "Нет записи к врачу в поликлинике",
      "channel_name": "Город",
      "channel_description": ""
    }
  ]
}
```

## Быстрая Проверка Через `curl`

Классификация:

```bash
curl -X POST http://127.0.0.1:8000/api/classify-category \
  -H "Content-Type: application/json" \
  -d '{
    "text": "В Аксайском районе пятый день не вывозят мусор, контейнеры переполнены",
    "channel_name": "Ростов новости",
    "channel_description": "Новости района"
  }'
```

Локация:

```bash
curl -X POST http://127.0.0.1:8000/api/extract-location \
  -H "Content-Type: application/json" \
  -d '{
    "text": "В Аксайском районе на ул. Большая Садовая переполнены контейнеры",
    "channel_name": "Ростов новости",
    "channel_description": "Новости района"
  }'
```

Ключевые слова:

```bash
curl -X POST http://127.0.0.1:8000/api/extract-key-words \
  -H "Content-Type: application/json" \
  -d '{
    "text": "В Аксайском районе пятый день не вывозят мусор, контейнеры переполнены"
  }'
```

Проверка health:

```bash
curl http://127.0.0.1:8000/api/health
```

## Тесты

Запуск:

```bash
.venv/bin/python -m pytest -q
```

Что покрывают тесты:

- API endpoints;
- обработку batch-запросов;
- парсинг JSON-ответа модели;
- нормализацию и валидацию ответа LLM;
- базовую устойчивость после рефакторинга.

## Примечания

- `scores` — это не строгая вероятность, а оценка уверенности, которую возвращает модель;
- если OpenRouter вернёт ошибку, API ответит `502`;
- если не задан `OPENROUTER_API_KEY`, API ответит `503`.
