"""FSM-воронка пользователя: /start → имя → кол-во → оплата → скрин, + /status."""
from __future__ import annotations

import asyncio
import logging
import os
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

import broadcast
import config
import db
import keyboards as kb
import scheduler as sched_mod
import segments
import sheets
import texts
import tickets
from handlers import checkin

log = logging.getLogger(__name__)
router = Router()

# Пользовательская воронка (анонс, регистрация, оплата) работает только в личке
# с ботом. В группах – включая орг-группу – эти хендлеры не срабатывают, чтобы
# не дублировать функционал бота и не плодить мусорные регистрации.
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


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

_SOURCE_RE = re.compile(r"[^a-z0-9_-]+")


def _clean_source(raw: str) -> str:
    """Нормализует метку канала из deep-link: только a-z0-9_-, до 32 символов."""
    return _SOURCE_RE.sub("", raw.lower())[:32]


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

    # deep-link канала привлечения: /start <метка> (например, flyer, insta).
    # Фиксируем при первом касании, чтобы понимать, откуда пришёл гость.
    if arg:
        src = _clean_source(arg)
        if src:
            await db.set_source_if_empty(user.id, src)

    reg = await db.get_registration(user.id)

    # зеркалим вход в Google Таблицу (фоном, не задерживая ответ)
    if reg:
        asyncio.create_task(sheets.sync_registration(reg))

    sold_out = await segments.is_sold_out()
    bot_closed = await db.get_meta("bot_closed") == "1"

    if reg and reg.get("status") in RETURNING_STATUSES:
        hint = texts.RETURNING_HINT if (not sold_out and not config.FREE_EVENT) else ""
        await message.answer(
            texts.status_view(reg) + hint,
            reply_markup=kb.returning_kb(reg["status"], sold_out=sold_out),
            disable_web_page_preview=True,
        )
        return

    # Новый пользователь — бот закрыт
    if bot_closed:
        await message.answer(texts.greeting_closed(), disable_web_page_preview=True)
        return

    # Новый пользователь
    if sold_out:
        await message.answer(texts.greeting_sold_out(), disable_web_page_preview=True)
        return

    # Если админ сохранил пост через /set_announce — показываем его точную копию.
    src_chat = await db.get_meta("announce_src_chat")
    src_msg = await db.get_meta("announce_src_msg")
    if src_chat and src_msg:
        try:
            await bot.copy_message(
                message.chat.id, int(src_chat), int(src_msg),
                reply_markup=kb.register_kb(),
            )
            return
        except Exception:
            log.exception("Не удалось скопировать сохранённый анонс — показываю запасной текст")

    # Запасной вариант: текст из кода + сохранённая/дисковая афиша.
    caption = texts.greeting_announce()
    announce_file_id = await db.get_meta("announce_file_id")
    if announce_file_id:
        photo = announce_file_id
    elif os.path.exists(config.ANNOUNCE_IMAGE):
        photo = FSInputFile(config.ANNOUNCE_IMAGE)
    else:
        photo = None
    await broadcast.send_announce(
        bot, message.chat.id, caption, photo, kb.register_kb()
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
    if await segments.is_sold_out():
        await call.answer("Все билеты проданы – регистрация закрыта 🙏", show_alert=True)
        return
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
    await _after_qty(call.message, state, call.from_user.id, qty)


@router.message(Form.waiting_qty_custom, F.text)
async def on_qty_custom(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if not raw.isdigit() or not (1 <= int(raw) <= config.MAX_TICKETS_PER_ORDER):
        await message.answer(texts.QTY_BAD.format(max=config.MAX_TICKETS_PER_ORDER))
        return
    await _after_qty(message, state, message.from_user.id, int(raw))


async def _after_qty(message: Message, state: FSMContext, user_id: int, qty: int) -> None:
    """После выбора кол-ва: бесплатное событие → сразу бронь, иначе → выбор оплаты."""
    if config.FREE_EVENT:
        await _register_free(message, state, user_id, qty)
    else:
        await _go_to_payment(message, state, user_id, qty)


async def _register_free(message: Message, state: FSMContext, user_id: int, qty: int) -> None:
    """Бесплатная регистрация: бронь места без оплаты + QR-билет."""
    await db.set_order(user_id, qty, "free", "донат", db.STATUS_CONFIRMED_ONLINE)
    reg = await db.get_registration(user_id)
    if not reg.get("ticket_code"):
        await db.set_ticket_code(user_id, tickets.new_code())
        reg = await db.get_registration(user_id)
    await state.clear()
    asyncio.create_task(sheets.sync_registration(reg))
    await message.answer(texts.registered_free(reg), disable_web_page_preview=True)
    if config.BOT_USERNAME and reg.get("ticket_code"):
        qr = tickets.make_qr_png(tickets.ticket_link(reg["ticket_code"]))
        await message.answer_photo(qr, caption=texts.ticket_caption(reg))
    if config.ADMIN_GROUP_ID:
        try:
            await message.bot.send_message(config.ADMIN_GROUP_ID, texts.admin_card_free(reg))
        except Exception:
            log.exception("Не удалось отправить карточку регистрации в админ-группу")


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

# Кнопки способа оплаты работают без привязки к состоянию FSM — чтобы гость
# мог сменить способ (донги ↔ рубли ↔ на месте) старыми кнопками из чата, не
# перезапуская /start. Блокируем только после отправки скрина/подтверждения.
@router.callback_query(F.data.startswith("pay:"))
async def on_pay(call: CallbackQuery, state: FSMContext) -> None:
    user_id = call.from_user.id
    reg = await db.get_registration(user_id)
    if reg and reg.get("status") in (
        db.STATUS_AWAITING_CONFIRMATION, db.STATUS_CONFIRMED_ONLINE,
    ):
        await call.answer(
            "Оплата уже отправлена на проверку. Чтобы изменить – напиши организатору.",
            show_alert=True,
        )
        return
    await call.answer()
    method = call.data.split(":", 1)[1]
    if method not in config.PAYMENT_METHODS:
        return
    data = await state.get_data()
    qty = int(data.get("qty") or (reg.get("qty") if reg else None) or 1)
    amount = config.format_amount(method, qty)

    if method == "door":
        await db.set_order(user_id, qty, "door", amount, db.STATUS_DOOR)
        reg = await db.get_registration(user_id)
        await sheets.sync_registration(reg)
        await state.clear()
        await call.message.answer(texts.door_registered(qty), reply_markup=kb.door_kb())
        if config.ADMIN_GROUP_ID:
            try:
                await call.message.bot.send_message(
                    config.ADMIN_GROUP_ID, texts.admin_card_door(reg)
                )
            except Exception:
                log.exception("Не удалось отправить бронь (на месте) в админ-группу")
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

# Статусы, при которых присланное фото/документ трактуется как скрин оплаты
SCREENSHOT_STATUSES = (db.STATUS_AWAITING_PAYMENT, db.STATUS_REJECTED)


async def _accept_screenshot(message: Message, state: FSMContext, bot: Bot) -> None:
    """Принимает скрин оплаты: бронь места + карточка оргам. Не зависит от FSM."""
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


@router.message(Form.waiting_screenshot, F.photo | F.document)
async def on_screenshot(message: Message, state: FSMContext, bot: Bot) -> None:
    await _accept_screenshot(message, state, bot)


@router.message(Form.waiting_screenshot)
async def on_screenshot_wrong(message: Message) -> None:
    await message.answer(texts.ask_screenshot_again())


@router.message(StateFilter(None), F.chat.type == "private", F.photo | F.document)
async def on_screenshot_stateless(message: Message, state: FSMContext, bot: Bot) -> None:
    """Скрин, присланный вне FSM (например, после перезапуска бота).

    Опираемся на статус в базе, а не на состояние в памяти — поэтому рестарты
    бота больше не «теряют» присланные скрины оплаты.
    """
    reg = await db.get_registration(message.from_user.id)
    if reg and reg.get("status") in SCREENSHOT_STATUSES:
        await _accept_screenshot(message, state, bot)


# ---------- Свободные сообщения вне воронки ----------

# Статусы, при которых текстовое сообщение трактуется как заказ еды
ORDER_STATUSES = (db.STATUS_CONFIRMED_ONLINE, db.STATUS_DOOR)


async def _try_forward_feedback(message: Message, bot: Bot) -> bool:
    """Если сбор обратной связи активен — пересылает сообщение в админ-группу.

    Работает только для подтверждённых онлайн-гостей.
    Возвращает True, если сообщение было обработано как отзыв.
    """
    if not config.ADMIN_GROUP_ID:
        return False
    if await db.get_meta(sched_mod.FEEDBACK_META_KEY) != "1":
        return False
    reg = await db.get_registration(message.from_user.id)
    if not reg or reg.get("status") != db.STATUS_CONFIRMED_ONLINE:
        return False
    try:
        await bot.send_message(config.ADMIN_GROUP_ID, texts.feedback_header(reg))
        await bot.forward_message(config.ADMIN_GROUP_ID, message.chat.id, message.message_id)
    except Exception:
        log.exception("Не удалось переслать отзыв в админ-группу")
    await message.answer(texts.FEEDBACK_ACK)
    return True


@router.message(StateFilter(None), F.chat.type == "private", F.voice | F.video_note)
async def on_feedback_media(message: Message, bot: Bot) -> None:
    """Голосовые и кружочки от гостей — только как отзывы."""
    await _try_forward_feedback(message, bot)


@router.message(StateFilter(None), F.chat.type == "private", F.text)
async def on_free_text(message: Message, bot: Bot) -> None:
    """Любое сообщение от гостя вне воронки. Для оплативших – это заказ еды или отзыв."""
    text = message.text.strip()
    if text.startswith("/"):
        return  # неизвестная команда — игнорируем
    reg = await db.get_registration(message.from_user.id)
    if not reg or reg.get("status") not in ORDER_STATUSES:
        await message.answer(texts.FREE_TEXT_HINT)
        return
    # Если идёт сбор обратной связи — текст трактуем как отзыв, не как заказ еды
    if await _try_forward_feedback(message, bot):
        return
    order = await db.append_food_order(message.from_user.id, text)
    reg = await db.get_registration(message.from_user.id)
    asyncio.create_task(sheets.sync_registration(reg))
    await message.answer(texts.food_order_saved(order))
    if config.ADMIN_GROUP_ID:
        try:
            await bot.send_message(config.ADMIN_GROUP_ID, texts.kitchen_order_card(reg))
        except Exception:
            log.exception("Не удалось отправить заказ еды в админ-группу")
