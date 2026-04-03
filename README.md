# Region Pulse

Backend-прототип для кейса по анализу региональных новостей, обращений и сообщений граждан.

Сервис умеет:

- классифицировать сообщение по отрасли через `classify_category(text, channel_name, channel_description)`;
- извлекать географию через `extract_location(text, channel_name, channel_description)`;
- работать в двух режимах: `rules` и `llm`;
- давать HTTP API для ручной проверки через Swagger;
- обрабатывать как одиночные, так и batch-запросы;
- запускать тесты через `pytest`.

## Функции

### `classify_category`

Определяет категорию сообщения по тексту, названию канала и описанию канала.

Поддерживаемые категории:

- `ЖКХ`
- `Дороги и транспорт`
- `Здравоохранение`
- `Образование`
- `Экология и ЧС`
- `Экономика и промышленность`

Ответ содержит:

- `category` — итоговая категория
- `scores` — количество совпадений по категориям
- `matched_keywords` — найденные ключевые слова
- `provider` — источник ответа: `rules` или `llm`
- `model` — название модели, если использовался LLM-режим

### `extract_location`

Извлекает географию из сообщения.

Ответ содержит:

- `region`
- `city`
- `district`
- `address`
- `provider`
- `model`

Сейчас используется локальный справочник по Ростовской области и простая нормализация, например:

- `Ростов` -> `Ростов-на-Дону`
- `Аксай` -> `Аксайский район`

Если география не найдена, поля возвращаются как `null`.

## Структура Проекта

```text
region-pulse/
├── functions/
│   └── main.py
├── tests/
│   ├── test_api.py
│   └── test_logic.py
├── .gitignore
├── pytest.ini
├── README.md
└── requirements.txt
```

## Установка И Запуск

```bash
cd /Users/matvey/Desktop/region-pulse
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Настройка `.env`

Создайте файл `.env` в корне проекта и укажите необходимые переменные окружения для вашего LLM-провайдера или локальной модели.

Пример:

```env
REGION_PULSE_PROVIDER=llm
LLM_MODEL=your_model_name
```

Важно:

- приложение читает именно `.env`
- `.env` добавлен в `.gitignore`

Если вы хотите использовать только локальные правила, можно оставить:

```env
REGION_PULSE_PROVIDER=rules
```

### Запуск API

```bash
uvicorn functions.main:app --reload
```

После запуска:

- root: `http://127.0.0.1:8000/`
- docs: `http://127.0.0.1:8000/docs`

## Режимы Работы

### `rules`

Локальный режим без вызова модели.

Используется:

- ключевые слова для категоризации
- справочник локаций для геопривязки
- regex для извлечения адресов

### `llm`

Режим, в котором ответы формируются через языковую модель.

Активный режим можно проверить через:

```text
GET /api/provider
```

Можно переключать режим:

- глобально через `.env`
- точечно через query-параметр `provider`

Примеры:

```text
POST /api/classify-category?provider=llm
POST /api/extract-location?provider=llm
POST /api/classify-category?provider=rules
POST /api/extract-location?provider=rules
```

## API

Основные эндпоинты:

- `GET /`
- `GET /api/health`
- `GET /api/provider`
- `GET /api/categories`
- `GET /api/location-directory`
- `POST /api/classify-category`
- `POST /api/classify-category/batch`
- `POST /api/extract-location`
- `POST /api/extract-location/batch`

## Примеры Проверки API

### Категоризация

`POST /api/classify-category`

```json
{
  "text": "В Аксайском районе пятый день не вывозят мусор, контейнеры переполнены",
  "channel_name": "Ростов новости",
  "channel_description": "Новости аксайского района и суворовского ТСЖ"
}
```

Ожидаемый результат:

- `category`: `ЖКХ`

Еще пример:

```json
{
  "text": "На центральной улице огромные ямы, пробки, автобусы идут с большим опозданием",
  "channel_name": "Транспорт Ростова",
  "channel_description": "Новости дорог и общественного транспорта"
}
```

Ожидаемый результат:

- `category`: `Дороги и транспорт`

### Извлечение Локации

`POST /api/extract-location`

```json
{
  "text": "В Аксайском районе на ул. Большая Садовая переполнены контейнеры",
  "channel_name": "Ростов новости",
  "channel_description": "Новости аксайского района"
}
```

Ожидаемый результат примерно такой:

```json
{
  "region": "Ростовская область",
  "city": "Ростов-на-Дону",
  "district": "Аксайский район",
  "address": "ул. Большая Садовая",
  "provider": "rules",
  "model": null
}
```

Пример без локации:

```json
{
  "text": "Жители обсуждают качество обслуживания и жалуются на ситуацию",
  "channel_name": "Городские новости",
  "channel_description": "Локальные события"
}
```

Ожидаемый результат:

```json
{
  "region": null,
  "city": null,
  "district": null,
  "address": null,
  "provider": "rules",
  "model": null
}
```

### Batch Примеры

`POST /api/classify-category/batch`

```json
{
  "items": [
    {
      "text": "В поликлинике снова огромная очередь к врачу",
      "channel_name": "Медицина региона",
      "channel_description": ""
    },
    {
      "text": "На заводе сообщили о сокращении сотрудников",
      "channel_name": "Промышленный вестник",
      "channel_description": ""
    }
  ]
}
```

`POST /api/extract-location/batch`

```json
{
  "items": [
    {
      "text": "В Ростове на проспект Буденновский образовалась пробка",
      "channel_name": "Транспорт города",
      "channel_description": ""
    },
    {
      "text": "Жители обсуждают фестиваль еды",
      "channel_name": "Афиша",
      "channel_description": ""
    }
  ]
}
```

## Запуск Тестов

```bash
pytest
```

Покрытие сейчас включает:

- тесты логики категоризации
- тесты извлечения локации
- тесты HTTP API
- тесты переключения `rules/llm`
