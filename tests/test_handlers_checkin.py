"""Тесты check-in через QR-сканирование (handlers/checkin.py)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import config
import db
from handlers.checkin import process_scan, on_checkin, is_staff
from tests.conftest import make_message, make_callback, make_bot


# ==================== is_staff ====================

async def test_is_staff_admin_id(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_IDS", {777})
    bot = make_bot()
    result = await is_staff(bot, 777)
    assert result is True


async def test_is_staff_not_in_list(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_IDS", {777})
    monkeypatch.setattr(config, "ADMIN_GROUP_ID", 0)
    bot = make_bot()
    result = await is_staff(bot, 999)
    assert result is False


async def test_is_staff_group_member(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_IDS", set())
    monkeypatch.setattr(config, "ADMIN_GROUP_ID", -100123)
    bot = make_bot(is_staff=True)
    result = await is_staff(bot, 111)
    assert result is True


async def test_is_staff_group_member_kicked(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_IDS", set())
    monkeypatch.setattr(config, "ADMIN_GROUP_ID", -100123)
    bot = make_bot(is_staff=False)  # status='kicked'
    result = await is_staff(bot, 222)
    assert result is False


async def test_is_staff_group_check_exception(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_IDS", set())
    monkeypatch.setattr(config, "ADMIN_GROUP_ID", -100123)
    bot = make_bot()
    bot.get_chat_member = AsyncMock(side_effect=Exception("error"))
    result = await is_staff(bot, 333)
    assert result is False


# ==================== process_scan ====================

async def test_process_scan_ticket_not_found(fresh_db):
    msg = make_message(user_id=100)
    bot = make_bot()

    await process_scan(msg, bot, "NONEXISTENT_CODE")

    msg.answer.assert_awaited_once()
    text = msg.answer.call_args[0][0]
    assert "не найден" in text.lower() or "❌" in text


async def test_process_scan_owner_views_own_ticket(fresh_db, monkeypatch):
    uid = 200
    await db.ensure_user(uid, "owner_user")
    await db.set_order(uid, 2, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    await db.set_ticket_code(uid, "OWNER_CODE")

    monkeypatch.setattr(config, "ADMIN_IDS", set())
    monkeypatch.setattr(config, "ADMIN_GROUP_ID", -100999)

    msg = make_message(user_id=uid, username="owner_user")
    bot = make_bot(is_staff=False)

    await process_scan(msg, bot, "OWNER_CODE")

    msg.answer.assert_awaited_once()
    text = msg.answer.call_args[0][0]
    assert "твой билет" in text.lower() or "✅" in text


async def test_process_scan_foreign_user_denied(fresh_db, monkeypatch):
    uid_owner = 300
    uid_other = 301

    await db.ensure_user(uid_owner, "owner300")
    await db.set_order(uid_owner, 1, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    await db.set_ticket_code(uid_owner, "FOREIGN_CODE")

    monkeypatch.setattr(config, "ADMIN_IDS", set())
    monkeypatch.setattr(config, "ADMIN_GROUP_ID", -100999)

    msg = make_message(user_id=uid_other, username="stranger")
    bot = make_bot(is_staff=False)

    await process_scan(msg, bot, "FOREIGN_CODE")

    msg.answer.assert_awaited_once()
    text = msg.answer.call_args[0][0]
    assert "чужой" in text.lower() or "организатор" in text.lower()


async def test_process_scan_staff_sees_checkin_card(fresh_db, monkeypatch):
    uid = 400
    await db.ensure_user(uid, "guest400")
    await db.set_name(uid, "Guest Name")
    await db.set_order(uid, 3, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    await db.set_ticket_code(uid, "STAFF_CODE")

    monkeypatch.setattr(config, "ADMIN_IDS", {9999})

    msg = make_message(user_id=9999, username="organizer")
    bot = make_bot()

    await process_scan(msg, bot, "STAFF_CODE")

    msg.answer.assert_awaited_once()
    # Карточка с кнопками
    call_kwargs = msg.answer.call_args[1]
    assert "reply_markup" in call_kwargs


async def test_process_scan_already_checked_in(fresh_db, monkeypatch):
    uid = 500
    await db.ensure_user(uid, "guest500")
    await db.set_order(uid, 1, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    await db.set_ticket_code(uid, "USED_CODE")
    await db.check_in(uid, 1)

    monkeypatch.setattr(config, "ADMIN_IDS", {9999})

    msg = make_message(user_id=9999, username="org")
    bot = make_bot()

    await process_scan(msg, bot, "USED_CODE")

    msg.answer.assert_awaited_once()
    text = msg.answer.call_args[0][0]
    assert "уже" in text.lower() or "отмечен" in text.lower()


# ==================== on_checkin ====================

async def test_checkin_non_staff_denied(fresh_db, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_IDS", set())
    monkeypatch.setattr(config, "ADMIN_GROUP_ID", -100999)

    call = make_callback(data="ci:SOME_CODE:1", user_id=888)
    bot = make_bot(is_staff=False)

    await on_checkin(call, bot)

    call.answer.assert_awaited()
    kwargs = call.answer.call_args[1]
    assert kwargs.get("show_alert") is True


async def test_checkin_ticket_not_found(fresh_db, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_IDS", {9999})

    call = make_callback(data="ci:INVALID:1", user_id=9999)
    bot = make_bot()

    await on_checkin(call, bot)

    call.answer.assert_awaited()
    kwargs = call.answer.call_args[1]
    assert kwargs.get("show_alert") is True


async def test_checkin_already_done(fresh_db, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_IDS", {9999})

    uid = 600
    await db.ensure_user(uid, "guest600")
    await db.set_order(uid, 2, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    await db.set_ticket_code(uid, "ALREADY_CODE")
    await db.check_in(uid, 2)

    call = make_callback(data="ci:ALREADY_CODE:2", user_id=9999)
    call.message.edit_text = AsyncMock()
    bot = make_bot()

    await on_checkin(call, bot)

    call.answer.assert_awaited()
    # Показывает "уже отмечен"
    answer_text = call.answer.call_args[0][0]
    assert "отмечен" in answer_text.lower() or "уже" in answer_text.lower()


async def test_checkin_success_marks_db(fresh_db, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_IDS", {9999})

    uid = 700
    await db.ensure_user(uid, "guest700")
    await db.set_name(uid, "Guest 700")
    await db.set_order(uid, 3, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    await db.set_ticket_code(uid, "SUCCESS_CODE")

    call = make_callback(data="ci:SUCCESS_CODE:2", user_id=9999)
    call.message.edit_text = AsyncMock()
    bot = make_bot()

    await on_checkin(call, bot)

    reg = await db.get_registration(uid)
    assert reg["checked_in_at"] is not None
    assert reg["arrived_count"] == 2
    call.answer.assert_awaited()


async def test_checkin_success_one_of_many(fresh_db, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_IDS", {9999})

    uid = 701
    await db.ensure_user(uid, "guest701")
    await db.set_order(uid, 5, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    await db.set_ticket_code(uid, "PARTIAL_CODE")

    call = make_callback(data="ci:PARTIAL_CODE:3", user_id=9999)
    call.message.edit_text = AsyncMock()
    bot = make_bot()

    await on_checkin(call, bot)

    reg = await db.get_registration(uid)
    assert reg["arrived_count"] == 3


async def test_checkin_prevents_double_scan(fresh_db, monkeypatch):
    """Билет с checked_in_at не может быть отмечен повторно."""
    monkeypatch.setattr(config, "ADMIN_IDS", {9999})

    uid = 702
    await db.ensure_user(uid, "guest702")
    await db.set_order(uid, 1, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    await db.set_ticket_code(uid, "ONEUSE_CODE")

    # Первое сканирование — успешно
    call1 = make_callback(data="ci:ONEUSE_CODE:1", user_id=9999)
    call1.message.edit_text = AsyncMock()
    bot = make_bot()
    await on_checkin(call1, bot)

    # Второе сканирование — уже отмечен
    call2 = make_callback(data="ci:ONEUSE_CODE:1", user_id=9999)
    call2.message.edit_text = AsyncMock()
    await on_checkin(call2, bot)

    answer_text = call2.answer.call_args[0][0]
    assert "отмечен" in answer_text.lower() or "уже" in answer_text.lower()


# ==================== Накопительная отметка (докопка прихода) ====================

async def test_checkin_partial_then_complete(fresh_db, monkeypatch):
    """3 из 4 пришли сразу, потом 1 опоздавший по тому же QR → все на месте."""
    monkeypatch.setattr(config, "ADMIN_IDS", {9999})
    uid = 710
    await db.ensure_user(uid, "guest710")
    await db.set_order(uid, 4, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    await db.set_ticket_code(uid, "PARTIAL2_CODE")

    # пришли 3
    call1 = make_callback(data="ci:PARTIAL2_CODE:3", user_id=9999)
    call1.message.edit_text = AsyncMock()
    bot = make_bot()
    await on_checkin(call1, bot)

    reg = await db.get_registration(uid)
    assert reg["arrived_count"] == 3  # частично

    # опоздавший показывает тот же QR — карточка показывает остаток
    msg = make_message(user_id=9999, username="org")
    await process_scan(msg, bot, "PARTIAL2_CODE")
    card = msg.answer.call_args[0][0]
    assert "Осталось отметить" in card

    # отмечаем последнего
    call2 = make_callback(data="ci:PARTIAL2_CODE:1", user_id=9999)
    call2.message.edit_text = AsyncMock()
    await on_checkin(call2, bot)

    reg = await db.get_registration(uid)
    assert reg["arrived_count"] == 4  # все пришли
    done_text = call2.message.edit_text.call_args[0][0]
    assert "Все на месте" in done_text


async def test_checkin_rescan_after_full_shows_extra_pay(fresh_db, monkeypatch):
    """После полной отметки повторный скан → 'оплата на месте'."""
    monkeypatch.setattr(config, "ADMIN_IDS", {9999})
    uid = 711
    await db.ensure_user(uid, "guest711")
    await db.set_order(uid, 2, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    await db.set_ticket_code(uid, "FULL_CODE")

    call = make_callback(data="ci:FULL_CODE:2", user_id=9999)
    call.message.edit_text = AsyncMock()
    bot = make_bot()
    await on_checkin(call, bot)  # все 2 пришли

    msg = make_message(user_id=9999, username="org")
    await process_scan(msg, bot, "FULL_CODE")
    text = msg.answer.call_args[0][0]
    assert "уже" in text.lower()
    assert "на месте" in text.lower()


async def test_add_arrival_caps_at_qty(fresh_db):
    uid = 712
    await db.ensure_user(uid, "guest712")
    await db.set_order(uid, 3, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)

    assert await db.add_arrival(uid, 2) == 2
    # пытаемся добавить ещё 5 — потолок qty=3
    assert await db.add_arrival(uid, 5) == 3
    reg = await db.get_registration(uid)
    assert reg["arrived_count"] == 3


# ==================== Интеграция: полный цикл регистрации и check-in ====================

async def test_full_cycle_register_confirm_checkin(fresh_db, monkeypatch):
    """Полный цикл: регистрация → подтверждение → чек-ин."""
    monkeypatch.setattr(config, "ADMIN_IDS", {9999})
    monkeypatch.setattr(config, "BOT_USERNAME", "test_bot")

    uid = 800
    await db.ensure_user(uid, "cycle_user")
    await db.set_name(uid, "Cycle User")
    await db.set_order(uid, 2, "vnd", "400 000 ₫", db.STATUS_AWAITING_CONFIRMATION)

    # Администратор подтверждает
    from handlers.admin import on_admin_decision
    call_confirm = make_callback(data=f"adm:confirm:{uid}", user_id=9999, username="org")
    call_confirm.message.caption = "Card"
    call_confirm.message.edit_caption = AsyncMock()
    bot = make_bot(is_staff=True)

    with patch("sheets.sync_registration", new=AsyncMock()):
        await on_admin_decision(call_confirm, bot)

    reg = await db.get_registration(uid)
    assert reg["status"] == db.STATUS_CONFIRMED_ONLINE
    code = reg["ticket_code"]
    assert code is not None

    # Гость приходит и сканирует QR
    call_checkin = make_callback(data=f"ci:{code}:2", user_id=9999)
    call_checkin.message.edit_text = AsyncMock()

    await on_checkin(call_checkin, bot)

    reg = await db.get_registration(uid)
    assert reg["checked_in_at"] is not None
    assert reg["arrived_count"] == 2
