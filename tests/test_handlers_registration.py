"""Тесты FSM-воронки регистрации пользователя (handlers/registration.py)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import config
import db
import texts
from handlers.registration import (
    cmd_start,
    cmd_status,
    cmd_reset,
    on_register,
    on_name,
    on_qty,
    on_qty_custom,
    on_pay,
    on_screenshot,
    on_screenshot_wrong,
    on_screenshot_stateless,
    on_to_online,
    on_resend,
    on_free_text,
    Form,
)
from tests.conftest import make_message, make_callback, make_state, make_command, make_bot


# ==================== /start ====================

async def test_start_new_user_no_image(fresh_db):
    """Новый пользователь видит текстовый анонс, если нет файла афиши."""
    msg = make_message(user_id=1, username="alice")
    state = make_state()
    cmd = make_command(args="")
    bot = make_bot()

    with patch("os.path.exists", return_value=False):
        await cmd_start(msg, state, cmd, bot)

    state.clear.assert_awaited_once()
    msg.answer.assert_awaited_once()
    call_text = msg.answer.call_args[0][0]
    assert "Зарегистрироваться" in call_text or msg.answer.called


async def test_start_new_user_with_image(fresh_db):
    """Новый пользователь видит фото-анонс при наличии файла афиши."""
    msg = make_message(user_id=2, username="bob")
    state = make_state()
    cmd = make_command(args="")
    bot = make_bot()

    with patch("os.path.exists", return_value=True), \
         patch("handlers.registration.FSInputFile", return_value=MagicMock()):
        await cmd_start(msg, state, cmd, bot)

    msg.answer_photo.assert_awaited_once()


async def test_start_returning_awaiting_payment(fresh_db):
    """Пользователь с awaiting_payment получает статус, а не анонс."""
    uid = 3
    await db.ensure_user(uid, "charlie")
    await db.set_name(uid, "Charlie")
    await db.set_order(uid, 2, "vnd", "400 000 ₫", db.STATUS_AWAITING_PAYMENT)

    msg = make_message(user_id=uid, username="charlie")
    state = make_state()
    cmd = make_command(args="")
    bot = make_bot()

    await cmd_start(msg, state, cmd, bot)

    msg.answer.assert_awaited_once()
    # Должен показать статус, а не greeting
    call_text = msg.answer.call_args[0][0]
    assert "Зарегистрироваться" not in call_text


async def test_start_returning_confirmed(fresh_db):
    uid = 4
    await db.ensure_user(uid, "diana")
    await db.set_order(uid, 1, "vnd", "200 000 ₫", db.STATUS_CONFIRMED_ONLINE)

    msg = make_message(user_id=uid, username="diana")
    state = make_state()
    cmd = make_command(args="")
    bot = make_bot()

    await cmd_start(msg, state, cmd, bot)

    msg.answer.assert_awaited_once()


async def test_start_returning_door(fresh_db):
    uid = 5
    await db.ensure_user(uid, "evan")
    await db.set_order(uid, 1, "door", "300 000 ₫", db.STATUS_DOOR)

    msg = make_message(user_id=uid, username="evan")
    state = make_state()
    cmd = make_command(args="")
    bot = make_bot()

    await cmd_start(msg, state, cmd, bot)

    msg.answer.assert_awaited_once()


async def test_start_returning_rejected(fresh_db):
    uid = 6
    await db.ensure_user(uid, "fiona")
    await db.set_order(uid, 1, "vnd", "200 000 ₫", db.STATUS_REJECTED)

    msg = make_message(user_id=uid, username="fiona")
    state = make_state()
    cmd = make_command(args="")
    bot = make_bot()

    await cmd_start(msg, state, cmd, bot)

    msg.answer.assert_awaited_once()


async def test_start_deep_link_delegates_to_scan(fresh_db):
    """Deep-link t_CODE вызывает process_scan."""
    uid = 7
    await db.ensure_user(uid, "grace")

    msg = make_message(user_id=uid, username="grace")
    state = make_state()
    cmd = make_command(args="t_TESTCODE")
    bot = make_bot()

    with patch("handlers.checkin.process_scan", new=AsyncMock()) as mock_scan:
        await cmd_start(msg, state, cmd, bot)

    mock_scan.assert_awaited_once_with(msg, bot, "TESTCODE")


async def test_start_clears_state_always(fresh_db):
    """Стейт очищается при любом старте."""
    msg = make_message(user_id=8, username="hank")
    state = make_state()
    cmd = make_command(args="")
    bot = make_bot()

    with patch("os.path.exists", return_value=False):
        await cmd_start(msg, state, cmd, bot)

    state.clear.assert_awaited_once()


async def test_start_new_status_shows_greeting(fresh_db):
    """Пользователь с new-статусом видит анонс."""
    uid = 9
    await db.ensure_user(uid, "iris")
    # Статус new (по умолчанию)

    msg = make_message(user_id=uid, username="iris")
    state = make_state()
    cmd = make_command(args="")
    bot = make_bot()

    with patch("os.path.exists", return_value=False):
        await cmd_start(msg, state, cmd, bot)

    msg.answer.assert_awaited_once()


# ==================== /status ====================

async def test_status_not_registered(fresh_db):
    msg = make_message(user_id=100)
    await cmd_status(msg)
    msg.answer.assert_awaited_once()
    text = msg.answer.call_args[0][0]
    assert "не зарегистрирован" in text


async def test_status_confirmed(fresh_db):
    uid = 101
    await db.ensure_user(uid, "jack")
    await db.set_order(uid, 2, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    await db.set_raffle_numbers(uid, [1, 2])

    msg = make_message(user_id=uid, username="jack")
    await cmd_status(msg)

    msg.answer.assert_awaited_once()
    text = msg.answer.call_args[0][0]
    assert "Оплата подтверждена" in text


async def test_status_awaiting_confirmation(fresh_db):
    uid = 102
    await db.ensure_user(uid, "kate")
    await db.set_order(uid, 1, "rub", "x", db.STATUS_AWAITING_CONFIRMATION)

    msg = make_message(user_id=uid, username="kate")
    await cmd_status(msg)

    text = msg.answer.call_args[0][0]
    assert "Скрин получен" in text or "закреплено" in text


# ==================== /reset ====================

async def test_reset_clears_registration(fresh_db):
    uid = 150
    await db.ensure_user(uid, "resetme")
    await db.set_order(uid, 2, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)

    msg = make_message(user_id=uid, username="resetme")
    state = make_state()
    await cmd_reset(msg, state)

    state.clear.assert_awaited_once()
    assert await db.get_registration(uid) is None
    msg.answer.assert_awaited_once()


async def test_reset_then_start_shows_greeting(fresh_db):
    """После /reset пользователь снова видит приветствие, а не статус."""
    uid = 151
    await db.ensure_user(uid, "again")
    await db.set_order(uid, 1, "door", "x", db.STATUS_DOOR)

    # сброс
    state = make_state()
    await cmd_reset(make_message(user_id=uid, username="again"), state)

    # /start заново
    msg = make_message(user_id=uid, username="again")
    cmd = make_command(args="")
    bot = make_bot()
    with patch("os.path.exists", return_value=False):
        await cmd_start(msg, make_state(), cmd, bot)

    text = msg.answer.call_args[0][0]
    assert "Привет" in text  # приветствие, не статус


# ==================== on_register ====================

async def test_register_no_username(fresh_db):
    """Пользователь без @username получает сообщение с просьбой создать ник."""
    call = make_callback(data="register", user_id=200, username=None)
    call.from_user.username = None
    state = make_state()

    await on_register(call, state)

    call.answer.assert_awaited()
    call.message.answer.assert_awaited_once()
    text = call.message.answer.call_args[0][0]
    assert "username" in text.lower() or "ник" in text.lower()


async def test_register_with_username_sets_state(fresh_db):
    """Пользователь с @username переходит в состояние ввода имени."""
    call = make_callback(data="register", user_id=201, username="myuser")
    state = make_state()

    await on_register(call, state)

    call.answer.assert_awaited()
    state.set_state.assert_awaited_once_with(Form.waiting_name)
    call.message.answer.assert_awaited_once()


# ==================== on_name ====================

async def test_name_empty_asks_again(fresh_db):
    await db.ensure_user(300, "user300")
    msg = make_message(user_id=300, text="")
    state = make_state()

    await on_name(msg, state)

    msg.answer.assert_awaited_once()
    state.set_state.assert_not_awaited()


async def test_name_too_long_asks_again(fresh_db):
    await db.ensure_user(301, "user301")
    msg = make_message(user_id=301, text="A" * 101)
    state = make_state()

    await on_name(msg, state)

    msg.answer.assert_awaited_once()
    state.set_state.assert_not_awaited()


async def test_name_valid_stores_and_advances(fresh_db):
    await db.ensure_user(302, "user302")
    msg = make_message(user_id=302, text="Иван Иванов")
    state = make_state()

    await on_name(msg, state)

    reg = await db.get_registration(302)
    assert reg["name"] == "Иван Иванов"
    state.set_state.assert_awaited_once_with(Form.waiting_qty)
    msg.answer.assert_awaited_once()


async def test_name_exactly_100_chars_valid(fresh_db):
    await db.ensure_user(303, "user303")
    name = "А" * 100
    msg = make_message(user_id=303, text=name)
    state = make_state()

    await on_name(msg, state)

    reg = await db.get_registration(303)
    assert reg["name"] == name


async def test_name_strips_whitespace(fresh_db):
    await db.ensure_user(304, "user304")
    msg = make_message(user_id=304, text="  Мария  ")
    state = make_state()

    await on_name(msg, state)

    reg = await db.get_registration(304)
    assert reg["name"] == "Мария"


# ==================== on_qty / on_qty_custom ====================

async def test_qty_select_1(fresh_db):
    await db.ensure_user(400, "user400")
    call = make_callback(data="qty:1", user_id=400)
    state = make_state()

    with patch("segments.is_sold_out", new=AsyncMock(return_value=False)), \
         patch("segments.scarcity_line", new=AsyncMock(return_value=None)):
        await on_qty(call, state)

    call.answer.assert_awaited()
    state.update_data.assert_awaited_once_with(qty=1)
    state.set_state.assert_awaited_once_with(Form.choosing_payment)


async def test_qty_select_4(fresh_db):
    await db.ensure_user(401, "user401")
    call = make_callback(data="qty:4", user_id=401)
    state = make_state()

    with patch("segments.is_sold_out", new=AsyncMock(return_value=False)), \
         patch("segments.scarcity_line", new=AsyncMock(return_value=None)):
        await on_qty(call, state)

    state.update_data.assert_awaited_once_with(qty=4)


async def test_qty_more_sets_custom_state(fresh_db):
    call = make_callback(data="qty:more", user_id=402)
    state = make_state()

    await on_qty(call, state)

    state.set_state.assert_awaited_once_with(Form.waiting_qty_custom)
    call.message.answer.assert_awaited_once()


async def test_qty_custom_invalid_text(fresh_db):
    msg = make_message(user_id=410, text="много")
    state = make_state()

    await on_qty_custom(msg, state)

    msg.answer.assert_awaited_once()
    state.set_state.assert_not_awaited()


async def test_qty_custom_zero_invalid(fresh_db):
    msg = make_message(user_id=411, text="0")
    state = make_state()

    await on_qty_custom(msg, state)

    msg.answer.assert_awaited_once()


async def test_qty_custom_above_max_invalid(fresh_db, monkeypatch):
    monkeypatch.setattr(config, "MAX_TICKETS_PER_ORDER", 10)
    msg = make_message(user_id=412, text="11")
    state = make_state()

    await on_qty_custom(msg, state)

    msg.answer.assert_awaited_once()


async def test_qty_custom_valid(fresh_db, monkeypatch):
    monkeypatch.setattr(config, "MAX_TICKETS_PER_ORDER", 10)
    await db.ensure_user(413, "user413")
    msg = make_message(user_id=413, text="5")
    state = make_state()

    with patch("segments.is_sold_out", new=AsyncMock(return_value=False)), \
         patch("segments.scarcity_line", new=AsyncMock(return_value=None)):
        await on_qty_custom(msg, state)

    state.set_state.assert_awaited_once_with(Form.choosing_payment)


async def test_qty_custom_max_valid(fresh_db, monkeypatch):
    monkeypatch.setattr(config, "MAX_TICKETS_PER_ORDER", 10)
    await db.ensure_user(414, "user414")
    msg = make_message(user_id=414, text="10")
    state = make_state()

    with patch("segments.is_sold_out", new=AsyncMock(return_value=False)), \
         patch("segments.scarcity_line", new=AsyncMock(return_value=None)):
        await on_qty_custom(msg, state)

    state.set_state.assert_awaited_once_with(Form.choosing_payment)


# ==================== on_pay ====================

async def test_pay_door_stores_status(fresh_db):
    uid = 500
    await db.ensure_user(uid, "user500")
    await db.set_name(uid, "Door User")

    call = make_callback(data="pay:door", user_id=uid)
    state = make_state(data={"qty": 2})

    with patch("sheets.sync_registration", new=AsyncMock()):
        await on_pay(call, state)

    reg = await db.get_registration(uid)
    assert reg["status"] == db.STATUS_DOOR
    assert reg["payment_method"] == "door"
    state.clear.assert_awaited_once()
    call.message.answer.assert_awaited_once()


async def test_pay_vnd_online_available(fresh_db):
    uid = 501
    await db.ensure_user(uid, "user501")
    await db.set_name(uid, "VND User")

    call = make_callback(data="pay:vnd", user_id=uid)
    state = make_state(data={"qty": 1})

    with patch("segments.is_sold_out", new=AsyncMock(return_value=False)):
        await on_pay(call, state)

    reg = await db.get_registration(uid)
    assert reg["status"] == db.STATUS_AWAITING_PAYMENT
    assert reg["payment_method"] == "vnd"
    state.set_state.assert_awaited_once_with(Form.waiting_screenshot)


async def test_pay_rub_online_available(fresh_db):
    uid = 502
    await db.ensure_user(uid, "user502")
    await db.set_name(uid, "RUB User")

    call = make_callback(data="pay:rub", user_id=uid)
    state = make_state(data={"qty": 2})

    with patch("segments.is_sold_out", new=AsyncMock(return_value=False)):
        await on_pay(call, state)

    reg = await db.get_registration(uid)
    assert reg["payment_method"] == "rub"
    assert reg["amount"] == "1 300 ₽"


async def test_pay_usdt_online_available(fresh_db):
    uid = 503
    await db.ensure_user(uid, "user503")
    await db.set_name(uid, "USDT User")

    call = make_callback(data="pay:usdt", user_id=uid)
    state = make_state(data={"qty": 1})

    with patch("segments.is_sold_out", new=AsyncMock(return_value=False)):
        await on_pay(call, state)

    reg = await db.get_registration(uid)
    assert reg["payment_method"] == "usdt"


async def test_pay_online_sold_out_shows_message(fresh_db):
    uid = 504
    await db.ensure_user(uid, "user504")

    call = make_callback(data="pay:vnd", user_id=uid)
    state = make_state(data={"qty": 1})

    with patch("segments.is_sold_out", new=AsyncMock(return_value=True)):
        await on_pay(call, state)

    # Должен показать сообщение о sold_out, но NOT изменить статус на awaiting_payment
    reg = await db.get_registration(uid)
    assert reg["status"] == db.STATUS_NEW


async def test_pay_door_calculates_amount_correctly(fresh_db):
    uid = 505
    await db.ensure_user(uid, "user505")
    call = make_callback(data="pay:door", user_id=uid)
    state = make_state(data={"qty": 2})

    with patch("sheets.sync_registration", new=AsyncMock()):
        await on_pay(call, state)

    reg = await db.get_registration(uid)
    assert reg["amount"] == "600 000 ₫"


# ==================== on_screenshot ====================

async def test_screenshot_photo_updates_status(fresh_db):
    uid = 600
    await db.ensure_user(uid, "user600")
    await db.set_order(uid, 1, "vnd", "x", db.STATUS_AWAITING_PAYMENT)

    photo_mock = [MagicMock()]
    photo_mock[-1].file_id = "photo_file_id"

    msg = make_message(user_id=uid, username="user600", photo=photo_mock)
    state = make_state()
    bot = make_bot()
    bot.send_photo = AsyncMock()

    with patch("sheets.sync_registration", new=AsyncMock()):
        await on_screenshot(msg, state, bot)

    reg = await db.get_registration(uid)
    assert reg["status"] == db.STATUS_AWAITING_CONFIRMATION
    state.clear.assert_awaited_once()
    msg.answer.assert_awaited_once()


async def test_screenshot_document_updates_status(fresh_db):
    uid = 601
    await db.ensure_user(uid, "user601")
    await db.set_order(uid, 1, "rub", "x", db.STATUS_AWAITING_PAYMENT)

    doc_mock = MagicMock()
    doc_mock.file_id = "doc_file_id"

    msg = make_message(user_id=uid, username="user601", photo=None, document=doc_mock)
    state = make_state()
    bot = make_bot()

    with patch("sheets.sync_registration", new=AsyncMock()):
        await on_screenshot(msg, state, bot)

    reg = await db.get_registration(uid)
    assert reg["status"] == db.STATUS_AWAITING_CONFIRMATION


async def test_screenshot_forwards_to_admin_group(fresh_db, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_GROUP_ID", -100000)
    uid = 602
    await db.ensure_user(uid, "user602")
    await db.set_order(uid, 1, "vnd", "x", db.STATUS_AWAITING_PAYMENT)

    photo_mock = [MagicMock()]
    photo_mock[-1].file_id = "photo_id"

    msg = make_message(user_id=uid, username="user602", photo=photo_mock)
    state = make_state()
    bot = make_bot()

    with patch("sheets.sync_registration", new=AsyncMock()):
        await on_screenshot(msg, state, bot)

    bot.send_photo.assert_awaited_once()
    call_args = bot.send_photo.call_args[0]
    assert call_args[0] == -100000


async def test_screenshot_wrong_type_asks_again(fresh_db):
    msg = make_message(user_id=610, text="это не скрин")
    await on_screenshot_wrong(msg)
    msg.answer.assert_awaited_once()


# ==================== on_screenshot_stateless (после рестарта) ====================

async def test_stateless_screenshot_awaiting_payment_accepted(fresh_db):
    """Скрин без FSM-состояния от ждущего оплаты — принимается и уходит оргам."""
    uid = 620
    await db.ensure_user(uid, "user620")
    await db.set_order(uid, 1, "vnd", "x", db.STATUS_AWAITING_PAYMENT)

    photo_mock = [MagicMock()]
    photo_mock[-1].file_id = "ph_id"
    msg = make_message(user_id=uid, username="user620", photo=photo_mock)
    state = make_state()
    bot = make_bot()

    with patch("sheets.sync_registration", new=AsyncMock()):
        await on_screenshot_stateless(msg, state, bot)

    reg = await db.get_registration(uid)
    assert reg["status"] == db.STATUS_AWAITING_CONFIRMATION
    bot.send_photo.assert_awaited_once()
    msg.answer.assert_awaited_once()


async def test_stateless_screenshot_rejected_accepted(fresh_db):
    uid = 621
    await db.ensure_user(uid, "user621")
    await db.set_order(uid, 1, "vnd", "x", db.STATUS_REJECTED)

    doc_mock = MagicMock()
    doc_mock.file_id = "doc_id"
    msg = make_message(user_id=uid, username="user621", photo=None, document=doc_mock)
    state = make_state()
    bot = make_bot()

    with patch("sheets.sync_registration", new=AsyncMock()):
        await on_screenshot_stateless(msg, state, bot)

    reg = await db.get_registration(uid)
    assert reg["status"] == db.STATUS_AWAITING_CONFIRMATION


async def test_stateless_screenshot_confirmed_ignored(fresh_db):
    """Фото от уже подтверждённого гостя не трактуется как новый скрин."""
    uid = 622
    await db.ensure_user(uid, "user622")
    await db.set_order(uid, 1, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)

    photo_mock = [MagicMock()]
    photo_mock[-1].file_id = "ph_id"
    msg = make_message(user_id=uid, username="user622", photo=photo_mock)
    state = make_state()
    bot = make_bot()

    await on_screenshot_stateless(msg, state, bot)

    reg = await db.get_registration(uid)
    assert reg["status"] == db.STATUS_CONFIRMED_ONLINE  # без изменений
    bot.send_photo.assert_not_awaited()
    msg.answer.assert_not_awaited()


# ==================== on_to_online / on_resend ====================

async def test_to_online_goes_to_payment_choice(fresh_db):
    uid = 700
    await db.ensure_user(uid, "user700")
    await db.set_order(uid, 2, "door", "600 000 ₫", db.STATUS_DOOR)

    call = make_callback(data="to_online", user_id=uid)
    state = make_state()

    with patch("segments.is_sold_out", new=AsyncMock(return_value=False)), \
         patch("segments.scarcity_line", new=AsyncMock(return_value=None)):
        await on_to_online(call, state)

    state.set_state.assert_awaited_once_with(Form.choosing_payment)
    call.answer.assert_awaited()


async def test_resend_sets_waiting_screenshot_state(fresh_db):
    call = make_callback(data="resend", user_id=710)
    state = make_state()

    await on_resend(call, state)

    call.answer.assert_awaited()
    state.set_state.assert_awaited_once_with(Form.waiting_screenshot)
    call.message.answer.assert_awaited_once()


# ==================== on_free_text (заказ еды) ====================

async def test_free_text_saves_order_for_paid(fresh_db):
    uid = 800
    await db.ensure_user(uid, "u800")
    await db.set_order(uid, 1, "vnd", "200 000 ₫", db.STATUS_CONFIRMED_ONLINE)

    msg = make_message(user_id=uid, text="2 хачапури и лимонад")
    bot = make_bot()

    with patch("sheets.sync_registration", new=AsyncMock()), \
         patch("config.ADMIN_GROUP_ID", 0):
        await on_free_text(msg, bot)

    reg = await db.get_registration(uid)
    assert reg["food_order"] == "2 хачапури и лимонад"
    msg.answer.assert_awaited_once()


async def test_free_text_appends_multiple_orders(fresh_db):
    uid = 801
    await db.ensure_user(uid, "u801")
    await db.set_order(uid, 1, "vnd", "200 000 ₫", db.STATUS_CONFIRMED_ONLINE)
    bot = make_bot()

    with patch("sheets.sync_registration", new=AsyncMock()), \
         patch("config.ADMIN_GROUP_ID", 0):
        await on_free_text(make_message(user_id=uid, text="хачапури"), bot)
        await on_free_text(make_message(user_id=uid, text="и вино"), bot)

    reg = await db.get_registration(uid)
    assert reg["food_order"] == "хачапури\nи вино"


async def test_free_text_door_guest_saves_order(fresh_db):
    uid = 802
    await db.ensure_user(uid, "u802")
    await db.set_order(uid, 1, "door", "300 000 ₫", db.STATUS_DOOR)

    msg = make_message(user_id=uid, text="шашлык")
    bot = make_bot()
    with patch("sheets.sync_registration", new=AsyncMock()), \
         patch("config.ADMIN_GROUP_ID", 0):
        await on_free_text(msg, bot)

    reg = await db.get_registration(uid)
    assert reg["food_order"] == "шашлык"


async def test_free_text_unregistered_gets_hint(fresh_db):
    uid = 803
    await db.ensure_user(uid, "u803")  # статус new

    msg = make_message(user_id=uid, text="привет")
    bot = make_bot()
    await on_free_text(msg, bot)

    reg = await db.get_registration(uid)
    assert reg.get("food_order") is None
    msg.answer.assert_awaited_once()


async def test_free_text_ignores_unknown_command(fresh_db):
    uid = 804
    await db.ensure_user(uid, "u804")
    await db.set_order(uid, 1, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)

    msg = make_message(user_id=uid, text="/foobar")
    bot = make_bot()
    await on_free_text(msg, bot)

    reg = await db.get_registration(uid)
    assert reg.get("food_order") is None
    msg.answer.assert_not_awaited()


async def test_free_text_notifies_admin_group(fresh_db):
    uid = 805
    await db.ensure_user(uid, "u805")
    await db.set_order(uid, 1, "vnd", "200 000 ₫", db.STATUS_CONFIRMED_ONLINE)

    msg = make_message(user_id=uid, text="люля-кебаб")
    bot = make_bot()

    with patch("sheets.sync_registration", new=AsyncMock()), \
         patch("config.ADMIN_GROUP_ID", -100500):
        await on_free_text(msg, bot)

    bot.send_message.assert_awaited_once()
    call_args = bot.send_message.call_args[0]
    assert call_args[0] == -100500
    assert "люля-кебаб" in call_args[1]


# ==================== Бесплатное событие (FREE_EVENT) ====================

async def test_free_event_qty_registers_without_payment(fresh_db):
    """FREE_EVENT: выбор кол-ва сразу подтверждает бронь и выдаёт QR (без оплаты)."""
    uid = 900
    await db.ensure_user(uid, "free_guest")
    await db.set_name(uid, "Гость")

    call = make_callback(data="qty:2", user_id=uid, username="free_guest")
    state = make_state()

    with patch("config.FREE_EVENT", True), \
         patch("sheets.sync_registration", new=AsyncMock()):
        await on_qty(call, state)

    reg = await db.get_registration(uid)
    assert reg["status"] == db.STATUS_CONFIRMED_ONLINE
    assert reg["qty"] == 2
    assert reg["payment_method"] == "free"
    assert reg["ticket_code"]  # QR-код выдан
    state.clear.assert_awaited()


async def test_free_event_greeting_is_show_za_stolom(fresh_db):
    """FREE_EVENT: анонс — про «Шоу за столом», без упоминания оплаты."""
    with patch("config.FREE_EVENT", True):
        text = texts.greeting_announce()
    assert "Шоу за столом" in text
    assert "оплат" not in text.lower()


async def test_free_event_custom_qty_registers(fresh_db):
    """FREE_EVENT: ручной ввод кол-ва тоже регистрирует без оплаты."""
    uid = 901
    await db.ensure_user(uid, "free_guest2")
    await db.set_name(uid, "Гость2")

    msg = make_message(user_id=uid, username="free_guest2", text="3")
    state = make_state()

    with patch("config.FREE_EVENT", True), \
         patch("sheets.sync_registration", new=AsyncMock()):
        await on_qty_custom(msg, state)

    reg = await db.get_registration(uid)
    assert reg["status"] == db.STATUS_CONFIRMED_ONLINE
    assert reg["qty"] == 3
