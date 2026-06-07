"""Сканирование QR-билетов и отметка прихода (check-in).

Гость показывает QR на входе, организатор сканирует телефоном → открывается deep-link
бота с кодом → бот (если сканирует орг) показывает карточку и спрашивает, сколько пришло.
"""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

import config
import db
import keyboards as kb
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

    if reg.get("checked_in_at"):
        await message.answer(texts.checkin_already(reg))
        return

    await message.answer(
        texts.checkin_card(reg),
        reply_markup=kb.checkin_arrived_kb(code, int(reg.get("qty", 1))),
    )


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

    if reg.get("checked_in_at"):
        await call.answer("Уже отмечен", show_alert=True)
        try:
            await call.message.edit_text(texts.checkin_already(reg), reply_markup=None)
        except Exception:
            pass
        return

    arrived = int(k)
    await db.check_in(reg["user_id"], arrived)
    reg = await db.get_by_ticket_code(code)
    await call.answer("Отмечено ✅")
    try:
        await call.message.edit_text(texts.checkin_done(reg, arrived), reply_markup=None)
    except Exception:
        await call.message.answer(texts.checkin_done(reg, arrived))
