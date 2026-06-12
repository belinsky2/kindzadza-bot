"""Конфигурация бота: читается из .env. Все значения — в одном месте."""
from __future__ import annotations

import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return default


# --- Telegram ---
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
ADMIN_GROUP_ID: int = _int("ADMIN_GROUP_ID", 0)
BOT_USERNAME: str = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
ORGANIZER_USERNAME: str = os.getenv("ORGANIZER_USERNAME", "").strip().lstrip("@")
# Ник того, кому билетер пересылает заказ еды на кухню (без @).
KITCHEN_USERNAME: str = os.getenv("KITCHEN_USERNAME", "reap_of_dea").strip().lstrip("@")
# Чат/пользователь, куда уходит заказ по кнопке «Отправить на кухню».
# 0 → бот найдёт chat_id по KITCHEN_USERNAME (Артур должен был запустить бота).
KITCHEN_CHAT_ID: int = _int("KITCHEN_CHAT_ID", 0)
# Доп. список user_id оргов для check-in (через запятую). Необязательно —
# по умолчанию права определяются членством в ADMIN_GROUP_ID.
ADMIN_IDS: set[int] = {
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.lstrip("-").isdigit()
}

# --- Google Sheets (опционально; без креды — no-op) ---
GOOGLE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json").strip()
SPREADSHEET_ID: str = os.getenv("SPREADSHEET_ID", "").strip()

# --- Время / таймзона ---
TZ_NAME: str = os.getenv("TIMEZONE", "Asia/Ho_Chi_Minh").strip()
TZ = ZoneInfo(TZ_NAME)

# --- Мероприятие ---
EVENT_DATE: str = os.getenv("EVENT_DATE", "13 июня").strip()
EVENT_TIME: str = os.getenv("EVENT_TIME", "20:00").strip()
DOORS_TIME: str = os.getenv("DOORS_TIME", "19:30").strip()
EVENT_LOCATION: str = os.getenv("EVENT_LOCATION", "(локация уточняется)").strip()
EVENT_MAP_URL: str = os.getenv("EVENT_MAP_URL", "").strip()

# --- Лимит мест и дефицит ---
EVENT_CAPACITY: int = _int("EVENT_CAPACITY", 60)
SEATS_REVEAL_THRESHOLD: int = _int("SEATS_REVEAL_THRESHOLD", 15)
MAX_TICKETS_PER_ORDER: int = _int("MAX_TICKETS_PER_ORDER", 10)

# --- Рассылка / посты ---
DAILY_POST_TIME: str = os.getenv("DAILY_POST_TIME", "10:00").strip()  # HH:MM по TZ
CONFIRM_SLA: str = os.getenv("CONFIRM_SLA", "пары часов").strip()
BROADCAST_RATE: int = _int("BROADCAST_RATE", 25)  # сообщений в секунду (лимит Telegram ~30)

# --- Напоминания (cron: дата+время по TZ) ---
REMINDER_EVE: str = os.getenv("REMINDER_EVE", "2026-06-12 20:00").strip()
REMINDER_DAY: str = os.getenv("REMINDER_DAY", "2026-06-13 12:00").strip()

# --- Ссылки ---
TG_LINK: str = os.getenv("TG_LINK", "").strip()
INSTA_LINK: str = os.getenv("INSTA_LINK", "").strip()
BOT_LINK: str = os.getenv("BOT_LINK", "").strip()  # для CTA в постах

# --- Реквизиты оплаты (текст показывается пользователю) ---
REQUISITES = {
    "vnd": os.getenv("REQUISITES_VND", "(реквизиты для донгов уточняются)").strip(),
    "rub": os.getenv("REQUISITES_RUB", "(реквизиты для рублей уточняются)").strip(),
    "usdt": os.getenv("REQUISITES_USDT", "(кошелёк USDT уточняется)").strip(),
}
USDT_NETWORK: str = os.getenv("USDT_NETWORK", "TRC20").strip()

# --- Способы оплаты: цена за один билет ---
PAYMENT_METHODS = {
    "vnd": {"label": "🇻🇳 Донги", "unit": 200_000, "cur": "₫", "online": True},
    "rub": {"label": "🇷🇺 Рубли", "unit": 650, "cur": "₽", "online": True},
    "usdt": {"label": "🪙 Крипта (USDT)", "unit": 8, "cur": "USDT", "online": True},
    "door": {"label": "📍 Оплата на месте", "unit": 300_000, "cur": "₫", "online": False},
}

ONLINE_METHODS = [k for k, v in PAYMENT_METHODS.items() if v["online"]]

# --- Пути ---
DB_PATH: str = os.getenv("DB_PATH", "bot.db").strip()
CONTENT_DIR: str = os.getenv("CONTENT_DIR", "content").strip()
ANNOUNCE_IMAGE: str = os.path.join(CONTENT_DIR, "announce.jpg")
MENU_IMAGE: str = os.path.join(CONTENT_DIR, "menu.jpg")
PAYMENT_QR_VND: str = os.path.join(CONTENT_DIR, "payment_qr_vnd.jpg")
PAYMENT_QR_USDT: str = os.path.join(CONTENT_DIR, "payment_qr_usdt.jpg")
POSTS_DIR: str = os.path.join(CONTENT_DIR, "posts")

# Картинка-QR для способа оплаты (отправляется после реквизитов, если файл есть)
PAYMENT_QR_IMAGE = {
    "vnd": PAYMENT_QR_VND,
    "usdt": PAYMENT_QR_USDT,
}


def format_amount(method: str, qty: int = 1) -> str:
    """Сумма прописью с валютой: '600 000 ₫' или '8 USDT'."""
    m = PAYMENT_METHODS[method]
    total = m["unit"] * qty
    if m["cur"] == "USDT":
        num = f"{total:g}"
    else:
        num = f"{total:,}".replace(",", " ")
    return f"{num} {m['cur']}"


def validate() -> list[str]:
    """Возвращает список проблем конфигурации (для предупреждений при старте)."""
    issues = []
    if not BOT_TOKEN:
        issues.append("BOT_TOKEN не задан")
    if not ADMIN_GROUP_ID:
        issues.append("ADMIN_GROUP_ID не задан (подтверждения оплат не будут работать)")
    if not SPREADSHEET_ID:
        issues.append("SPREADSHEET_ID не задан — запись в Google Таблицу отключена")
    if not ORGANIZER_USERNAME:
        issues.append("ORGANIZER_USERNAME не задан — кнопка 'Связаться с организатором' скрыта")
    if not BOT_USERNAME:
        issues.append("BOT_USERNAME не задан — QR-билеты со сканированием работать не будут")
    return issues
