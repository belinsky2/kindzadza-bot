"""Inline-клавиатуры."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
import db


def _contact_button() -> InlineKeyboardButton | None:
    if not config.ORGANIZER_USERNAME:
        return None
    return InlineKeyboardButton(
        text="💬 Связаться с организатором",
        url=f"https://t.me/{config.ORGANIZER_USERNAME}",
    )


def register_kb(sold_out: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if not sold_out:
        kb.button(text="✍️ Зарегистрироваться", callback_data="register")
    contact = _contact_button()
    if contact:
        kb.row(contact)
    kb.adjust(1)
    return kb.as_markup()


def returning_kb(status: str, sold_out: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if not sold_out:
        if status == db.STATUS_AWAITING_PAYMENT:
            kb.button(text="💳 Завершить оплату", callback_data="register")
        elif status == db.STATUS_REJECTED:
            kb.button(text="📸 Прислать скрин заново", callback_data="register")
        elif status == db.STATUS_DOOR:
            kb.button(text="💳 Оплатить онлайн", callback_data="register")
        elif status == db.STATUS_CONFIRMED_ONLINE:
            kb.button(text="🎟 Купить ещё билеты", callback_data="register")
    contact = _contact_button()
    if contact:
        kb.row(contact)
    kb.adjust(1)
    return kb.as_markup()


def qty_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for n in (1, 2, 3, 4):
        kb.button(text=str(n), callback_data=f"qty:{n}")
    kb.button(text="5+", callback_data="qty:more")
    kb.adjust(5)
    return kb.as_markup()


def payment_kb(sold_out: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if not sold_out:
        for key in config.ONLINE_METHODS:
            m = config.PAYMENT_METHODS[key]
            label = f"{m['label']}  ·  {config.format_amount(key, 1)}"
            kb.button(text=label, callback_data=f"pay:{key}")
    door = config.PAYMENT_METHODS["door"]
    kb.button(
        text=f"{door['label']}  ·  {config.format_amount('door', 1)}",
        callback_data="pay:door",
    )
    contact = _contact_button()
    if contact:
        kb.row(contact)
    kb.adjust(1)
    return kb.as_markup()


def waiting_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    contact = _contact_button()
    if contact:
        kb.row(contact)
    return kb.as_markup()


def rejected_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📸 Прислать скрин заново", callback_data="resend")
    contact = _contact_button()
    if contact:
        kb.row(contact)
    kb.adjust(1)
    return kb.as_markup()


def door_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Оплатить онлайн и гарантировать место", callback_data="to_online")
    contact = _contact_button()
    if contact:
        kb.row(contact)
    kb.adjust(1)
    return kb.as_markup()


def admin_confirm_kb(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data=f"adm:confirm:{user_id}")
    kb.button(text="❌ Отклонить", callback_data=f"adm:reject:{user_id}")
    kb.adjust(2)
    return kb.as_markup()


def checkin_arrived_kb(code: str, remaining: int) -> InlineKeyboardMarkup:
    """Кнопки 'сколько пришло сейчас': 1..remaining (до 10).

    remaining – сколько ещё осталось отметить (qty минус уже пришедшие).
    """
    kb = InlineKeyboardBuilder()
    n = min(remaining, 10)
    if n == 1:
        kb.button(text="✅ Пришёл (1)", callback_data=f"ci:{code}:1")
    else:
        for k in range(1, n + 1):
            kb.button(text=str(k), callback_data=f"ci:{code}:{k}")
    kb.adjust(5)
    return kb.as_markup()


def raffle_confirm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎰 Запустить розыгрыш!", callback_data="raffle:run")
    kb.button(text="Отмена", callback_data="raffle:cancel")
    kb.adjust(1)
    return kb.as_markup()


def kitchen_send_kb(user_id: int) -> InlineKeyboardMarkup:
    """Кнопка билетера: отправить заказ еды на кухню."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🍽 Отправить на кухню", callback_data=f"kit:{user_id}")
    kb.adjust(1)
    return kb.as_markup()


def broadcast_segment_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Купили онлайн", callback_data="bc:paid")
    kb.button(text="❌ Не купили", callback_data="bc:unpaid")
    kb.button(text="Все", callback_data="bc:all")
    kb.button(text="Отмена", callback_data="bc:cancel")
    kb.adjust(2, 2)
    return kb.as_markup()
