"""FSM-воронка пользователя: /start → имя → кол-во → оплата → скрин, + /status."""
from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

import config
import db
import keyboards as kb
import segments
import sheets
import texts
from handlers import checkin

log = logging.getLogger(__name__)
router = Router()


class Form(StatesGroup):
    waiting_name = State()
    waiting_qty = State()
    waiting_qty_custom = State()
    choosing_payment = State()
    waiting_screenshot = State()


# Статусы, при которых /start показывает «вернувшегося», а не анонс заново
RETURNING_STATUSES = (
    db.STATUS_AWAITING_PAYMENT,
    db.STATUS_AWAITING_CONFIRMATION,
    db.STATUS_CONFIRMED_ONLINE,
    db.STATUS_DOOR,
    db.STATUS_REJECTED,
)


# ---------- /start ----------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject, bot: Bot) -> None:
    await state.clear()
    user = message.from_user
    await db.ensure_user(user.id, user.username)

    # deep-link сканирования QR-билета: /start t_<code>
    arg = (command.args or "").strip()
    if arg.startswith("t_"):
        await checkin.process_scan(message, bot, arg[2:])
        return

    reg = await db.get_registration(user.id)

    # зеркалим вход в Google Таблицу (фоном, не задерживая ответ)
    if reg:
        asyncio.create_task(sheets.sync_registration(reg))

    if reg and reg.get("status") in RETURNING_STATUSES:
        await message.answer(
            texts.status_view(reg) + texts.RETURNING_HINT,
            reply_markup=kb.returning_kb(reg["status"]),
            disable_web_page_preview=True,
        )
        return

    # Новый пользователь: анонс с афишей (если есть)
    if os.path.exists(config.ANNOUNCE_IMAGE):
        await message.answer_photo(
            FSInputFile(config.ANNOUNCE_IMAGE),
            caption=texts.greeting_announce(),
            reply_markup=kb.register_kb(),
        )
    else:
        await message.answer(
            texts.greeting_announce(),
            reply_markup=kb.register_kb(),
            disable_web_page_preview=True,
        )


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    reg = await db.get_registration(message.from_user.id)
    await message.answer(texts.status_view(reg), disable_web_page_preview=True)


@router.message(Command("reset"))
async def cmd_reset(message: Message, state: FSMContext) -> None:
    """Сброс регистрации: удаляет запись и состояние, /start начнётся заново."""
    await state.clear()
    await db.delete_registration(message.from_user.id)
    await message.answer(texts.RESET_DONE)


# ---------- Регистрация: имя ----------

@router.callback_query(F.data == "register")
async def on_register(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    if not call.from_user.username:
        await call.message.answer(texts.NO_USERNAME)
        return
    await db.ensure_user(call.from_user.id, call.from_user.username)
    await state.set_state(Form.waiting_name)
    await call.message.answer(texts.ASK_NAME)


@router.message(Form.waiting_name, F.text)
async def on_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name or len(name) > 100:
        await message.answer("Напиши, пожалуйста, имя текстом (до 100 символов):")
        return
    await db.set_name(message.from_user.id, name)
    await state.set_state(Form.waiting_qty)
    await message.answer(texts.ASK_QTY, reply_markup=kb.qty_kb())


# ---------- Кол-во билетов ----------

@router.callback_query(Form.waiting_qty, F.data.startswith("qty:"))
async def on_qty(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    value = call.data.split(":", 1)[1]
    if value == "more":
        await state.set_state(Form.waiting_qty_custom)
        await call.message.answer(texts.ASK_QTY_CUSTOM)
        return
    qty = int(value)
    await _go_to_payment(call.message, state, call.from_user.id, qty)


@router.message(Form.waiting_qty_custom, F.text)
async def on_qty_custom(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if not raw.isdigit() or not (1 <= int(raw) <= config.MAX_TICKETS_PER_ORDER):
        await message.answer(texts.QTY_BAD.format(max=config.MAX_TICKETS_PER_ORDER))
        return
    await _go_to_payment(message, state, message.from_user.id, int(raw))


async def _go_to_payment(message: Message, state: FSMContext, user_id: int, qty: int) -> None:
    await state.update_data(qty=qty)
    await state.set_state(Form.choosing_payment)
    sold_out = await segments.is_sold_out()
    scarcity = await segments.scarcity_line()
    await message.answer(
        texts.payment_choice(qty, scarcity, sold_out),
        reply_markup=kb.payment_kb(sold_out),
    )


# ---------- Выбор способа оплаты ----------

@router.callback_query(Form.choosing_payment, F.data.startswith("pay:"))
async def on_pay(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    method = call.data.split(":", 1)[1]
    data = await state.get_data()
    qty = int(data.get("qty", 1))
    user_id = call.from_user.id
    amount = config.format_amount(method, qty)

    if method == "door":
        await db.set_order(user_id, qty, "door", amount, db.STATUS_DOOR)
        reg = await db.get_registration(user_id)
        await sheets.sync_registration(reg)
        await state.clear()
        await call.message.answer(texts.door_registered(qty), reply_markup=kb.door_kb())
        return

    # онлайн-способ: проверяем места ещё раз (на случай гонки)
    if await segments.is_sold_out():
        sold_out = True
        await call.message.answer(
            texts.payment_choice(qty, None, sold_out), reply_markup=kb.payment_kb(sold_out)
        )
        return

    await db.set_order(user_id, qty, method, amount, db.STATUS_AWAITING_PAYMENT)
    await state.set_state(Form.waiting_screenshot)
    await call.message.answer(texts.requisites(method, qty), reply_markup=kb.waiting_kb())
    qr_path = config.PAYMENT_QR_IMAGE.get(method)
    if qr_path and os.path.exists(qr_path):
        await call.message.answer_photo(FSInputFile(qr_path))


@router.callback_query(F.data == "to_online")
async def on_to_online(call: CallbackQuery, state: FSMContext) -> None:
    """Из 'оплата на месте' → переключение на онлайн."""
    await call.answer()
    reg = await db.get_registration(call.from_user.id)
    qty = int(reg.get("qty", 1)) if reg else 1
    await _go_to_payment(call.message, state, call.from_user.id, qty)


@router.callback_query(F.data == "resend")
async def on_resend(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(Form.waiting_screenshot)
    await call.message.answer(texts.ask_screenshot_again())


# ---------- Скрин оплаты ----------

@router.message(Form.waiting_screenshot, F.photo | F.document)
async def on_screenshot(message: Message, state: FSMContext, bot: Bot) -> None:
    user_id = message.from_user.id
    # бронируем место
    await db.update_status(user_id, db.STATUS_AWAITING_CONFIRMATION)
    reg = await db.get_registration(user_id)
    await sheets.sync_registration(reg)

    # пересылаем скрин оргам с карточкой и кнопками
    card = texts.admin_card(reg)
    markup = kb.admin_confirm_kb(user_id)
    try:
        if message.photo:
            await bot.send_photo(
                config.ADMIN_GROUP_ID, message.photo[-1].file_id,
                caption=card, reply_markup=markup,
            )
        else:
            await bot.send_document(
                config.ADMIN_GROUP_ID, message.document.file_id,
                caption=card, reply_markup=markup,
            )
    except Exception:
        log.exception("Не удалось отправить скрин в админ-группу (ADMIN_GROUP_ID=%s)",
                      config.ADMIN_GROUP_ID)

    await state.clear()
    await message.answer(texts.screenshot_received(), reply_markup=kb.waiting_kb())


@router.message(Form.waiting_screenshot)
async def on_screenshot_wrong(message: Message) -> None:
    await message.answer(texts.ask_screenshot_again())
