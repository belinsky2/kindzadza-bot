"""Рассылка в личку с троттлингом и обработкой ошибок."""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

import config

log = logging.getLogger(__name__)

# send_one(bot, user_id) -> None  (выполняет сам отправку: текст/фото — на усмотрение вызывающего)
SendOne = Callable[[Bot, int], Awaitable[None]]

# Лимит подписи к фото в Telegram. Если текст длиннее — шлём фото и текст
# двумя сообщениями, иначе кнопка не прикрепится к подписи.
CAPTION_LIMIT = 1024


async def send_announce(bot: Bot, chat_id: int, text: str, photo, markup) -> None:
    """Отправить анонс: фото + текст + кнопка. Длинный текст — отдельным сообщением.

    photo — file_id (str), FSInputFile или None (тогда только текст).
    """
    if photo is not None and len(text) <= CAPTION_LIMIT:
        await bot.send_photo(chat_id, photo, caption=text, reply_markup=markup)
        return
    if photo is not None:
        await bot.send_photo(chat_id, photo)
    await bot.send_message(
        chat_id, text, reply_markup=markup, disable_web_page_preview=True
    )


async def broadcast(bot: Bot, user_ids: list[int], send_one: SendOne) -> tuple[int, int]:
    """Возвращает (отправлено, ошибок). Пропускает заблокировавших бота."""
    delay = 1 / max(1, config.BROADCAST_RATE)
    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await send_one(bot, uid)
            sent += 1
        except TelegramRetryAfter as e:
            # флуд-лимит: ждём и пробуем один раз ещё
            log.warning("RetryAfter %ss для %s", e.retry_after, uid)
            await asyncio.sleep(e.retry_after + 1)
            try:
                await send_one(bot, uid)
                sent += 1
            except Exception:
                failed += 1
        except TelegramForbiddenError:
            # пользователь заблокировал/удалил бота — это норма, пропускаем
            failed += 1
        except TelegramBadRequest:
            failed += 1
        except Exception:
            log.exception("Ошибка отправки %s", uid)
            failed += 1
        await asyncio.sleep(delay)
    return sent, failed
