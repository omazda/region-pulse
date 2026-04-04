# Region Pulse

Асинхронный LLM-only backend для анализа региональных сообщений, новостей и обращений граждан.

Сервис использует модель через GigaChat и умеет:

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
- `matched_keywords` — ключевые слова, связанные с категориями;
- `provider` — источник ответа, сейчас `gigachat`;
- `model` — имя модели.

Поддерживаемые категории:

- `ЖКХ`
- `Дороги и транспорт`
- `Здравоохранение`
- `Образование`
- `Экология и ЧС`
- `Экономика и промышленность`
- `Социальная защита и выплаты`
- `Благоустройство и городская среда`
- `Безопасность и правопорядок`
- `Госуслуги и обращения граждан`
- `Жилье и строительство`

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
REGION_PULSE_PROVIDER=llm
GIGACHAT_MODEL=GigaChat-2
GIGACHAT_TIMEOUT=60
GIGACHAT_VERIFY_SSL_CERTS=false
GIGACHAT_BASE_URL=https://gigachat.devices.sberbank.ru/api/v1
GIGACHAT_AUTH_URL=https://ngw.devices.sberbank.ru:9443/api/v2/oauth
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_CLIENT_ID=your_client_id
GIGACHAT_CLIENT_SECRET=your_client_secret
```

Переменные:

- `REGION_PULSE_PROVIDER` — текущий режим, сейчас должен быть `llm`;
- `GIGACHAT_MODEL` — модель для вызова;
- `GIGACHAT_TIMEOUT` — таймаут запроса в секундах;
- `GIGACHAT_VERIFY_SSL_CERTS` — проверять ли SSL-сертификаты (`true` или `false`).
- `GIGACHAT_BASE_URL` — base URL REST API GigaChat;
- `GIGACHAT_AUTH_URL` — OAuth endpoint для получения токена;
- `GIGACHAT_SCOPE` — scope для OAuth;
- `GIGACHAT_CLIENT_ID` и `GIGACHAT_CLIENT_SECRET` — данные для автоматического обновления токена.

Важно:

- проект сейчас работает только через LLM;
- локального `rules`-режима больше нет;
- токен GigaChat обновляется автоматически через `client_id/client_secret`;
- можно использовать `GIGACHAT_ACCESS_TOKEN` как ручной fallback, но это не основной режим;
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
  "matched_keywords": {
    "ЖКХ": ["мусор", "контейнеры"],
    "Дороги и транспорт": [],
    "Здравоохранение": [],
    "Образование": [],
    "Экология и ЧС": [],
    "Экономика и промышленность": [],
    "Социальная защита и выплаты": [],
    "Благоустройство и городская среда": [],
    "Безопасность и правопорядок": [],
    "Госуслуги и обращения граждан": [],
    "Жилье и строительство": []
  },
  "provider": "gigachat",
  "model": "GigaChat-2"
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
  "provider": "gigachat",
  "model": "GigaChat-2"
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
  "provider": "gigachat",
  "model": "GigaChat-2"
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

### Проверка Категорий

`ЖКХ`

```bash
curl -X POST http://127.0.0.1:8000/api/classify-category \
  -H "Content-Type: application/json" \
  -d '{
    "text":"Во дворе уже неделю не вывозят мусор, контейнеры переполнены",
    "channel_name":"Новости района",
    "channel_description":"Проблемы города"
  }'
```

`Социальная защита и выплаты`

```bash
curl -X POST http://127.0.0.1:8000/api/classify-category \
  -H "Content-Type: application/json" \
  -d '{
    "text":"Семья не может получить положенное пособие на ребенка уже третий месяц",
    "channel_name":"Соцподдержка",
    "channel_description":"Выплаты и льготы"
  }'
```

`Благоустройство и городская среда`

```bash
curl -X POST http://127.0.0.1:8000/api/classify-category \
  -H "Content-Type: application/json" \
  -d '{
    "text":"Во дворе разбитая детская площадка и не работает уличное освещение",
    "channel_name":"Комфортная среда",
    "channel_description":"Благоустройство города"
  }'
```

`Безопасность и правопорядок`

```bash
curl -X POST http://127.0.0.1:8000/api/classify-category \
  -H "Content-Type: application/json" \
  -d '{
    "text":"Жители просят усилить патрулирование района из-за серии ночных краж",
    "channel_name":"Безопасный город",
    "channel_description":"Проблемы правопорядка"
  }'
```

`Госуслуги и обращения граждан`

```bash
curl -X POST http://127.0.0.1:8000/api/classify-category \
  -H "Content-Type: application/json" \
  -d '{
    "text":"Через портал не получается подать обращение, заявление зависает на последнем шаге",
    "channel_name":"Госуслуги онлайн",
    "channel_description":"Проблемы с сервисами"
  }'
```

`Жилье и строительство`

```bash
curl -X POST http://127.0.0.1:8000/api/classify-category \
  -H "Content-Type: application/json" \
  -d '{
    "text":"Дольщики жалуются на срыв сроков сдачи дома и отсутствие информации от застройщика",
    "channel_name":"Жилье и стройка",
    "channel_description":"Проблемы строительства"
  }'
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
- валидацию ответа LLM;
- асинхронный слой вызова LLM;
- базовую устойчивость после рефакторинга.

## Примечания

- если GigaChat вернёт ошибку, API ответит `502`;
- если не заданы данные доступа к GigaChat, API ответит `503`.
- сервис использует прямой REST API GigaChat через `httpx.AsyncClient`, без SDK.
