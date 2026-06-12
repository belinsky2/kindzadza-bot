"""Админ-хендлеры: подтверждение/отклонение оплат, статистика, посты, рассылки.

Все команды и кнопки работают только в админ-группе (ADMIN_GROUP_ID).
"""
from __future__ import annotations

import logging
import os

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, Message

import config
import db
import keyboards as kb
import scheduler
import segments
import sheets
import texts
import tickets

log = logging.getLogger(__name__)
router = Router()

# Все апдейты в этом роутере — только из админ-группы
router.message.filter(F.chat.id == config.ADMIN_GROUP_ID)
router.callback_query.filter(F.message.chat.id == config.ADMIN_GROUP_ID)

# Временное хранилище контента для /broadcast: {admin_user_id: payload}
_pending_broadcast: dict[int, dict] = {}


# ---------- Подтверждение / отклонение ----------

@router.callback_query(F.data.startswith("adm:"))
async def on_admin_decision(call: CallbackQuery, bot: Bot) -> None:
    _, action, uid_str = call.data.split(":", 2)
    user_id = int(uid_str)
    reg = await db.get_registration(user_id)
    if not reg:
        await call.answer("Запись не найдена", show_alert=True)
        return

    actor = call.from_user.username or call.from_user.full_name

    if action == "confirm":
        if reg["status"] == db.STATUS_CONFIRMED_ONLINE:
            await call.answer("Уже подтверждено")
            return
        qty = int(reg.get("qty", 1))
        numbers = await db.assign_raffle_numbers(qty)
        await db.set_raffle_numbers(user_id, numbers)
        # уникальный код билета (генерим один раз)
        if not reg.get("ticket_code"):
            await db.set_ticket_code(user_id, tickets.new_code())
        await db.update_status(user_id, db.STATUS_CONFIRMED_ONLINE)
        reg = await db.get_registration(user_id)
        await sheets.sync_registration(reg)
        try:
            await bot.send_message(user_id, texts.confirmed(reg), disable_web_page_preview=True)
            # QR-билет отдельным сообщением
            if config.BOT_USERNAME and reg.get("ticket_code"):
                qr = tickets.make_qr_png(tickets.ticket_link(reg["ticket_code"]))
                await bot.send_photo(user_id, qr, caption=texts.ticket_caption(reg))
            if os.path.exists(config.MENU_IMAGE):
                await bot.send_photo(
                    user_id,
                    FSInputFile(config.MENU_IMAGE),
                    caption=texts.menu_promo(),
                )
            await bot.send_message(user_id, texts.ASK_FOOD_ORDER)
        except Exception:
            log.exception("Не удалось уведомить пользователя %s о подтверждении", user_id)
        await _mark_card(call, f"✅ Подтвердил {actor} · номера: "
                               f"{reg.get('raffle_numbers')}")
        await call.answer("Подтверждено ✅")

    elif action == "reject":
        await db.update_status(user_id, db.STATUS_REJECTED)
        reg = await db.get_registration(user_id)
        await sheets.sync_registration(reg)
        try:
            await bot.send_message(user_id, texts.rejected(), reply_markup=kb.rejected_kb())
        except Exception:
            log.exception("Не удалось уведомить пользователя %s об отклонении", user_id)
        await _mark_card(call, f"❌ Отклонил {actor}")
        await call.answer("Отклонено ❌")


async def _mark_card(call: CallbackQuery, note: str) -> None:
    """Дописывает результат в карточку оргов и убирает кнопки."""
    try:
        base = call.message.caption or call.message.text or ""
        new = f"{base}\n\n{note}"
        if call.message.caption is not None:
            await call.message.edit_caption(caption=new, reply_markup=None)
        else:
            await call.message.edit_text(new, reply_markup=None)
    except Exception:
        log.debug("Не удалось обновить карточку (необязательно).")


# ---------- /guests ----------

@router.message(Command("guests"))
async def cmd_guests(message: Message) -> None:
    regs = await db.get_all_registrations()
    for page in texts.guests_list(regs):
        await message.answer(page)


# ---------- /sync_sheets ----------

@router.message(Command("sync_sheets"))
async def cmd_sync_sheets(message: Message) -> None:
    if not config.SPREADSHEET_ID:
        await message.answer(
            "Google Таблица не подключена: задай SPREADSHEET_ID в .env и перезапусти бота."
        )
        return
    await message.answer("Синхронизирую всех гостей в таблицу…")
    regs = await db.get_all_registrations(include_new=True)
    n = await sheets.sync_all(regs)
    if n < 0:
        await message.answer(
            "Не удалось записать в таблицу. Проверь credentials.json и доступ "
            "сервисного аккаунта к таблице."
        )
    else:
        await message.answer(f"Готово – в таблице {n} строк (включая «просто зашли»).")


# ---------- /stats ----------

@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    taken = await db.seats_taken()
    left = config.EVENT_CAPACITY - taken
    by_status = await db.count_by_status()
    ci_orders, ci_guests = await db.checkin_totals()

    lines = [
        "📊 <b>Статистика</b>",
        f"Мест занято (онлайн + бронь): <b>{taken}</b> / {config.EVENT_CAPACITY}",
        f"Свободно: <b>{left}</b>",
        f"На входе отмечено: <b>{ci_guests}</b> гостей ({ci_orders} билетов)",
        "",
        "<b>По статусам</b> (записей · билетов):",
    ]
    labels = {
        db.STATUS_NEW: "зашли",
        db.STATUS_AWAITING_PAYMENT: "не оплатили",
        db.STATUS_AWAITING_CONFIRMATION: "ждут подтверждения",
        db.STATUS_CONFIRMED_ONLINE: "оплатили онлайн",
        db.STATUS_DOOR: "оплата на месте",
        db.STATUS_REJECTED: "отклонены",
    }
    for status, label in labels.items():
        d = by_status.get(status, {"count": 0, "qty": 0})
        lines.append(f"• {label}: {d['count']} · {d['qty']}")

    # оценка выручки по подтверждённым онлайн
    rev = await db.breakdown_by_method(db.STATUS_CONFIRMED_ONLINE)
    if rev:
        lines.append("")
        lines.append("<b>Выручка (подтверждённые онлайн):</b>")
        for method, qty in rev:
            if method:
                lines.append(f"• {config.format_amount(method, qty)} ({qty} билетов)")

    await message.answer("\n".join(lines))


# ---------- Посты ----------

@router.message(Command("post_now"))
async def cmd_post_now(message: Message, bot: Bot) -> None:
    result = await scheduler.publish_next_post(bot)
    if not result:
        await message.answer("Очередь постов пуста. Добавь пост через /addpost.")
        return
    await message.answer(
        f"Пост #{result['post']['id']} разослан: "
        f"отправлено {result['sent']}, ошибок {result['failed']}."
    )


@router.message(Command("addpost"))
async def cmd_addpost(message: Message) -> None:
    args = message.text.split(maxsplit=1)
    text_arg = args[1].strip() if len(args) > 1 else ""
    reply = message.reply_to_message

    if reply and reply.photo:
        file_id = reply.photo[-1].file_id
        caption = text_arg or reply.caption or ""
        post_id = await db.add_post(file_id, caption)
        kind = "фото + текст"
    elif text_arg:
        post_id = await db.add_post(None, text_arg)
        kind = "текст"
    elif reply and reply.text:
        post_id = await db.add_post(None, reply.text)
        kind = "текст (из ответа)"
    else:
        await message.answer(
            "Как добавить пост:\n"
            "• ответом на фото: <code>/addpost</code> (подпись возьму из фото) "
            "или <code>/addpost текст</code>\n"
            "• текстом: <code>/addpost текст поста</code>"
        )
        return

    left = await db.count_unpublished_posts()
    await message.answer(f"Пост #{post_id} добавлен ({kind}). В очереди: {left}.")


# ---------- /broadcast (по сегментам) ----------

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message) -> None:
    args = message.text.split(maxsplit=1)
    text_arg = args[1].strip() if len(args) > 1 else ""
    reply = message.reply_to_message

    payload: dict | None = None
    if reply and reply.photo:
        payload = {"type": "photo", "file_id": reply.photo[-1].file_id,
                   "caption": text_arg or reply.caption or ""}
    elif text_arg:
        payload = {"type": "text", "text": text_arg}
    elif reply and reply.text:
        payload = {"type": "text", "text": reply.text}

    if not payload:
        await message.answer(
            "Что разослать? Варианты:\n"
            "• <code>/broadcast текст</code>\n"
            "• ответом на сообщение/фото: <code>/broadcast</code>"
        )
        return

    _pending_broadcast[message.from_user.id] = payload
    await message.answer("Кому разослать?", reply_markup=kb.broadcast_segment_kb())


@router.callback_query(F.data.startswith("bc:"))
async def on_broadcast_segment(call: CallbackQuery, bot: Bot) -> None:
    seg = call.data.split(":", 1)[1]
    if seg == "cancel":
        _pending_broadcast.pop(call.from_user.id, None)
        await call.answer("Отменено")
        await call.message.edit_reply_markup(reply_markup=None)
        return

    payload = _pending_broadcast.pop(call.from_user.id, None)
    if not payload:
        await call.answer("Нет текста для рассылки — начни заново с /broadcast", show_alert=True)
        return

    await call.answer("Рассылаю…")
    if seg == "all":
        uids = await db.list_all_user_ids()
    elif seg == "paid":
        uids = await segments.user_ids_paid()
    elif seg == "unpaid":
        uids = await segments.user_ids_not_paid()
    else:
        uids = await segments.user_ids_for_segment(seg)

    import broadcast as bc_mod

    async def send_one(b: Bot, uid: int) -> None:
        if payload["type"] == "photo":
            await b.send_photo(uid, payload["file_id"], caption=payload.get("caption", ""))
        else:
            await b.send_message(uid, payload["text"], disable_web_page_preview=True)

    sent, failed = await bc_mod.broadcast(bot, uids, send_one)
    await call.message.edit_reply_markup(reply_markup=None)
    seg_label = {"paid": "купили онлайн", "unpaid": "не купили", "all": "все"}.get(seg, seg)
    await call.message.answer(
        f"Рассылка завершена ({seg_label}): отправлено {sent}, ошибок {failed}."
    )
