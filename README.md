# Discord Farm Bot

## Локальный запуск
```bash
cp .env.example .env      # вписать токен
docker compose up -d --build
docker compose logs -f
```

## Данные
Хранятся в volume `farm-data` (`/app/data`): `clicks.json`, `state.json`, `Logs.xlsx`.

## Переменные окружения
| Переменная | Обязательна | По умолчанию | Описание |
|---|---|---|---|
| `DISCORD_TOKEN` | ✅ | — | Токен бота |
| `CHANNEL_ID` | ❌ | `1197494268353314882` | ID канала с кнопками |
| `REMINDER_HOURS` | ❌ | `3` | Интервал напоминаний |
| `DATA_DIR` | ❌ | `/app/data` | Папка данных внутри контейнера |