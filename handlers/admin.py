"""Админ-хендлеры: подтверждение/отклонение оплат, статистика, посты, рассылки.

Все команды и кнопки работают только в админ-группе (ADMIN_GROUP_ID).
"""
from __future__ import annotations

import logging
import os
import random

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
from scheduler import FEEDBACK_META_KEY

log = logging.getLogger(__name__)
router = Router()

# Все апдейты в этом роутере — только из админ-группы
router.message.filter(F.chat.id == config.ADMIN_GROUP_ID)
router.callback_query.filter(F.message.chat.id == config.ADMIN_GROUP_ID)

# Временное хранилище контента для /broadcast: {admin_user_id: payload}
_pending_broadcast: dict[int, dict] = {}

# Временное хранилище афиши для /announce: {admin_user_id: {"file_id": ...}}
_pending_announce: dict[int, dict] = {}


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
        # Уже выданные номера розыгрыша (если гость докупает) — их сохраняем.
        # Их количество = число ранее подтверждённых билетов.
        existing = [n for n in (reg.get("raffle_numbers") or "").split(",") if n.strip()]
        is_repeat = bool(existing)
        new_qty = int(reg.get("qty", 1))
        # новые номера — по одному на каждый докупленный билет
        new_numbers = await db.assign_raffle_numbers(new_qty)
        all_numbers = [int(n) for n in existing] + new_numbers
        await db.set_raffle_numbers(user_id, all_numbers)
        # общее число билетов = старые + докупленные (= число всех номеров)
        await db.set_qty(user_id, len(all_numbers))
        # уникальный код билета (генерим один раз; тот же QR пускает всю компанию)
        if not reg.get("ticket_code"):
            await db.set_ticket_code(user_id, tickets.new_code())
        await db.update_status(user_id, db.STATUS_CONFIRMED_ONLINE)
        reg = await db.get_registration(user_id)
        await sheets.sync_registration(reg)
        try:
            text = texts.order_updated(reg) if is_repeat else texts.confirmed(reg)
            await bot.send_message(user_id, text, disable_web_page_preview=True)
            # QR-билет отдельным сообщением (обновлённый — на всё количество)
            if config.BOT_USERNAME and reg.get("ticket_code"):
                qr = tickets.make_qr_png(tickets.ticket_link(reg["ticket_code"]))
                await bot.send_photo(user_id, qr, caption=texts.ticket_caption(reg))
            # меню и просьбу о заказе шлём только при первом подтверждении
            if not is_repeat:
                if os.path.exists(config.MENU_IMAGE):
                    await bot.send_photo(
                        user_id,
                        FSInputFile(config.MENU_IMAGE),
                        caption=texts.menu_promo(),
                    )
                await bot.send_message(user_id, texts.ASK_FOOD_ORDER)
        except Exception:
            log.exception("Не удалось уведомить пользователя %s о подтверждении", user_id)
        note = "✅ Подтвердил (докупка)" if is_repeat else "✅ Подтвердил"
        await _mark_card(call, f"{note} {actor} · номера: {reg.get('raffle_numbers')}")
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


# ---------- /help ----------

@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Список всех команд админ-группы с описанием."""
    await message.answer(texts.admin_help(), disable_web_page_preview=True)


# ---------- /feedback ----------

@router.message(Command("feedback"))
async def cmd_feedback(message: Message, bot: Bot) -> None:
    """Немедленно разослать запрос обратной связи и включить пересылку ответов."""
    await scheduler.send_feedback_request(bot)
    await message.answer(
        "✅ Запрос обратной связи разослан всем оплатившим.\n"
        "Ответы гостей (текст, голосовые, кружочки) будут пересылаться сюда.\n\n"
        "Остановить: <code>/feedback_off</code>"
    )


@router.message(Command("feedback_off"))
async def cmd_feedback_off(message: Message) -> None:
    """Выключить пересылку отзывов."""
    await db.set_meta(FEEDBACK_META_KEY, "0")
    await message.answer("❌ Сбор обратной связи остановлен.")


# ---------- /raffle ----------

RAFFLE_WINNERS = 3


@router.message(Command("raffle"))
async def cmd_raffle(message: Message) -> None:
    pool = await db.get_raffle_pool()
    unique_guests = len({uid for uid, _ in pool})
    already_done = await db.get_meta("raffle_done") == "1"
    if unique_guests < RAFFLE_WINNERS:
        await message.answer(texts.raffle_not_enough())
        return
    await message.answer(
        texts.raffle_admin_preview(unique_guests, len(pool), already_done),
        reply_markup=kb.raffle_confirm_kb(),
    )


@router.callback_query(F.data.startswith("raffle:"))
async def on_raffle(call: CallbackQuery, bot: Bot) -> None:
    action = call.data.split(":", 1)[1]
    if action == "cancel":
        await call.answer("Отменено")
        await call.message.edit_reply_markup(reply_markup=None)
        return

    pool = await db.get_raffle_pool()
    unique_uids = {uid for uid, _ in pool}
    if len(unique_uids) < RAFFLE_WINNERS:
        await call.answer(texts.raffle_not_enough(), show_alert=True)
        return

    # Честный розыгрыш: тянем из пула номеров, max 1 выигрыш на гостя
    shuffled = pool.copy()
    random.shuffle(shuffled)
    winners: list[tuple[int, int]] = []  # [(user_id, number)]
    winner_ids: set[int] = set()
    for uid, number in shuffled:
        if uid not in winner_ids:
            winners.append((uid, number))
            winner_ids.add(uid)
        if len(winners) == RAFFLE_WINNERS:
            break

    # Рассылаем поздравления победителям
    sent_w = 0
    for uid, num in winners:
        reg = await db.get_registration(uid)
        try:
            await bot.send_message(uid, texts.raffle_winner(reg, num))
            sent_w += 1
        except Exception:
            log.exception("Не удалось отправить поздравление пользователю %s", uid)

    # Утешительное — всем остальным оплатившим
    all_uids = await db.list_user_ids_by_statuses((db.STATUS_CONFIRMED_ONLINE,))
    sent_l = 0
    for uid in all_uids:
        if uid not in winner_ids:
            try:
                await bot.send_message(uid, texts.raffle_no_win())
                sent_l += 1
            except Exception:
                log.exception("Не удалось отправить утешительное пользователю %s", uid)

    await db.set_meta("raffle_done", "1")

    winner_regs = [(await db.get_registration(uid), num) for uid, num in winners]
    result = texts.raffle_admin_result(winner_regs, sent_w, sent_l)
    await call.answer("Готово ✅")
    try:
        await call.message.edit_text(result, reply_markup=None)
    except Exception:
        await call.message.answer(result)


# ---------- /soldout ----------

@router.message(Command("soldout"))
async def cmd_soldout(message: Message) -> None:
    """Открыть/закрыть продажи: /soldout → закрыть, /soldout off → открыть."""
    args = message.text.split()
    turn_off = len(args) > 1 and args[1].strip().lower() == "off"
    if turn_off:
        await db.set_meta("sold_out_override", "0")
        await message.answer("✅ Продажи открыты – бот снова принимает регистрации.")
    else:
        await db.set_meta("sold_out_override", "1")
        taken = await db.seats_taken()
        await message.answer(
            f"🚫 Продажи закрыты – режим солд-аута включён.\n"
            f"Занято мест: {taken}.\n\n"
            "Новые гости увидят «Все билеты проданы».\n"
            "Вернуть приём: <code>/soldout off</code>"
        )


# ---------- /close / /open ----------

@router.message(Command("close"))
async def cmd_close(message: Message) -> None:
    """Закрыть бота для новых пользователей – они увидят «скоро вернёмся»."""
    await db.set_meta("bot_closed", "1")
    await message.answer(
        "🔒 Бот закрыт для новых пользователей.\n"
        "Они видят: «Мы скоро вернёмся».\n\n"
        "Открыть снова: <code>/open</code>"
    )


@router.message(Command("open"))
async def cmd_open(message: Message) -> None:
    """Открыть бота для новых пользователей."""
    await db.set_meta("bot_closed", "0")
    await message.answer("✅ Бот открыт – новые пользователи снова видят анонс.")


# ---------- /refund ----------

@router.message(Command("refund"))
async def cmd_refund(message: Message) -> None:
    """Возврат билета: /refund <user_id> или /refund @username."""
    args = message.text.split()
    if len(args) < 2:
        await message.answer(texts.refund_usage())
        return

    arg = args[1].strip()
    if arg.startswith("@"):
        reg = await db.get_by_username(arg[1:])
    elif arg.lstrip("-").isdigit():
        reg = await db.get_registration(int(arg))
    else:
        reg = None

    if not reg:
        await message.answer(texts.refund_not_found(arg))
        return

    await db.refund(reg["user_id"])
    reg = await db.get_registration(reg["user_id"])
    # Полная пересборка таблицы — гость уходит с листа «Оплатившие».
    regs = await db.get_all_registrations(include_new=True)
    await sheets.sync_all(regs)
    await message.answer(texts.refund_done(reg))


# ---------- /set_announce (запомнить афишу) ----------

@router.message(Command("set_announce"))
async def cmd_set_announce(message: Message) -> None:
    """Запомнить картинку-афишу: ответь этой командой на фото."""
    reply = message.reply_to_message
    if not (reply and reply.photo):
        await message.answer(
            "📷 Пришли фото-афишу в группу и <b>ответь</b> на неё командой "
            "<code>/set_announce</code> – я запомню её для анонса.\n\n"
            "Проверить: /start в личке боту. Разослать всем: /announce"
        )
        return
    file_id = reply.photo[-1].file_id
    await db.set_meta("announce_file_id", file_id)
    await message.answer(
        "✅ Афиша сохранена.\n"
        "Проверь её: открой бота в личке и нажми /start.\n"
        "Разослать всем: /announce"
    )


# ---------- /announce (рассылка анонса всем) ----------

@router.message(Command("announce"))
async def cmd_announce(message: Message) -> None:
    """Разослать анонс (фото + текст + кнопка регистрации) всем пользователям.

    Фото берётся из сообщения, на которое ответили; иначе — сохранённая афиша
    (/set_announce). Текст – из texts.announce_broadcast().
    """
    reply = message.reply_to_message
    if reply and reply.photo:
        file_id = reply.photo[-1].file_id
    else:
        file_id = await db.get_meta("announce_file_id")
    _pending_announce[message.from_user.id] = {"file_id": file_id or ""}

    total = len(await db.list_all_user_ids())
    note = "" if file_id else (
        "\n\n⚠️ Фото не найдено – уйдёт только текст.\n"
        "Ответь этой командой на фото в группе или задай афишу через /set_announce."
    )
    await message.answer(
        texts.announce_admin_preview(total) + note,
        reply_markup=kb.announce_confirm_kb(),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("ann:"))
async def on_announce(call: CallbackQuery, bot: Bot) -> None:
    action = call.data.split(":", 1)[1]
    if action == "cancel":
        _pending_announce.pop(call.from_user.id, None)
        await call.answer("Отменено")
        await call.message.edit_reply_markup(reply_markup=None)
        return

    payload = _pending_announce.pop(call.from_user.id, None) or {}
    file_id = payload.get("file_id") or await db.get_meta("announce_file_id")
    await call.answer("Рассылаю…")

    if action == "paid":
        uids = await segments.user_ids_paid()
    elif action == "unpaid":
        uids = await segments.user_ids_not_paid()
    else:  # all
        uids = await db.list_all_user_ids()

    text = texts.announce_broadcast()

    async def send_one(b: Bot, uid: int) -> None:
        if file_id:
            await b.send_photo(uid, file_id, caption=text, reply_markup=kb.register_kb())
        else:
            await b.send_message(
                uid, text, reply_markup=kb.register_kb(), disable_web_page_preview=True
            )

    import broadcast as bc_mod
    sent, failed = await bc_mod.broadcast(bot, uids, send_one)
    await call.message.edit_reply_markup(reply_markup=None)
    seg_label = {
        "paid": "забронировали" if config.FREE_EVENT else "купили онлайн",
        "unpaid": "не забронировали" if config.FREE_EVENT else "не купили",
        "all": "все",
    }.get(action, action)
    await call.message.answer(
        f"📣 Анонс разослан ({seg_label}): отправлено {sent}, ошибок {failed}."
    )


# ---------- /reset_event (сброс под новое мероприятие) ----------

@router.message(Command("reset_event"))
async def cmd_reset_event(message: Message) -> None:
    """Сброс всех регистраций под новое мероприятие (пользователи сохраняются)."""
    total = len(await db.list_all_user_ids())
    await message.answer(
        texts.reset_event_preview(total),
        reply_markup=kb.reset_event_confirm_kb(),
    )


@router.callback_query(F.data.startswith("rev:"))
async def on_reset_event(call: CallbackQuery) -> None:
    action = call.data.split(":", 1)[1]
    if action == "cancel":
        await call.answer("Отменено")
        await call.message.edit_reply_markup(reply_markup=None)
        return

    n = await db.reset_all_registrations()
    # сбрасываем операционные флаги прошлого события
    for key in ("sold_out_override", "raffle_done", FEEDBACK_META_KEY, "bot_closed"):
        await db.set_meta(key, "0")
    # перезаписываем Google-таблицу под чистый лист
    regs = await db.get_all_registrations(include_new=True)
    await sheets.sync_all(regs)
    await call.answer("Готово ✅")
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(texts.reset_event_done(n))


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
    by_status = await db.count_by_status()
    ci_orders, ci_guests = await db.checkin_totals()
    reg = by_status.get(db.STATUS_CONFIRMED_ONLINE, {"count": 0, "qty": 0})
    new = by_status.get(db.STATUS_NEW, {"count": 0, "qty": 0})

    if config.FREE_EVENT:
        lines = [
            "📊 <b>Статистика</b> · Шоу за столом",
            f"✅ Зарегистрировано: <b>{reg['count']}</b> чел. · <b>{reg['qty']}</b> мест",
            f"🚪 На входе отмечено: <b>{ci_guests}</b> гостей ({ci_orders} брони)",
            f"👀 Просто зашли в бота: {new['count']}",
        ]
        await message.answer("\n".join(lines))
        return

    taken = await db.seats_taken()
    left = config.EVENT_CAPACITY - taken
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
        db.STATUS_REFUNDED: "возвраты",
    }
    for status, label in labels.items():
        d = by_status.get(status, {"count": 0, "qty": 0})
        lines.append(f"• {label}: {d['count']} · {d['qty']}")

    # оценка выручки по подтверждённым онлайн
    rev = await db.breakdown_by_method(db.STATUS_CONFIRMED_ONLINE)
    rev_lines = [
        f"• {config.format_amount(m, q)} ({q} билетов)"
        for m, q in rev if m and m in config.PAYMENT_METHODS
    ]
    if rev_lines:
        lines.append("")
        lines.append("<b>Выручка (подтверждённые онлайн):</b>")
        lines.extend(rev_lines)

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
