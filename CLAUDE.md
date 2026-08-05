# CLAUDE.md — правила для ИИ-ассистента

## Файлы проекта: всегда указывай полный путь

Когда ссылаешься на любой файл проекта — всегда пиши полный путь от корня репозитория.

Примеры:
- НЕ: "смотри в check_config.py" → ДА: "`/home/user/kindzadza-bot/check_config.py`"
- НЕ: "в папке content/" → ДА: "`/home/user/kindzadza-bot/content/`"
- НЕ: "в handlers/admin.py" → ДА: "`/home/user/kindzadza-bot/handlers/admin.py`"

## Структура проекта

```
/home/user/kindzadza-bot/
├── main.py                      # точка входа, запуск бота
├── config.py                    # все настройки из .env
├── db.py                        # база данных SQLite
├── texts.py                     # все тексты сообщений
├── keyboards.py                 # кнопки
├── scheduler.py                 # ежедневные посты и напоминания
├── broadcast.py                 # рассылка по пользователям
├── segments.py                  # сегментация A/B/C
├── sheets.py                    # Google Sheets (опционально)
├── tickets.py                   # QR-билеты
├── check_config.py              # проверка .env перед запуском
├── deploy.sh                    # скрипт установки на сервер
├── kindzadza-bot.service        # systemd unit для автозапуска
├── requirements.txt             # зависимости Python
├── .env.example                 # шаблон конфига (заполнить → .env)
├── DEPLOY.md                    # инструкция по деплою на сервер
├── handlers/
│   ├── admin.py                 # подтверждение оплат, /stats, посты, рассылки
│   ├── checkin.py               # QR-сканирование на входе
│   └── registration.py          # FSM-воронка /start
├── content/
│   ├── announce.jpg             # фото анонса (показывается на /start)
│   ├── menu.jpg                 # фото меню (отправляется после QR-билета)
│   ├── payment_qr_vnd.jpg       # QR для оплаты в донгах
│   └── posts/                   # медиафайлы для постов рассылки
└── tests/
    ├── conftest.py              # фикстуры pytest
    ├── test_db.py
    ├── test_handlers_admin.py
    ├── test_handlers_checkin.py
    ├── test_handlers_registration.py
    └── test_tickets.py
```

## Технологический стек

- **aiogram 3.x** — async Telegram bot framework
- **aiosqlite** — async SQLite (файл `bot.db` на сервере)
- **APScheduler** — ежедневные посты и напоминания
- **pytest-asyncio** — тесты (asyncio_mode = auto)
- Python 3.11+, виртуальное окружение `.venv/`

## Важные правила кода

- Все тексты сообщений — только в `/home/user/kindzadza-bot/texts.py`
- Все настройки — только в `/home/user/kindzadza-bot/config.py` (читаются из `.env`)
- Тире в текстах — только en dash `–`, не em dash `—`
- После каждого изменения запускай тесты: `python -m pytest tests/ -q`
- Коммить на ветку `claude/bot-testing-validation-CZT2j`

## Деплой

Подробно: `/home/user/kindzadza-bot/DEPLOY.md`
Проверка конфига: `python /home/user/kindzadza-bot/check_config.py`
Установка на сервер: `bash /home/user/kindzadza-bot/deploy.sh`
