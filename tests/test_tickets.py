"""Тесты генерации QR-билетов (tickets.py)."""
from __future__ import annotations

import re
import pytest
from unittest.mock import patch
from aiogram.types import BufferedInputFile

import config
import tickets


def test_new_code_returns_string():
    code = tickets.new_code()
    assert isinstance(code, str)


def test_new_code_non_empty():
    code = tickets.new_code()
    assert len(code) > 0


def test_new_code_url_safe():
    """Код должен быть URL-safe: только буквы, цифры, - и _."""
    code = tickets.new_code()
    assert re.fullmatch(r"[A-Za-z0-9_\-]+", code), f"Код содержит недопустимые символы: {code!r}"


def test_new_code_generates_unique_values():
    codes = {tickets.new_code() for _ in range(100)}
    # Вероятность коллизии при 11-байтовом коде практически нулевая
    assert len(codes) == 100


def test_new_code_length():
    """token_urlsafe(8) даёт ~11 символов в base64url-кодировке."""
    code = tickets.new_code()
    assert len(code) >= 10


def test_ticket_link_format():
    with patch.object(config, "BOT_USERNAME", "test_bot"):
        link = tickets.ticket_link("MYCODE")
    assert link == "https://t.me/test_bot?start=t_MYCODE"


def test_ticket_link_contains_code():
    with patch.object(config, "BOT_USERNAME", "somebot"):
        code = "abc123"
        link = tickets.ticket_link(code)
    assert code in link


def test_ticket_link_deep_link_prefix():
    with patch.object(config, "BOT_USERNAME", "bot"):
        link = tickets.ticket_link("XYZ")
    assert "?start=t_" in link


def test_make_qr_png_returns_buffered_input():
    result = tickets.make_qr_png("https://t.me/bot?start=t_test")
    assert isinstance(result, BufferedInputFile)


def test_make_qr_png_filename_is_ticket():
    result = tickets.make_qr_png("some_data")
    assert result.filename == "ticket.png"


def test_make_qr_png_is_valid_png():
    """Файл начинается с PNG magic bytes."""
    PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
    result = tickets.make_qr_png("test_data")
    assert result.data[:8] == PNG_MAGIC


def test_make_qr_png_non_empty():
    result = tickets.make_qr_png("content")
    assert len(result.data) > 100  # реальное PNG не бывает меньше 100 байт
