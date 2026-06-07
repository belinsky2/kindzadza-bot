"""Общие фикстуры и хелперы для всех тестов."""
from __future__ import annotations

import sys
import os

# Добавляем корень проекта в путь, чтобы импорты работали без установки пакета
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import AsyncMock, MagicMock

import config
import db as db_module


@pytest.fixture
async def fresh_db(tmp_path):
    """Чистая SQLite-БД в временной директории для каждого теста."""
    if db_module._db is not None:
        try:
            await db_module.close_db()
        except Exception:
            pass
        db_module._db = None

    original_path = config.DB_PATH
    db_path = str(tmp_path / "test.db")
    config.DB_PATH = db_path

    await db_module.init_db()
    yield db_module

    await db_module.close_db()
    db_module._db = None
    config.DB_PATH = original_path


# ---------- Фабрики мок-объектов aiogram ----------

def make_user(user_id: int = 100, username: str = "tester", full_name: str = "Test User"):
    user = MagicMock()
    user.id = user_id
    user.username = username
    user.full_name = full_name
    return user


def make_message(
    user_id: int = 100,
    username: str = "tester",
    text: str = "",
    chat_id: int | None = None,
    photo=None,
    document=None,
):
    msg = AsyncMock()
    msg.from_user = make_user(user_id, username)
    msg.text = text
    msg.photo = photo
    msg.document = document
    msg.chat = MagicMock()
    msg.chat.id = chat_id if chat_id is not None else user_id
    msg.answer = AsyncMock()
    msg.answer_photo = AsyncMock()
    return msg


def make_callback(
    data: str = "",
    user_id: int = 100,
    username: str = "tester",
    chat_id: int | None = None,
):
    call = AsyncMock()
    call.data = data
    call.from_user = make_user(user_id, username)
    call.message = make_message(user_id, username, chat_id=chat_id)
    call.answer = AsyncMock()
    return call


def make_state(data: dict | None = None):
    state = AsyncMock()
    state.clear = AsyncMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value=data or {})
    return state


def make_bot(is_staff: bool = False):
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock()
    bot.send_document = AsyncMock()

    member = MagicMock()
    member.status = "member" if is_staff else "kicked"
    bot.get_chat_member = AsyncMock(return_value=member)
    return bot


def make_command(args: str = ""):
    cmd = MagicMock()
    cmd.args = args
    return cmd
