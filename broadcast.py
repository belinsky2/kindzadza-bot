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
