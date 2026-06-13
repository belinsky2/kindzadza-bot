"""Тесты Admin-хендлеров (handlers/admin.py)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import config
import db
from handlers.admin import (
    on_admin_decision,
    cmd_raffle,
    on_raffle,
    cmd_stats,
    cmd_addpost,
    cmd_broadcast,
    cmd_refund,
    on_broadcast_segment,
    _pending_broadcast,
)
from tests.conftest import make_message, make_callback, make_bot


# ==================== cmd_raffle / on_raffle ====================

async def _setup_raffle_guests(n: int) -> list[int]:
    """Создаёт n подтверждённых онлайн-гостей с номерами розыгрыша."""
    uids = []
    for i in range(n):
        uid = 9000 + i
        await db.ensure_user(uid, f"rguest{i}")
        await db.set_name(uid, f"Гость {i}")
        await db.set_order(uid, 1, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
        await db.set_raffle_numbers(uid, [i + 1])
        uids.append(uid)
    return uids


async def test_raffle_cmd_shows_preview(fresh_db):
    await _setup_raffle_guests(5)
    msg = make_message(user_id=9999, text="/raffle")

    await cmd_raffle(msg)

    msg.answer.assert_awaited_once()
    text = msg.answer.call_args[0][0]
    assert "розыгрыш" in text.lower()
    assert "5" in text  # 5 участников


async def test_raffle_cmd_not_enough(fresh_db):
    await _setup_raffle_guests(2)  # меньше 3
    msg = make_message(user_id=9999, text="/raffle")

    await cmd_raffle(msg)

    text = msg.answer.call_args[0][0]
    assert "недостаточно" in text.lower()


async def test_raffle_picks_3_unique_winners(fresh_db):
    uids = await _setup_raffle_guests(10)
    bot = make_bot()

    call = make_callback(data="raffle:run", user_id=9999)
    call.message.edit_text = AsyncMock()

    await on_raffle(call, bot)

    # 3 победителя получили поздравление
    winner_calls = [
        c for c in bot.send_message.await_args_list
        if "выиграл" in (c.args[1] if len(c.args) > 1 else "")
    ]
    assert len(winner_calls) == 3
    winner_uids = {c.args[0] for c in winner_calls}
    assert len(winner_uids) == 3  # уникальные гости

    # 7 остальных получили утешительное
    loser_calls = [
        c for c in bot.send_message.await_args_list
        if "удача" in (c.args[1] if len(c.args) > 1 else "")
    ]
    assert len(loser_calls) == 7

    # Флаг выставлен
    assert await db.get_meta("raffle_done") == "1"


async def test_raffle_cancel(fresh_db):
    call = make_callback(data="raffle:cancel", user_id=9999)
    call.message.edit_reply_markup = AsyncMock()
    bot = make_bot()

    await on_raffle(call, bot)

    bot.send_message.assert_not_awaited()
    call.answer.assert_awaited()


async def test_raffle_already_done_shows_warning(fresh_db):
    await _setup_raffle_guests(5)
    await db.set_meta("raffle_done", "1")
    msg = make_message(user_id=9999, text="/raffle")

    await cmd_raffle(msg)

    text = msg.answer.call_args[0][0]
    assert "уже проводился" in text.lower()


async def test_raffle_guest_with_2_tickets_has_2_chances(fresh_db):
    """Гость с 2 билетами имеет 2 номера в пуле — пул считается корректно."""
    uid = 9100
    await db.ensure_user(uid, "rich")
    await db.set_order(uid, 2, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    await db.set_raffle_numbers(uid, [1, 2])

    for i in range(5):
        u = 9101 + i
        await db.ensure_user(u, f"r{i}")
        await db.set_order(u, 1, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
        await db.set_raffle_numbers(u, [10 + i])

    pool = await db.get_raffle_pool()
    uid_counts = {}
    for u, _ in pool:
        uid_counts[u] = uid_counts.get(u, 0) + 1
    assert uid_counts[uid] == 2  # у богатого гостя 2 шанса


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


async def test_confirm_repeat_purchase_accumulates(fresh_db):
    """Докупка: гость уже подтверждён, покупает ещё — номера копятся, qty растёт."""
    uid = 1500
    await db.ensure_user(uid, "repeatguest")
    await db.set_name(uid, "Гость")
    await db.set_order(uid, 2, "vnd", "400 000 ₫", db.STATUS_AWAITING_CONFIRMATION)

    # первое подтверждение → 2 номера
    call1 = make_callback(data=f"adm:confirm:{uid}", user_id=9999, username="adm")
    call1.message.caption = "Card"
    call1.message.edit_caption = AsyncMock()
    bot1 = make_bot()
    with patch("sheets.sync_registration", new=AsyncMock()), \
         patch("config.BOT_USERNAME", "bot"):
        await on_admin_decision(call1, bot1)

    reg = await db.get_registration(uid)
    first_numbers = reg["raffle_numbers"].split(",")
    assert len(first_numbers) == 2

    # гость докупает 1 билет: воронка перезаписала qty и статус, номера сохранились
    await db.set_order(uid, 1, "vnd", "200 000 ₫", db.STATUS_AWAITING_CONFIRMATION)

    call2 = make_callback(data=f"adm:confirm:{uid}", user_id=9999, username="adm")
    call2.message.caption = "Card"
    call2.message.edit_caption = AsyncMock()
    bot2 = make_bot()
    with patch("sheets.sync_registration", new=AsyncMock()), \
         patch("config.BOT_USERNAME", "bot"):
        await on_admin_decision(call2, bot2)

    reg = await db.get_registration(uid)
    nums = reg["raffle_numbers"].split(",")
    assert len(nums) == 3                  # 2 старых + 1 докупленный
    assert nums[:2] == first_numbers       # прежние номера на месте
    assert reg["qty"] == 3                  # итоговое число билетов

    # одно сообщение об обновлении заказа, без повторных меню/просьбы о заказе
    bot2.send_message.assert_awaited_once()
    sent = bot2.send_message.await_args_list[0].args[1]
    assert "обновлён" in sent.lower()


async def test_confirm_no_qr_without_bot_username(fresh_db):
    uid = 1002
    await db.ensure_user(uid, "user1002")
    await db.set_order(uid, 1, "vnd", "x", db.STATUS_AWAITING_CONFIRMATION)

    call = make_callback(data=f"adm:confirm:{uid}", user_id=9999, username="adm")
    call.message.caption = "Card"
    call.message.edit_caption = AsyncMock()
    bot = make_bot()

    with patch("sheets.sync_registration", new=AsyncMock()), \
         patch("config.BOT_USERNAME", ""), \
         patch("config.MENU_IMAGE", "/nonexistent/menu.jpg"):  # нет username → нет QR, нет меню
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


# ==================== cmd_refund ====================

async def test_refund_by_user_id_voids_ticket(fresh_db):
    uid = 6001
    await db.ensure_user(uid, "refundguest")
    await db.set_name(uid, "Возвратный")
    await db.set_order(uid, 2, "vnd", "400 000 ₫", db.STATUS_CONFIRMED_ONLINE)
    await db.set_raffle_numbers(uid, [5, 6])
    await db.set_ticket_code(uid, "ABC123")
    await db.add_arrival(uid, 1)

    msg = make_message(user_id=9999, text=f"/refund {uid}")
    with patch("sheets.sync_all", new=AsyncMock(return_value=1)):
        await cmd_refund(msg)

    reg = await db.get_registration(uid)
    assert reg["status"] == db.STATUS_REFUNDED
    assert reg["qty"] == 0
    assert reg["raffle_numbers"] is None
    assert reg["ticket_code"] is None
    assert reg["arrived_count"] is None
    assert reg["checked_in_at"] is None
    # место освобождено
    assert await db.seats_taken() == 0
    # QR больше не резолвится
    assert await db.get_by_ticket_code("ABC123") is None
    msg.answer.assert_awaited_once()


async def test_refund_by_username(fresh_db):
    uid = 6002
    await db.ensure_user(uid, "IgorM7317")
    await db.set_order(uid, 1, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)

    # регистронезависимо и с @
    msg = make_message(user_id=9999, text="/refund @igorm7317")
    with patch("sheets.sync_all", new=AsyncMock(return_value=1)):
        await cmd_refund(msg)

    reg = await db.get_registration(uid)
    assert reg["status"] == db.STATUS_REFUNDED


async def test_refund_no_arg_shows_usage(fresh_db):
    msg = make_message(user_id=9999, text="/refund")
    await cmd_refund(msg)
    msg.answer.assert_awaited_once()
    text = msg.answer.call_args[0][0]
    assert "refund" in text.lower()


async def test_refund_not_found(fresh_db):
    msg = make_message(user_id=9999, text="/refund 424242")
    with patch("sheets.sync_all", new=AsyncMock(return_value=1)):
        await cmd_refund(msg)
    text = msg.answer.call_args[0][0]
    assert "не найден" in text.lower()


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


async def test_broadcast_segment_paid_targets_confirmed(fresh_db):
    import segments
    await db.ensure_user(5101, "u5101")
    await db.set_order(5101, 1, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    await db.ensure_user(5102, "u5102")  # просто зашёл — не должен попасть

    uid_admin = 5199
    _pending_broadcast[uid_admin] = {"type": "text", "text": "Спасибо за оплату!"}

    call = make_callback(data="bc:paid", user_id=uid_admin)
    call.message.edit_reply_markup = AsyncMock()
    call.message.answer = AsyncMock()
    bot = make_bot()

    captured = {}

    async def fake_broadcast(b, uids, send_one):
        captured["uids"] = list(uids)
        return (len(uids), 0)

    with patch("broadcast.broadcast", new=fake_broadcast):
        await on_broadcast_segment(call, bot)

    assert captured["uids"] == [5101]
    assert uid_admin not in _pending_broadcast


async def test_broadcast_segment_unpaid_targets_everyone_else(fresh_db):
    await db.ensure_user(5201, "u5201")  # просто зашёл (new)
    await db.ensure_user(5202, "u5202")
    await db.set_order(5202, 1, "vnd", "x", db.STATUS_AWAITING_PAYMENT)
    await db.ensure_user(5203, "u5203")
    await db.set_order(5203, 1, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)  # оплатил — не попадёт

    uid_admin = 5299
    _pending_broadcast[uid_admin] = {"type": "text", "text": "Ещё не поздно купить!"}

    call = make_callback(data="bc:unpaid", user_id=uid_admin)
    call.message.edit_reply_markup = AsyncMock()
    call.message.answer = AsyncMock()
    bot = make_bot()

    captured = {}

    async def fake_broadcast(b, uids, send_one):
        captured["uids"] = list(uids)
        return (len(uids), 0)

    with patch("broadcast.broadcast", new=fake_broadcast):
        await on_broadcast_segment(call, bot)

    assert set(captured["uids"]) == {5201, 5202}
    assert uid_admin not in _pending_broadcast
