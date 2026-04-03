# Region Pulse

Минимальный backend для кейса по анализу региональных новостей и сообщений граждан.

Сервис реализует:

- функцию `classify_category(text, channel_name, channel_description)`;
- HTTP API для ручной проверки классификации;
- пакетную проверку нескольких сообщений за один запрос.

## Категории

- ЖКХ
- Дороги и транспорт
- Здравоохранение
- Образование
- Экология и ЧС
- Экономика и промышленность

## Запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn functions.test:app --reload
```

## API

После запуска документация будет доступна по адресу:

```text
http://127.0.0.1:8000/docs
```

Основные эндпоинты:

- `GET /api/health`
- `GET /api/categories`
- `POST /api/classify-category`
- `POST /api/classify-category/batch`

## Пример запроса

```bash
curl -X POST http://127.0.0.1:8000/api/classify-category \
  -H "Content-Type: application/json" \
  -d '{
    "text": "В Аксайском районе пятый день не вывозят мусор, контейнеры переполнены",
    "channel_name": "Ростов новости",
    "channel_description": "Новости аксайского района и суворовского ТСЖ"
  }'
```

Пример ответа:

```json
{
  "category": "ЖКХ",
  "scores": {
    "ЖКХ": 4,
    "Дороги и транспорт": 0,
    "Здравоохранение": 0,
    "Образование": 0,
    "Экология и ЧС": 0,
    "Экономика и промышленность": 0
  },
  "matched_keywords": {
    "ЖКХ": ["мусор", "контейнер", "контейнеры", "тсж"],
    "Дороги и транспорт": [],
    "Здравоохранение": [],
    "Образование": [],
    "Экология и ЧС": [],
    "Экономика и промышленность": []
  }
}
```
