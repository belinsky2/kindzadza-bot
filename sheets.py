"""Зеркало регистраций в Google Таблице. Graceful no-op без креды.

Два листа в одной таблице. Набор колонок зависит от типа события:

Платное событие (FREE_EVENT=false):
  «Все гости»    — все записи включая просто зашедших (со способом и суммой)
  «Оплатившие»   — только confirmed_online, с колонкой «Заказ еды»

Бесплатное событие (FREE_EVENT=true):
  «Все гости»          — все записи без колонок оплаты
  «Зарегистрированные» — только зарегистрировавшиеся (confirmed_online)

gspread синхронный — блокирующие вызовы уносим в поток через asyncio.to_thread,
чтобы не вешать event loop бота.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

import config

log = logging.getLogger(__name__)

_sh = None          # gspread Spreadsheet
_ws_all = None      # лист «Все гости»
_ws_paid = None     # лист «Оплатившие» / «Зарегистрированные»

# --- Платное событие ---
HEADER_ALL_PAID = [
    "user_id", "Имя", "Ник", "Кол-во", "Способ",
    "Сумма", "Статус", "Источник", "Номера розыгрыша", "Пришло", "Создано", "Обновлено",
]

HEADER_PAID = [
    "user_id", "Имя", "Ник", "Кол-во билетов", "Способ",
    "Сумма", "Номера розыгрыша", "Заказ еды", "Пришло", "Создано",
]

# --- Бесплатное событие (без колонок оплаты) ---
HEADER_ALL_FREE = [
    "user_id", "Имя", "Ник", "Кол-во мест",
    "Статус", "Источник", "Номера розыгрыша", "Пришло", "Создано", "Обновлено",
]

HEADER_REG_FREE = [
    "user_id", "Имя", "Ник", "Кол-во мест",
    "Номера розыгрыша", "Пришло", "Создано",
]

STATUS_LABELS = {
    "new": "зашёл",
    "awaiting_payment": "не оплатил",
    "awaiting_confirmation": "ждёт подтверждения",
    "confirmed_online": "оплатил онлайн",
    "door": "оплата на месте",
    "rejected": "отклонён",
    "refunded": "возврат",
}

# При бесплатном входе статус confirmed_online означает «зарегистрирован»
STATUS_LABELS_FREE = {**STATUS_LABELS, "confirmed_online": "зарегистрирован"}


def _status_label(status: str | None) -> str:
    labels = STATUS_LABELS_FREE if config.FREE_EVENT else STATUS_LABELS
    return labels.get(status, status or "")


def _header_all() -> list:
    return HEADER_ALL_FREE if config.FREE_EVENT else HEADER_ALL_PAID


def _header_second() -> list:
    return HEADER_REG_FREE if config.FREE_EVENT else HEADER_PAID


def _sheet_name(base: str) -> str:
    """Добавляет SHEET_TAG к имени листа: «27.06 Все гости»."""
    tag = config.SHEET_TAG
    return f"{tag} {base}" if tag else base


def _second_title() -> str:
    base = "Зарегистрированные" if config.FREE_EVENT else "Оплатившие"
    return _sheet_name(base)


def _get_or_create_ws(sh, title: str, header: list):
    """Возвращает лист по имени, создаёт если нет, гарантирует заголовок."""
    try:
        ws = sh.worksheet(title)
    except Exception:
        ws = sh.add_worksheet(title=title, rows=1000, cols=len(header))
    if ws.row_values(1) != header:
        ws.update("A1", [header])
    return ws


def _init_sync() -> bool:
    global _sh, _ws_all, _ws_paid
    if _ws_all is not None:
        return True
    if not config.SPREADSHEET_ID or not os.path.exists(config.GOOGLE_CREDENTIALS_FILE):
        log.warning("Google Sheets отключены (нет SPREADSHEET_ID или файла креды).")
        return False
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_FILE, scopes=scopes
        )
        client = gspread.authorize(creds)
        _sh = client.open_by_key(config.SPREADSHEET_ID)
        _ws_all = _get_or_create_ws(_sh, _sheet_name("Все гости"), _header_all())
        _ws_paid = _get_or_create_ws(_sh, _second_title(), _header_second())
        log.info("Google Sheets подключены (2 листа).")
        return True
    except Exception:
        log.exception("Не удалось подключить Google Sheets — продолжаю без них.")
        return False


def _fmt_ts(ts) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts), config.TZ).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError, TypeError):
        return ""


def _arrived_str(reg: dict) -> str:
    """'2/3' если были отметки, иначе ''."""
    arrived = reg.get("arrived_count")
    if arrived is None:
        return ""
    qty = reg.get("qty") or 0
    return f"{int(arrived)}/{int(qty)}"


def _row_all(reg: dict) -> list:
    uid = str(reg["user_id"])
    name = reg.get("name") or ""
    nick = f"@{reg['username']}" if reg.get("username") else ""
    source = reg.get("source") or ""
    if config.FREE_EVENT:
        return [
            uid, name, nick,
            reg.get("qty") or "",
            _status_label(reg.get("status")),
            source,
            reg.get("raffle_numbers") or "",
            _arrived_str(reg),
            _fmt_ts(reg.get("created_at")),
            _fmt_ts(reg.get("updated_at")),
        ]
    method = config.PAYMENT_METHODS.get(reg.get("payment_method") or "", {}).get("label", "")
    return [
        uid, name, nick,
        reg.get("qty") or "",
        method,
        reg.get("amount") or "",
        _status_label(reg.get("status")),
        source,
        reg.get("raffle_numbers") or "",
        _arrived_str(reg),
        _fmt_ts(reg.get("created_at")),
        _fmt_ts(reg.get("updated_at")),
    ]


def _row_paid(reg: dict) -> list:
    uid = str(reg["user_id"])
    name = reg.get("name") or ""
    nick = f"@{reg['username']}" if reg.get("username") else ""
    if config.FREE_EVENT:
        return [
            uid, name, nick,
            reg.get("qty") or "",
            reg.get("raffle_numbers") or "",
            _arrived_str(reg),
            _fmt_ts(reg.get("created_at")),
        ]
    method = config.PAYMENT_METHODS.get(reg.get("payment_method") or "", {}).get("label", "")
    return [
        uid, name, nick,
        reg.get("qty") or "",
        method,
        reg.get("amount") or "",
        reg.get("raffle_numbers") or "",
        reg.get("food_order") or "",
        _arrived_str(reg),
        _fmt_ts(reg.get("created_at")),
    ]


def _upsert_in_ws(ws, uid: str, row: list) -> None:
    col = ws.col_values(1)
    if uid in col:
        idx = col.index(uid) + 1
        ws.update(f"A{idx}", [row])
    else:
        ws.append_row(row, value_input_option="USER_ENTERED")


def _upsert_sync(reg: dict) -> None:
    if not _init_sync():
        return
    uid = str(reg["user_id"])
    try:
        _upsert_in_ws(_ws_all, uid, _row_all(reg))
    except Exception:
        log.exception("Ошибка записи в лист «Все гости» для user_id=%s", uid)
    if reg.get("status") == "confirmed_online":
        try:
            _upsert_in_ws(_ws_paid, uid, _row_paid(reg))
        except Exception:
            log.exception("Ошибка записи в лист «Оплатившие» для user_id=%s", uid)


def _rewrite_all_sync(regs: list[dict]) -> int:
    if not _init_sync():
        return -1
    paid = [r for r in regs if r.get("status") == "confirmed_online"]
    try:
        _ws_all.clear()
        _ws_all.update("A1", [_header_all()] + [_row_all(r) for r in regs],
                       value_input_option="USER_ENTERED")
        _ws_paid.clear()
        _ws_paid.update("A1", [_header_second()] + [_row_paid(r) for r in paid],
                        value_input_option="USER_ENTERED")
        return len(regs)
    except Exception:
        log.exception("Ошибка массовой записи в Google Таблицу")
        return -1


async def sync_registration(reg: dict) -> None:
    """Upsert в оба листа. Безопасно вызывать всегда."""
    await asyncio.to_thread(_upsert_sync, reg)


async def sync_all(regs: list[dict]) -> int:
    """Полная перезаливка обоих листов. -1 если Sheets отключены/ошибка."""
    return await asyncio.to_thread(_rewrite_all_sync, regs)
