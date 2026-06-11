"""Зеркало регистраций в Google Таблице. Graceful no-op без креды.

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

_worksheet = None
_enabled = False

HEADER = [
    "user_id", "Имя", "Ник", "Кол-во", "Способ",
    "Сумма", "Статус", "Номера розыгрыша", "Создано", "Обновлено",
]

STATUS_LABELS = {
    "new": "зашёл",
    "awaiting_payment": "не оплатил",
    "awaiting_confirmation": "ждёт подтверждения",
    "confirmed_online": "оплатил онлайн",
    "door": "оплата на месте",
    "rejected": "отклонён",
}


def _init_sync() -> bool:
    """Ленивая инициализация worksheet. Возвращает True, если включено."""
    global _worksheet, _enabled
    if _worksheet is not None:
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
        sh = client.open_by_key(config.SPREADSHEET_ID)
        ws = sh.sheet1
        # гарантируем заголовок
        existing = ws.row_values(1)
        if existing != HEADER:
            ws.update("A1", [HEADER])
        _worksheet = ws
        _enabled = True
        log.info("Google Sheets подключены.")
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


def _row_from_reg(reg: dict) -> list:
    nums = reg.get("raffle_numbers") or ""
    method = reg.get("payment_method") or ""
    method_label = config.PAYMENT_METHODS.get(method, {}).get("label", method)
    return [
        str(reg["user_id"]),
        reg.get("name") or "",
        f"@{reg['username']}" if reg.get("username") else "",
        reg.get("qty") or "",
        method_label,
        reg.get("amount") or "",
        STATUS_LABELS.get(reg.get("status"), reg.get("status") or ""),
        nums,
        _fmt_ts(reg.get("created_at")),
        _fmt_ts(reg.get("updated_at")),
    ]


def _upsert_sync(reg: dict) -> None:
    if not _init_sync():
        return
    ws = _worksheet
    uid = str(reg["user_id"])
    row = _row_from_reg(reg)
    try:
        col = ws.col_values(1)  # колонка user_id
        if uid in col:
            idx = col.index(uid) + 1  # 1-based
            ws.update(f"A{idx}", [row])
        else:
            ws.append_row(row, value_input_option="USER_ENTERED")
    except Exception:
        log.exception("Ошибка записи в Google Таблицу для user_id=%s", uid)


def _rewrite_all_sync(regs: list[dict]) -> int:
    """Полностью перезаписывает лист: заголовок + все строки. Возвращает кол-во строк."""
    if not _init_sync():
        return -1
    ws = _worksheet
    rows = [HEADER] + [_row_from_reg(r) for r in regs]
    try:
        ws.clear()
        ws.update("A1", rows, value_input_option="USER_ENTERED")
        return len(regs)
    except Exception:
        log.exception("Ошибка массовой записи в Google Таблицу")
        return -1


async def sync_registration(reg: dict) -> None:
    """Upsert строки регистрации по user_id. Безопасно вызывать всегда."""
    await asyncio.to_thread(_upsert_sync, reg)


async def sync_all(regs: list[dict]) -> int:
    """Полная перезалив­ка всех регистраций. -1 если Sheets отключены/ошибка."""
    return await asyncio.to_thread(_rewrite_all_sync, regs)
