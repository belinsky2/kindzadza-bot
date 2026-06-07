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


def _row_from_reg(reg: dict) -> list:
    nums = reg.get("raffle_numbers") or ""
    method = reg.get("payment_method") or ""
    method_label = config.PAYMENT_METHODS.get(method, {}).get("label", method)
    now = datetime.now(config.TZ).strftime("%Y-%m-%d %H:%M")
    return [
        str(reg["user_id"]),
        reg.get("name") or "",
        f"@{reg['username']}" if reg.get("username") else "",
        reg.get("qty") or "",
        method_label,
        reg.get("amount") or "",
        STATUS_LABELS.get(reg.get("status"), reg.get("status") or ""),
        nums,
        now if reg.get("status") in (None, "new") else "",
        now,
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
            # сохраняем «Создано», если уже было
            created = ws.cell(idx, 9).value
            if created:
                row[8] = created
            ws.update(f"A{idx}", [row])
        else:
            ws.append_row(row, value_input_option="USER_ENTERED")
    except Exception:
        log.exception("Ошибка записи в Google Таблицу для user_id=%s", uid)


async def sync_registration(reg: dict) -> None:
    """Upsert строки регистрации по user_id. Безопасно вызывать всегда."""
    await asyncio.to_thread(_upsert_sync, reg)
