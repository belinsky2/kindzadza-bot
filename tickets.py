"""Генерация QR-билетов и deep-link для сканирования."""
from __future__ import annotations

import io
import secrets

import qrcode
from aiogram.types import BufferedInputFile

import config


def new_code() -> str:
    """Короткий неугадываемый код билета (url-safe, влезает в deep-link start)."""
    return secrets.token_urlsafe(8)


def ticket_link(code: str) -> str:
    """Deep-link: при сканировании открывает бота с параметром check-in."""
    return f"https://t.me/{config.BOT_USERNAME}?start=t_{code}"


def make_qr_png(data: str) -> BufferedInputFile:
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return BufferedInputFile(buf.read(), filename="ticket.png")
