"""Тесты Admin-хендлеров (handlers/admin.py)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import config
import db
from handlers.admin import (
    on_admin_decision,
    cmd_stats,
    cmd_addpost,
    cmd_broadcast,
    on_broadcast_segment,
    _pending_broadcast,
)
from tests.conftest import make_message, make_callback, make_bot


# ==================== on_admin_decision (confirm) ====================

async def test_confirm_first_time_assigns_raffle_and_ticket(fresh_db):
    uid = 1000
    await db.ensure_user(uid, "user1000")
    await db.set_name(uid, "Test User")
    await db.set_order(uid, 2, "vnd", "400 000 ₫", db.STATUS_AWAITING_CONFIRMATION)

    call = make_callback(data=f"adm:confirm:{uid}", user_id=9999, username="admin_user")
    call.message.caption = "Карточка"
    call.message.edit_caption = AsyncMock()
    bot = make_bot()

    with patch("sheets.sync_registration", new=AsyncMock()), \
         patch("config.BOT_USERNAME", "test_bot"):
        await on_admin_decision(call, bot)

    reg = await db.get_registration(uid)
    assert reg["status"] == db.STATUS_CONFIRMED_ONLINE
    assert reg["ticket_code"] is not None
    assert reg["raffle_numbers"] is not None
    nums = reg["raffle_numbers"].split(",")
    assert len(nums) == 2  # qty=2

    bot.send_message.assert_awaited()
    bot.send_photo.assert_awaited()  # QR-билет
    call.answer.assert_awaited()


async def test_confirm_already_confirmed_skips(fresh_db):
    uid = 1001
    await db.ensure_user(uid, "user1001")
    await db.set_order(uid, 1, "vnd", "200 000 ₫", db.STATUS_CONFIRMED_ONLINE)

    call = make_callback(data=f"adm:confirm:{uid}", user_id=9999)
    bot = make_bot()

    await on_admin_decision(call, bot)

    # Должен вернуть "уже подтверждено" без изменений
    call.answer.assert_awaited()
    answer_text = call.answer.call_args[0][0]
    assert "уже" in answer_text.lower() or "подтверждено" in answer_text.lower()
    bot.send_message.assert_not_awaited()


async def test_confirm_user_not_found(fresh_db):
    call = make_callback(data="adm:confirm:99999", user_id=9999)
    bot = make_bot()

    await on_admin_decision(call, bot)

    call.answer.assert_awaited()
    # show_alert=True + текст об ошибке
    kwargs = call.answer.call_args[1]
    assert kwargs.get("show_alert") is True


async def test_confirm_assigns_sequential_raffle_numbers(fresh_db):
    # Два пользователя подтверждаются — номера не пересекаются
    for uid, qty in [(2000, 3), (2001, 2)]:
        await db.ensure_user(uid, f"u{uid}")
        await db.set_order(uid, qty, "vnd", "x", db.STATUS_AWAITING_CONFIRMATION)

    for uid in [2000, 2001]:
        call = make_callback(data=f"adm:confirm:{uid}", user_id=9999, username="adm")
        call.message.caption = "Card"
        call.message.edit_caption = AsyncMock()
        bot = make_bot()
        with patch("sheets.sync_registration", new=AsyncMock()), \
             patch("config.BOT_USERNAME", "bot"):
            await on_admin_decision(call, bot)

    reg0 = await db.get_registration(2000)
    reg1 = await db.get_registration(2001)
    nums0 = set(int(n) for n in reg0["raffle_numbers"].split(","))
    nums1 = set(int(n) for n in reg1["raffle_numbers"].split(","))
    assert nums0.isdisjoint(nums1)


async def test_confirm_no_qr_without_bot_username(fresh_db):
    uid = 1002
    await db.ensure_user(uid, "user1002")
    await db.set_order(uid, 1, "vnd", "x", db.STATUS_AWAITING_CONFIRMATION)

    call = make_callback(data=f"adm:confirm:{uid}", user_id=9999, username="adm")
    call.message.caption = "Card"
    call.message.edit_caption = AsyncMock()
    bot = make_bot()

    with patch("sheets.sync_registration", new=AsyncMock()), \
         patch("config.BOT_USERNAME", ""):  # нет username → нет QR
        await on_admin_decision(call, bot)

    # Подтверждение текстом есть, QR нет
    bot.send_message.assert_awaited()
    bot.send_photo.assert_not_awaited()


# ==================== on_admin_decision (reject) ====================

async def test_reject_updates_status(fresh_db):
    uid = 1010
    await db.ensure_user(uid, "user1010")
    await db.set_order(uid, 1, "vnd", "x", db.STATUS_AWAITING_CONFIRMATION)

    call = make_callback(data=f"adm:reject:{uid}", user_id=9999, username="adm")
    call.message.caption = "Card"
    call.message.edit_caption = AsyncMock()
    bot = make_bot()

    with patch("sheets.sync_registration", new=AsyncMock()):
        await on_admin_decision(call, bot)

    reg = await db.get_registration(uid)
    assert reg["status"] == db.STATUS_REJECTED
    bot.send_message.assert_awaited()  # уведомление пользователю
    call.answer.assert_awaited()


async def test_reject_user_not_found(fresh_db):
    call = make_callback(data="adm:reject:88888", user_id=9999)
    bot = make_bot()

    await on_admin_decision(call, bot)

    call.answer.assert_awaited()
    kwargs = call.answer.call_args[1]
    assert kwargs.get("show_alert") is True


async def test_reject_notifies_user(fresh_db):
    uid = 1011
    await db.ensure_user(uid, "user1011")
    await db.set_order(uid, 1, "rub", "650 ₽", db.STATUS_AWAITING_CONFIRMATION)

    call = make_callback(data=f"adm:reject:{uid}", user_id=9999, username="adm")
    call.message.caption = "Card"
    call.message.edit_caption = AsyncMock()
    bot = make_bot()

    with patch("sheets.sync_registration", new=AsyncMock()):
        await on_admin_decision(call, bot)

    bot.send_message.assert_awaited_once()
    send_args = bot.send_message.call_args[0]
    assert send_args[0] == uid
    assert "подтвердить" in send_args[1].lower() or "скрин" in send_args[1].lower()


# ==================== cmd_stats ====================

async def test_stats_empty_db(fresh_db):
    msg = make_message(user_id=9999)

    await cmd_stats(msg)

    msg.answer.assert_awaited_once()
    text = msg.answer.call_args[0][0]
    assert "Статистика" in text
    assert "0" in text


async def test_stats_with_data(fresh_db):
    await db.ensure_user(3000, "u3000")
    await db.set_order(3000, 3, "vnd", "600 000 ₫", db.STATUS_CONFIRMED_ONLINE)
    await db.ensure_user(3001, "u3001")
    await db.set_order(3001, 1, "door", "300 000 ₫", db.STATUS_DOOR)

    msg = make_message(user_id=9999)
    await cmd_stats(msg)

    text = msg.answer.call_args[0][0]
    assert "3" in text  # 3 подтверждённых
    assert "Статистика" in text


async def test_stats_shows_checkin_info(fresh_db):
    await db.ensure_user(3010, "u3010")
    await db.set_order(3010, 2, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    await db.check_in(3010, 2)

    msg = make_message(user_id=9999)
    await cmd_stats(msg)

    text = msg.answer.call_args[0][0]
    assert "входе" in text.lower() or "отмечено" in text.lower()


# ==================== cmd_addpost ====================

async def test_addpost_text_argument(fresh_db):
    msg = make_message(user_id=9999, text="/addpost Текст нашего поста")
    msg.reply_to_message = None

    await cmd_addpost(msg)

    post = await db.get_next_post()
    assert post is not None
    assert post["caption"] == "Текст нашего поста"
    assert post["file_path"] is None
    msg.answer.assert_awaited_once()


async def test_addpost_reply_text(fresh_db):
    msg = make_message(user_id=9999, text="/addpost")
    reply = MagicMock()
    reply.text = "Текст из ответа"
    reply.photo = None
    msg.reply_to_message = reply

    await cmd_addpost(msg)

    post = await db.get_next_post()
    assert post["caption"] == "Текст из ответа"


async def test_addpost_reply_photo(fresh_db):
    msg = make_message(user_id=9999, text="/addpost")
    reply = MagicMock()
    reply.photo = [MagicMock()]
    reply.photo[-1].file_id = "file_id_xyz"
    reply.text = None
    reply.caption = "Подпись"
    msg.reply_to_message = reply

    await cmd_addpost(msg)

    post = await db.get_next_post()
    assert post["file_path"] == "file_id_xyz"
    assert post["caption"] == "Подпись"


async def test_addpost_no_content_shows_help(fresh_db):
    msg = make_message(user_id=9999, text="/addpost")
    msg.reply_to_message = None

    await cmd_addpost(msg)

    assert await db.count_unpublished_posts() == 0
    msg.answer.assert_awaited_once()
    text = msg.answer.call_args[0][0]
    assert "addpost" in text


async def test_addpost_increments_queue(fresh_db):
    for i in range(3):
        msg = make_message(user_id=9999, text=f"/addpost Пост {i + 1}")
        msg.reply_to_message = None
        await cmd_addpost(msg)

    assert await db.count_unpublished_posts() == 3


# ==================== cmd_broadcast / on_broadcast_segment ====================

async def test_broadcast_text_stores_pending(fresh_db):
    uid = 9999
    msg = make_message(user_id=uid, text="/broadcast Текст рассылки")
    msg.reply_to_message = None

    await cmd_broadcast(msg)

    assert uid in _pending_broadcast
    assert _pending_broadcast[uid]["type"] == "text"
    assert _pending_broadcast[uid]["text"] == "Текст рассылки"
    msg.answer.assert_awaited_once()
    _pending_broadcast.pop(uid, None)


async def test_broadcast_no_content_shows_help(fresh_db):
    uid = 8888
    msg = make_message(user_id=uid, text="/broadcast")
    msg.reply_to_message = None

    await cmd_broadcast(msg)

    assert uid not in _pending_broadcast
    msg.answer.assert_awaited_once()


async def test_broadcast_segment_cancel(fresh_db):
    uid = 7777
    _pending_broadcast[uid] = {"type": "text", "text": "Hello"}

    call = make_callback(data="bc:cancel", user_id=uid)
    call.message.edit_reply_markup = AsyncMock()
    bot = make_bot()

    await on_broadcast_segment(call, bot)

    assert uid not in _pending_broadcast
    call.answer.assert_awaited()


async def test_broadcast_segment_no_pending(fresh_db):
    uid = 6666
    # Нет pending — должен попросить начать заново
    call = make_callback(data="bc:A", user_id=uid)
    bot = make_bot()

    await on_broadcast_segment(call, bot)

    call.answer.assert_awaited()
    kwargs = call.answer.call_args[1]
    assert kwargs.get("show_alert") is True


async def test_broadcast_segment_A_sends_to_unpaid(fresh_db):
    # Пользователь A (awaiting_payment)
    await db.ensure_user(4001, "u4001")
    await db.set_order(4001, 1, "vnd", "x", db.STATUS_AWAITING_PAYMENT)

    uid_admin = 4999
    _pending_broadcast[uid_admin] = {"type": "text", "text": "Ещё не оплатили?"}

    call = make_callback(data="bc:A", user_id=uid_admin)
    call.message.edit_reply_markup = AsyncMock()
    call.message.answer = AsyncMock()
    bot = make_bot()

    with patch("broadcast.broadcast", new=AsyncMock(return_value=(1, 0))):
        await on_broadcast_segment(call, bot)

    assert uid_admin not in _pending_broadcast
    call.message.answer.assert_awaited_once()


async def test_broadcast_segment_all(fresh_db):
    await db.ensure_user(5001, "u5001")
    await db.ensure_user(5002, "u5002")

    uid_admin = 5999
    _pending_broadcast[uid_admin] = {"type": "text", "text": "Всем привет!"}

    call = make_callback(data="bc:all", user_id=uid_admin)
    call.message.edit_reply_markup = AsyncMock()
    call.message.answer = AsyncMock()
    bot = make_bot()

    with patch("broadcast.broadcast", new=AsyncMock(return_value=(2, 0))):
        await on_broadcast_segment(call, bot)

    assert uid_admin not in _pending_broadcast
