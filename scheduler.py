"""APScheduler: ежедневный пост-DM с персональным CTA и напоминания по сегментам."""
from __future__ import annotations

import logging
import os
from datetime import datetime

from aiogram import Bot
from aiogram.types import FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import broadcast
import config
import db
import segments
import sheets
import texts

# Ключ meta-записи для пересылки отзывов в админ-группу
FEEDBACK_META_KEY = "feedback_active"

log = logging.getLogger(__name__)


# ---------- Ежедневный пост ----------

async def _send_post_to(bot: Bot, uid: int, post: dict, scarcity: str | None) -> None:
    caption = post["caption"] or ""
    fp = post["file_path"]
    if fp:
        photo = FSInputFile(fp) if os.path.exists(fp) else fp  # путь или file_id
        await bot.send_photo(uid, photo, caption=caption)
    else:
        await bot.send_message(uid, caption, disable_web_page_preview=True)


async def publish_next_post(bot: Bot) -> dict | None:
    """Публикует следующий неопубликованный пост всем пользователям. None — если очередь пуста."""
    post = await db.get_next_post()
    if not post:
        log.info("Очередь постов пуста — ежедневная рассылка пропущена.")
        return None
    scarcity = await segments.scarcity_line()
    uids = await db.list_all_user_ids()

    async def send_one(b: Bot, uid: int) -> None:
        await _send_post_to(b, uid, post, scarcity)

    sent, failed = await broadcast.broadcast(bot, uids, send_one)
    await db.mark_post_published(post["id"])
    log.info("Пост #%s разослан: отправлено=%s, ошибок=%s", post["id"], sent, failed)
    return {"post": post, "sent": sent, "failed": failed}


# ---------- Напоминания ----------

async def _send_segment(bot: Bot, segment: str, text: str) -> tuple[int, int]:
    uids = await segments.user_ids_for_segment(segment)

    async def send_one(b: Bot, uid: int) -> None:
        await b.send_message(uid, text, disable_web_page_preview=True)

    return await broadcast.broadcast(bot, uids, send_one)


async def send_reminder(bot: Bot, key: str, when_label: str) -> None:
    if await db.is_broadcast_sent(key):
        log.info("Напоминание %s уже отправлено — пропуск.", key)
        return
    await _send_segment(bot, segments.SEG_PAID, texts.reminder_paid(when_label))
    await _send_segment(bot, segments.SEG_DOOR, texts.reminder_door(when_label))
    await _send_segment(bot, segments.SEG_NOT_PAID, texts.reminder_not_paid(when_label))
    await db.mark_broadcast_sent(key)
    log.info("Напоминание %s отправлено.", key)


def _parse_dt(value: str) -> datetime | None:
    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M")
        return dt.replace(tzinfo=config.TZ)
    except (ValueError, TypeError):
        log.warning("Не удалось разобрать дату напоминания: %r", value)
        return None


async def _periodic_sync() -> None:
    """Полная перезапись Google-таблицы раз в 30 минут (страховочная синхронизация)."""
    regs = await db.get_all_registrations(include_new=True)
    result = await sheets.sync_all(regs)
    if result >= 0:
        log.debug("Авто-синхронизация Google Sheets: %s строк.", result)
    else:
        log.warning("Авто-синхронизация Google Sheets не удалась (Sheets отключены или ошибка).")


async def send_feedback_request(bot: Bot) -> None:
    """Рассылает запрос обратной связи всем оплатившим онлайн и включает пересылку ответов."""
    await db.set_meta(FEEDBACK_META_KEY, "1")
    uids = await db.list_user_ids_by_statuses((db.STATUS_CONFIRMED_ONLINE,))

    async def send_one(b: Bot, uid: int) -> None:
        await b.send_message(uid, texts.FEEDBACK_REQUEST)

    sent, failed = await broadcast.broadcast(bot, uids, send_one)
    log.info("Запрос обратной связи разослан: отправлено=%s, ошибок=%s", sent, failed)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone=config.TZ)

    # периодическая синхронизация с Google Sheets
    sched.add_job(_periodic_sync, "interval", minutes=30, id="sheets_sync")

    # напоминания
    eve = _parse_dt(config.REMINDER_EVE)
    if eve:
        sched.add_job(send_reminder, "date", run_date=eve,
                      args=[bot, "reminder_eve", "завтра"], id="reminder_eve",
                      misfire_grace_time=3600)
    day = _parse_dt(config.REMINDER_DAY)
    if day:
        sched.add_job(send_reminder, "date", run_date=day,
                      args=[bot, "reminder_day", "сегодня"], id="reminder_day",
                      misfire_grace_time=3600)

    sched.start()
    log.info("Планировщик запущен (TZ=%s).", config.TZ_NAME)
    return sched
