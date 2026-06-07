"""Сегменты пользователей и расчёт мест."""
from __future__ import annotations

import config
import db

# Сегменты для персонального CTA / напоминаний / ручных рассылок
SEG_NOT_PAID = "A"   # начали, но не оплатили онлайн (дожим)
SEG_DOOR = "B"       # оплата на месте (нудж на онлайн)
SEG_PAID = "C"       # оплатили онлайн (только "дойти")

SEGMENT_STATUSES = {
    SEG_NOT_PAID: (db.STATUS_AWAITING_PAYMENT, db.STATUS_REJECTED),
    SEG_DOOR: (db.STATUS_DOOR,),
    SEG_PAID: (db.STATUS_CONFIRMED_ONLINE,),
}

SEGMENT_TITLES = {
    SEG_NOT_PAID: "Не оплатили",
    SEG_DOOR: "Оплата на месте",
    SEG_PAID: "Оплатили онлайн",
}


def segment_of(status: str) -> str | None:
    for seg, statuses in SEGMENT_STATUSES.items():
        if status in statuses:
            return seg
    return None


async def user_ids_for_segment(segment: str) -> list[int]:
    return await db.list_user_ids_by_statuses(SEGMENT_STATUSES[segment])


async def seats_left() -> int:
    return config.EVENT_CAPACITY - await db.seats_taken()


async def is_sold_out() -> bool:
    return await seats_left() <= 0


async def scarcity_line() -> str | None:
    """Строка 'осталось N мест' — только при реальном дефиците."""
    left = await seats_left()
    if 0 < left <= config.SEATS_REVEAL_THRESHOLD:
        return f"🔥 Осталось всего {left} мест!"
    return None
