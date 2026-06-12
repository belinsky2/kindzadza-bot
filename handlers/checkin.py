"""Сканирование QR-билетов и отметка прихода (check-in).

Гость показывает QR на входе, организатор сканирует телефоном → открывается deep-link
бота с кодом → бот (если сканирует орг) показывает карточку и спрашивает, сколько пришло.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

import config
import db
import keyboards as kb
import sheets
import texts

log = logging.getLogger(__name__)
router = Router()


async def is_staff(bot: Bot, user_id: int) -> bool:
    """Орг? — по списку ADMIN_IDS или членству в админ-группе."""
    if user_id in config.ADMIN_IDS:
        return True
    if not config.ADMIN_GROUP_ID:
        return False
    try:
        member = await bot.get_chat_member(config.ADMIN_GROUP_ID, user_id)
        return member.status in {"creator", "administrator", "member"}
    except Exception:
        return False


async def process_scan(message: Message, bot: Bot, code: str) -> None:
    """Вызывается из /start, когда параметр = t_<code>."""
    reg = await db.get_by_ticket_code(code)
    if not reg:
        await message.answer(texts.scan_ticket_not_found())
        return

    if not await is_staff(bot, message.from_user.id):
        if reg["user_id"] == message.from_user.id:
            await message.answer(texts.scan_owner_view(reg))
        else:
            await message.answer(texts.scan_foreign())
        return

    qty = int(reg.get("qty") or 1)
    arrived = int(reg.get("arrived_count") or 0)
    if arrived >= qty:
        # все оплаченные места уже отмечены
        await message.answer(texts.checkin_all_arrived(reg))
        return

    remaining = qty - arrived
    await message.answer(
        texts.checkin_card(reg, arrived, remaining),
        reply_markup=kb.checkin_arrived_kb(code, remaining),
    )
    # На первом сканировании отдаём заказ еды отдельным сообщением с кнопкой —
    # билетер отправляет его на кухню, если гости подтвердили заказ.
    if arrived == 0 and (reg.get("food_order") or "").strip():
        await message.answer(
            texts.kitchen_order_card(reg),
            reply_markup=kb.kitchen_send_kb(reg["user_id"]),
        )


@router.callback_query(F.data.startswith("kit:"))
async def on_send_to_kitchen(call: CallbackQuery, bot: Bot) -> None:
    """Билетер нажал «Отправить на кухню» — пересылаем заказ Артуру/в кухонный чат."""
    uid = int(call.data.split(":", 1)[1])
    if not await is_staff(bot, call.from_user.id):
        await call.answer("Отправлять на кухню могут только организаторы", show_alert=True)
        return

    reg = await db.get_registration(uid)
    if not reg or not (reg.get("food_order") or "").strip():
        await call.answer("Заказ не найден", show_alert=True)
        return

    # Куда слать: явный KITCHEN_CHAT_ID или chat_id Артура по нику (если он запускал бота)
    target = config.KITCHEN_CHAT_ID
    if not target and config.KITCHEN_USERNAME:
        krec = await db.get_by_username(config.KITCHEN_USERNAME)
        target = krec["user_id"] if krec else 0
    if not target:
        await call.answer(texts.kitchen_not_configured(), show_alert=True)
        return

    try:
        await bot.send_message(target, texts.kitchen_order_card(reg))
    except Exception:
        log.exception("Не удалось отправить заказ на кухню (target=%s)", target)
        await call.answer(texts.kitchen_send_failed(), show_alert=True)
        return

    await call.answer("Отправлено на кухню ✅")
    try:
        base = call.message.text or call.message.caption or ""
        await call.message.edit_text(f"{base}\n\n✅ Отправлено на кухню", reply_markup=None)
    except Exception:
        pass


@router.callback_query(F.data.startswith("ci:"))
async def on_checkin(call: CallbackQuery, bot: Bot) -> None:
    _, code, k = call.data.split(":", 2)
    if not await is_staff(bot, call.from_user.id):
        await call.answer("Отмечать вход могут только организаторы", show_alert=True)
        return

    reg = await db.get_by_ticket_code(code)
    if not reg:
        await call.answer("Билет не найден", show_alert=True)
        return

    qty = int(reg.get("qty") or 1)
    arrived = int(reg.get("arrived_count") or 0)
    if arrived >= qty:
        await call.answer("Все уже отмечены", show_alert=True)
        try:
            await call.message.edit_text(texts.checkin_all_arrived(reg), reply_markup=None)
        except Exception:
            pass
        return

    new = await db.add_arrival(reg["user_id"], int(k))
    reg = await db.get_by_ticket_code(code)
    asyncio.create_task(sheets.sync_registration(reg))
    await call.answer("Отмечено ✅")
    text = texts.checkin_done_full(reg) if new >= qty else texts.checkin_done_partial(reg)
    try:
        await call.message.edit_text(text, reply_markup=None)
    except Exception:
        await call.message.answer(text)
