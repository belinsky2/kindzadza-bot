"""Тесты функции рассылки с троттлингом (broadcast.py)."""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramBadRequest

import config
import broadcast as bc


def make_bot():
    return AsyncMock()


async def test_broadcast_empty_list(monkeypatch):
    monkeypatch.setattr(config, "BROADCAST_RATE", 100)
    bot = make_bot()
    send = AsyncMock()
    sent, failed = await bc.broadcast(bot, [], send)
    assert sent == 0
    assert failed == 0
    send.assert_not_awaited()


async def test_broadcast_all_success(monkeypatch):
    monkeypatch.setattr(config, "BROADCAST_RATE", 1000)
    bot = make_bot()
    send = AsyncMock()
    sent, failed = await bc.broadcast(bot, [1, 2, 3], send)
    assert sent == 3
    assert failed == 0
    assert send.await_count == 3


async def test_broadcast_forbidden_counts_as_failed(monkeypatch):
    monkeypatch.setattr(config, "BROADCAST_RATE", 1000)
    bot = make_bot()

    async def send_raising(b, uid):
        raise TelegramForbiddenError(method=MagicMock(), message="Forbidden")

    sent, failed = await bc.broadcast(bot, [10, 20], send_raising)
    assert sent == 0
    assert failed == 2


async def test_broadcast_bad_request_counts_as_failed(monkeypatch):
    monkeypatch.setattr(config, "BROADCAST_RATE", 1000)
    bot = make_bot()

    async def send_raising(b, uid):
        raise TelegramBadRequest(method=MagicMock(), message="Bad Request")

    sent, failed = await bc.broadcast(bot, [1], send_raising)
    assert sent == 0
    assert failed == 1


async def test_broadcast_mixed_results(monkeypatch):
    monkeypatch.setattr(config, "BROADCAST_RATE", 1000)
    bot = make_bot()
    results = {1: "ok", 2: "forbidden", 3: "ok"}

    async def send_one(b, uid):
        if results[uid] == "forbidden":
            raise TelegramForbiddenError(method=MagicMock(), message="Forbidden")

    sent, failed = await bc.broadcast(bot, [1, 2, 3], send_one)
    assert sent == 2
    assert failed == 1


async def test_broadcast_retry_after_then_success(monkeypatch):
    monkeypatch.setattr(config, "BROADCAST_RATE", 1000)
    bot = make_bot()
    call_count = {"n": 0}

    async def send_retry(b, uid):
        call_count["n"] += 1
        if call_count["n"] == 1:
            err = TelegramRetryAfter(method=MagicMock(), message="", retry_after=0)
            raise err

    with patch("asyncio.sleep", new=AsyncMock()):
        sent, failed = await bc.broadcast(bot, [1], send_retry)

    assert sent == 1
    assert failed == 0


async def test_broadcast_retry_after_then_fail(monkeypatch):
    monkeypatch.setattr(config, "BROADCAST_RATE", 1000)
    bot = make_bot()

    async def send_always_retry(b, uid):
        err = TelegramRetryAfter(method=MagicMock(), message="", retry_after=0)
        raise err

    with patch("asyncio.sleep", new=AsyncMock()):
        sent, failed = await bc.broadcast(bot, [1], send_always_retry)

    assert sent == 0
    assert failed == 1


async def test_broadcast_rate_delays(monkeypatch):
    monkeypatch.setattr(config, "BROADCAST_RATE", 10)  # 0.1 sec delay
    bot = make_bot()
    sleep_calls = []

    original_sleep = asyncio.sleep

    async def mock_sleep(t):
        sleep_calls.append(t)

    send = AsyncMock()
    with patch("asyncio.sleep", side_effect=mock_sleep):
        await bc.broadcast(bot, [1, 2, 3], send)

    assert len(sleep_calls) == 3
    for delay in sleep_calls:
        assert abs(delay - 0.1) < 0.001


async def test_broadcast_general_exception_counts_as_failed(monkeypatch):
    monkeypatch.setattr(config, "BROADCAST_RATE", 1000)
    bot = make_bot()

    async def send_raising(b, uid):
        raise RuntimeError("Unexpected error")

    sent, failed = await bc.broadcast(bot, [1, 2], send_raising)
    assert sent == 0
    assert failed == 2
