"""Все тексты сообщений (RU). Правь здесь – логика не зависит от формулировок."""
from __future__ import annotations

import config

# ===================== АНОНС / ПРИВЕТСТВИЕ =====================

def greeting_sold_out() -> str:
    links = []
    if config.TG_LINK:
        links.append(f"<a href=\"{config.TG_LINK}\">TG Киндзадза</a>")
    if config.INSTA_LINK:
        links.append(f"<a href=\"{config.INSTA_LINK}\">Инста Киндзадза</a>")
    links_line = (" · ".join(links) + "\n") if links else ""
    return (
        "🎉 Все билеты проданы – спасибо за интерес к концерту «Киндзадза»!\n\n"
        "К сожалению, регистрация закрыта: мест больше нет.\n\n"
        f"📅 {config.EVENT_DATE}, {config.EVENT_TIME} – ждём тех, кто уже с нами!\n"
        f"{links_line}"
        "Следи за анонсами следующих вечеров 🥂"
    )


def greeting_announce() -> str:
    map_line = f"\n🗺 <a href=\"{config.EVENT_MAP_URL}\">Как добраться</a>" if config.EVENT_MAP_URL else ""
    return (
        "Привет! 👋\n\n"
        "Это бот регистрации на <b>стендап-концерт «Киндзадза»</b> –\n"
        "вечер живого юмора в грузинском ресторане в Нячанге.\n\n"
        f"📅 <b>{config.EVENT_DATE}</b>, начало в {config.EVENT_TIME} "
        f"(сбор гостей с {config.DOORS_TIME})\n"
        f"📍 {config.EVENT_LOCATION}{map_line}\n\n"
        "📸 Будет фотограф – красивые кадры с вечера выложим в группу ресторана.\n"
        "🎂 Оплати <b>онлайн</b> – гарантируешь место и участвуешь в розыгрыше десертов.\n\n"
        "👇 Регистрируйся – мест немного!"
    )


# ===================== РЕГИСТРАЦИЯ =====================

RETURNING_HINT = "\n\nХочешь докупить билеты или изменить заказ – кнопка ниже 👇"

RESET_DONE = (
    "Готово – регистрация сброшена 🔄\n"
    "Нажми /start, чтобы начать заново."
)

ASK_NAME = "Как тебя зовут? Напиши имя – оно будет в списке гостей."

NO_USERNAME = (
    "У тебя не задан @username в Telegram – он нужен, чтобы найти тебя в списке.\n"
    "Зайди в настройки Telegram → Имя пользователя, задай ник и нажми /start заново.\n"
    "Или свяжись с организатором, если не получается."
)

ASK_QTY = "На сколько человек берёшь билеты?"

ASK_QTY_CUSTOM = "Напиши количество билетов числом (например, 6):"

QTY_BAD = "Нужно число от 1 до {max}. Попробуй ещё раз:"


def payment_choice(qty: int, scarcity: str | None, sold_out: bool) -> str:
    head = f"🎟 Билетов: <b>{qty}</b>\n\n"
    if not sold_out:
        head += (
            "💳 Оплати <b>онлайн</b> – гарантируешь место и участвуешь в "
            "розыгрыше десертов 🎂.\n"
            "📍 Без онлайн-оплаты место за тобой не закрепляется.\n"
        )
    if scarcity:
        head += f"\n{scarcity}\n"
    if sold_out:
        head += (
            "\n⚠️ Онлайн-места закончились (аншлаг). Осталась только оплата на месте –\n"
            "без гарантии места."
        )
    head += "\n👇 Выбери способ оплаты (цена за 1 билет):"
    return head


def requisites(method: str, qty: int) -> str:
    amount = config.format_amount(method, qty)
    unit = config.format_amount(method, 1)
    per_ticket = f" ({qty} × {unit})" if qty > 1 else ""
    req = config.REQUISITES[method]
    net = f"\nСеть: <b>{config.USDT_NETWORK}</b>" if method == "usdt" else ""
    return (
        f"К оплате: <b>{amount}</b>{per_ticket}\n\n"
        f"Реквизиты:\n<code>{req}</code>{net}\n\n"
        "🎂 Оплата онлайн = гарантия места + участие в розыгрыше десертов.\n\n"
        "После оплаты пришли сюда <b>скрин</b> – место сразу закрепим за тобой."
    )


def screenshot_received() -> str:
    return (
        "Спасибо! Место за тобой <b>закреплено</b> ✅\n\n"
        f"Проверим оплату в течение {config.CONFIRM_SLA} – "
        "после этого пришлём номера розыгрыша и QR-билет.\n\n"
        "Есть вопросы? Напиши организатору – кнопка ниже."
    )


def ask_screenshot_again() -> str:
    return "Жду скрин оплаты 📸 (фото или файл-картинку)."


def door_registered(qty: int) -> str:
    amount = config.format_amount("door", qty)
    unit = config.format_amount("door", 1)
    per_ticket = f" ({qty} × {unit})" if qty > 1 else ""
    return (
        f"📍 Записал! Оплата на месте: {qty} билет(ов), <b>{amount}</b>{per_ticket}.\n\n"
        "Ещё раз напомню, что место не гарантировано. При аншлаге онлайн-гости "
        "заходят первыми и участвуют в розыгрыше десертов.\n\n"
        "💳 Гарантируй место – оплати онлайн 👇"
    )


def confirmed(reg: dict) -> str:
    nums = reg.get("raffle_numbers") or ""
    nums_line = ""
    if nums:
        pretty = ", ".join(f"№{n}" for n in nums.split(","))
        nums_line = f"🎂 Номера розыгрыша десертов: <b>{pretty}</b>\n"
    map_line = f" – <a href=\"{config.EVENT_MAP_URL}\">карта</a>" if config.EVENT_MAP_URL else ""
    links = []
    if config.TG_LINK:
        links.append(f"<a href=\"{config.TG_LINK}\">TG Киндзадза</a>")
    if config.INSTA_LINK:
        links.append(f"<a href=\"{config.INSTA_LINK}\">Инста Киндзадза</a>")
    links_line = (" · ".join(links) + "\n") if links else ""
    return (
        "🎉 Оплата подтверждена – спасибо, ты с нами!\n\n"
        "Благодарим за поддержку 🙏 Ждём тебя с грузинским гостеприимством, "
        "вкусной едой и живым юмором.\n\n"
        f"📅 {config.EVENT_DATE}, начало {config.EVENT_TIME}\n"
        f"📍 {config.EVENT_LOCATION}{map_line}\n"
        f"🎟 Билетов: <b>{reg.get('qty', 1)}</b>\n"
        f"{nums_line}"
        f"🚪 Приходи к {config.DOORS_TIME} – выберешь место и успеешь сделать заказ.\n"
        "📸 На вечере вас встретит профессиональный фотограф.\n"
        f"{links_line}"
        "\n🎫 QR-билет – следующим сообщением. Закрепи его, чтобы потом не искать!\n\n"
        "Ждём тебя – будет душевно и весело 🥂"
    )


def order_updated(reg: dict) -> str:
    """Сообщение при докупке: гость уже был подтверждён, добавил ещё билеты."""
    nums = reg.get("raffle_numbers") or ""
    pretty = ", ".join(f"№{n}" for n in nums.split(",")) if nums else "–"
    return (
        "🎉 Заказ обновлён – спасибо за поддержку!\n\n"
        f"🎟 Теперь у тебя билетов: <b>{reg.get('qty', 1)}</b>\n"
        f"🎂 Номера розыгрыша десертов: <b>{pretty}</b>\n"
        "(прежние номера остаются в силе – добавились новые)\n\n"
        "🎫 Обновлённый QR-билет – следующим сообщением. Он один на всю компанию, "
        f"покажи его на входе. Приходи к {config.DOORS_TIME}.\n\n"
        "Ждём тебя – будет душевно и весело 🥂"
    )


def rejected() -> str:
    return (
        "Оплату подтвердить не удалось 😕\n"
        "Возможно, скрин нечитаемый или сумма не сошлась.\n"
        "Пришли скрин заново или свяжись с организатором – поможем разобраться."
    )


# ===================== /status =====================

def status_view(reg: dict | None) -> str:
    if not reg or reg.get("status") in (None, "new"):
        return "Ты ещё не зарегистрирован. Нажми /start, чтобы начать 👇"
    status = reg["status"]
    qty = reg.get("qty", 1)
    if status == "confirmed_online":
        nums = reg.get("raffle_numbers") or ""
        pretty = ", ".join(f"№{n}" for n in nums.split(",")) if nums else "–"
        return (
            f"✅ Оплата подтверждена. Билетов: <b>{qty}</b>.\n"
            f"🎂 Номера розыгрыша: <b>{pretty}</b>.\n"
            "Ждём тебя 🥂"
        )
    if status == "awaiting_confirmation":
        return (
            f"⏳ Скрин получен, место закреплено. Билетов: <b>{qty}</b>.\n"
            f"Подтвердим в течение {config.CONFIRM_SLA}."
        )
    if status == "awaiting_payment":
        return (
            f"💳 Онлайн-оплата выбрана, {qty} билет(ов). Осталось прислать скрин.\n"
            "Пришли сюда фото чека – закрепим место. Или начни заново: /start"
        )
    if status == "door":
        return (
            f"📍 Ты записан на оплату на месте ({qty} билет(ов)) – место не гарантировано.\n"
            "Хочешь гарантировать? Оплати онлайн: /start"
        )
    if status == "rejected":
        return "❌ Прошлый скрин не подтвердили. Пришли скрин заново через /start."
    if status == "refunded":
        return "↩️ По этому билету оформлен возврат. Хочешь прийти снова – нажми /start."
    return "Нажми /start, чтобы зарегистрироваться."


# ===================== КАРТОЧКА ДЛЯ ОРГОВ =====================

def refund_usage() -> str:
    return (
        "↩️ <b>Возврат билета</b>. Укажи гостя:\n"
        "• <code>/refund 1888561400</code> (user_id)\n"
        "• <code>/refund @username</code>\n\n"
        "Билет аннулируется: место освобождается, QR и номера розыгрыша гасятся. "
        "Строка гостя остаётся со статусом «возврат»."
    )


def refund_not_found(arg: str) -> str:
    return f"Гость <code>{arg}</code> не найден. Проверь user_id или @username."


def refund_done(reg: dict) -> str:
    uname = f"@{reg['username']}" if reg.get("username") else "(нет ника)"
    return (
        "↩️ <b>Возврат оформлен</b>\n"
        f"👤 {reg.get('name', '–')} ({uname})\n"
        f"🆔 <code>{reg['user_id']}</code>\n\n"
        "Место освобождено, QR и номера розыгрыша аннулированы. "
        "Гость помечен как «возврат»."
    )


def admin_card(reg: dict) -> str:
    m = config.PAYMENT_METHODS.get(reg["payment_method"], {})
    uname = f"@{reg['username']}" if reg.get("username") else "(нет ника)"
    return (
        "🧾 <b>Новая оплата на подтверждение</b>\n\n"
        f"👤 {reg.get('name', '–')} ({uname})\n"
        f"💳 Способ: {m.get('label', reg['payment_method'])}\n"
        f"🎟 Билетов: {reg.get('qty', 1)}\n"
        f"💰 Сумма: <b>{reg.get('amount', '–')}</b>\n"
        f"🆔 <code>{reg['user_id']}</code>"
    )


# ===================== QR-БИЛЕТ / CHECK-IN =====================

def ticket_caption(reg: dict) -> str:
    code = reg.get("ticket_code") or ""
    return (
        "🎟 <b>Твой билет</b>\n"
        f"Гостей: <b>{reg.get('qty', 1)}</b>\n\n"
        "Покажи этот QR на входе – организатор отсканирует его.\n"
        f"Код билета: <code>{code}</code>\n\n"
        "🎫 Один QR на всю компанию. Если придёте не все сразу – опоздавшие "
        "покажут этот же QR, и их отметят.\n"
        "Не пересылай его посторонним."
    )


def scan_ticket_not_found() -> str:
    return "❌ Билет не найден. Возможно, код повреждён."


def scan_owner_view(reg: dict) -> str:
    return (
        "Это твой билет ✅\n"
        f"Гостей: <b>{reg.get('qty', 1)}</b>. Покажи QR организатору на входе.\n"
        "Сканирование и отметка доступны только организаторам."
    )


def scan_foreign() -> str:
    return "Это чужой билет. Сканировать и отмечать вход могут только организаторы."


def checkin_card(reg: dict, arrived: int, remaining: int) -> str:
    """Карточка при сканировании: показывает, сколько уже пришло и сколько осталось."""
    uname = f"@{reg['username']}" if reg.get("username") else "(нет ника)"
    qty = reg.get("qty", 1)
    already = f"✅ Уже пришло: <b>{arrived}</b>\n" if arrived else ""
    # Заказ еды показываем-напоминаем только на первом сканировании (arrived == 0)
    food = (reg.get("food_order") or "").strip()
    food_block = ""
    if arrived == 0 and food:
        food_block = (
            "\n🍽 <b>У гостя есть предзаказ еды</b> – он отдельным сообщением ниже.\n"
            "Уточни у гостей, всё ли верно:\n"
            "• всё верно → нажми «🍽 Отправить на кухню» под заказом;\n"
            "• заказ другой → позови официанта для уточнения.\n"
        )
    return (
        "🎫 <b>Билет</b>\n"
        f"👤 {reg.get('name', '–')} ({uname})\n"
        f"🎟 Оплачено мест: <b>{qty}</b>\n"
        f"{already}"
        f"Осталось отметить: <b>{remaining}</b>\n"
        f"{food_block}"
        "\nСколько человек пришло сейчас? Отметь 👇"
    )


def checkin_done_partial(reg: dict) -> str:
    """Отметили часть компании – ждём остальных по тому же QR."""
    arrived = int(reg.get("arrived_count") or 0)
    qty = int(reg.get("qty") or 1)
    return (
        "✅ <b>Отмечено!</b>\n"
        f"👤 {reg.get('name', '–')}\n"
        f"Прошло гостей: <b>{arrived}</b> из {qty}. Осталось: <b>{qty - arrived}</b>.\n\n"
        "Когда подойдут остальные – отсканируй этот же QR ещё раз. 🥂"
    )


def checkin_done_full(reg: dict) -> str:
    """Пришла вся компания – билет закрыт."""
    qty = int(reg.get("qty") or 1)
    return (
        "✅ <b>Все на месте!</b>\n"
        f"👤 {reg.get('name', '–')}\n"
        f"Прошло гостей: <b>{qty}</b> из {qty}. Билет закрыт.\n"
        "Добро пожаловать! 🥂"
    )


def checkin_all_arrived(reg: dict) -> str:
    """Повторный скан, когда уже отмечены все оплаченные места."""
    qty = int(reg.get("qty") or 1)
    return (
        "⚠️ <b>Все оплаченные места уже отмечены</b>\n"
        f"👤 {reg.get('name', '–')}\n"
        f"По этому билету прошло {qty} из {qty}.\n\n"
        "Если пришёл ещё человек – это сверх оплаченного. "
        "Оплата на месте у организатора."
    )


# ===================== НАПОМИНАНИЯ (по сегментам) =====================

def reminder_paid(when: str) -> str:
    map_line = f"\n🗺 <a href=\"{config.EVENT_MAP_URL}\">Карта</a>" if config.EVENT_MAP_URL else ""
    return (
        f"🎤 Привет! {when} ждём тебя на стендапе «Киндзадза».\n\n"
        f"📅 {config.EVENT_DATE}, начало {config.EVENT_TIME} (двери {config.DOORS_TIME})\n"
        f"📍 {config.EVENT_LOCATION}{map_line}\n\n"
        "Будет тепло, весело и вкусно. До встречи 🥂"
    )


def reminder_door(when: str) -> str:
    return (
        f"🎤 {when} – стендап «Киндзадза»! Ты записан на оплату на месте.\n\n"
        f"📅 {config.EVENT_DATE}, начало {config.EVENT_TIME} (двери {config.DOORS_TIME})\n"
        f"📍 {config.EVENT_LOCATION}\n\n"
        "⚠️ Место не гарантировано. Можешь ещё успеть оплатить онлайн –\n"
        "гарантируй место и участвуй в розыгрыше десертов 👉 /start"
    )


def reminder_not_paid(when: str) -> str:
    return (
        f"🎤 {when} – стендап «Киндзадза»!\n"
        "Места ещё есть, но заканчиваются. Оплати онлайн –\n"
        "гарантируй место и участвуй в розыгрыше десертов 🎂 👉 /start"
    )


# ===================== /guests =====================

_GUEST_ICONS = {
    "awaiting_payment": "💳",
    "awaiting_confirmation": "⏳",
    "confirmed_online": "✅",
    "door": "📍",
    "rejected": "❌",
    "refunded": "↩️",
}

_STATUS_SHORT = {
    "awaiting_payment": "не оплатил",
    "awaiting_confirmation": "ждёт подтв.",
    "confirmed_online": "оплатил",
    "door": "на месте",
    "rejected": "отклонён",
    "refunded": "возврат",
}


def guests_list(regs: list[dict]) -> list[str]:
    """Форматирует список гостей. Возвращает страницы ≤4000 символов."""
    if not regs:
        return ["Гостей пока нет."]
    confirmed_qty = sum((r.get("qty") or 0) for r in regs if r["status"] == "confirmed_online")
    confirmed_cnt = sum(1 for r in regs if r["status"] == "confirmed_online")
    header = (
        f"📋 <b>Гости</b> · {confirmed_cnt} чел. оплатили · {confirmed_qty} билетов\n\n"
    )
    lines = []
    for r in regs:
        icon = _GUEST_ICONS.get(r["status"], "❓")
        name = r.get("name") or "–"
        uname = f" @{r['username']}" if r.get("username") else ""
        qty = r.get("qty") or 1
        nums = r.get("raffle_numbers") or ""
        nums_str = f" · №{nums}" if nums else ""
        checkin = " ✔️" if r.get("checked_in_at") else ""
        status_str = _STATUS_SHORT.get(r["status"], r["status"])
        lines.append(f"{icon} {name}{uname} — {qty} бил. · {status_str}{nums_str}{checkin}")
    pages, current = [], header
    for line in lines:
        if len(current) + len(line) + 1 > 4000:
            pages.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current:
        pages.append(current)
    return pages


# ===================== CTA ДЛЯ ПОСТОВ (по сегментам) =====================

def menu_promo() -> str:
    return (
        "🍽 Вот меню вечера!\n\n"
        "Сделай заказ заранее – и к началу концерта всё будет на столе.\n"
        "Вкусная грузинская кухня + живой юмор = идеальный вечер 🥂"
    )


# Просьба прислать заказ (после QR-билета и меню)
ASK_FOOD_ORDER = (
    "🍽 Хочешь поужинать без ожидания?\n"
    "Напиши заказ из меню прямо сюда – одним сообщением. Мы передадим его на кухню "
    "перед концертом, чтобы к твоему приходу всё начали готовить.\n\n"
    "Например: «2 хачапури по-аджарски, люля, грузинский лимонад»"
)


def food_order_saved(order: str) -> str:
    return (
        "Записал ✅ Передадим на кухню перед концертом.\n\n"
        f"🍽 Твой заказ:\n<i>{order}</i>\n\n"
        "Хочешь дополнить – просто напиши ещё сообщение."
    )


def kitchen_order_card(reg: dict) -> str:
    uname = f"@{reg['username']}" if reg.get("username") else "(нет ника)"
    order = reg.get("food_order") or ""
    return (
        "🍽 <b>Заказ еды</b>\n\n"
        f"👤 {reg.get('name', '–')} ({uname})\n"
        f"🎟 Билетов: {reg.get('qty', 1)}\n\n"
        f"📋 Заказ:\n{order}"
    )


def kitchen_not_configured() -> str:
    uname = f"@{config.KITCHEN_USERNAME}" if config.KITCHEN_USERNAME else "кухне"
    return f"Кухня не настроена в боте. Перешли заказ вручную {uname}."


def kitchen_send_failed() -> str:
    uname = f"@{config.KITCHEN_USERNAME}" if config.KITCHEN_USERNAME else "кухне"
    return (
        "Не удалось отправить: кухня ещё не запустила бота. "
        f"Перешли заказ вручную {uname}."
    )


# ===================== РОЗЫГРЫШ ДЕСЕРТОВ =====================

def raffle_winner(reg: dict, winning_number: int) -> str:
    return (
        f"🎉 Поздравляем! Твой номер <b>№{winning_number}</b> выиграл!\n\n"
        "Ты получаешь десерт на сегодняшнем концерте «Киндзадза» 🎂\n"
        "Просто покажи это сообщение официанту – и он принесёт твой десерт.\n\n"
        "Приятного вечера! 🥂"
    )


def raffle_no_win() -> str:
    return (
        "В этот раз удача улыбнулась другим – но ты точно не останешься без сладкого! 😊\n\n"
        "В меню есть потрясающие десерты – например, <b>Лимонное Брюле</b> – просто пушка! 🍋\n"
        "Закажи у официанта – оно того стоит.\n\n"
        "Спасибо, что ты с нами! 🥂"
    )


def raffle_admin_preview(total_guests: int, total_numbers: int, already_done: bool) -> str:
    warn = "\n\n⚠️ Розыгрыш уже проводился! Запустить повторно?" if already_done else ""
    return (
        f"🎰 <b>Розыгрыш десертов</b>{warn}\n\n"
        f"Участников: <b>{total_guests}</b> гостей · <b>{total_numbers}</b> номеров в пуле\n"
        f"(у гостя с 2 билетами – 2 шанса)\n"
        f"Призов: <b>3 десерта</b>\n\n"
        "Нажми кнопку – бот случайно выберет 3 победителей и разошлёт им сообщения:"
    )


def raffle_admin_result(winner_regs: list[tuple[dict, int]], sent_w: int, sent_l: int) -> str:
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🎰 <b>Розыгрыш проведён!</b>\n"]
    for i, (reg, num) in enumerate(winner_regs):
        medal = medals[i] if i < len(medals) else "🏅"
        uname = f" @{reg['username']}" if reg.get("username") else ""
        lines.append(f"{medal} №{num} – {reg.get('name', '–')}{uname}")
    lines.append(f"\n✅ Поздравления отправлены: {sent_w}")
    lines.append(f"😊 Утешительных отправлено: {sent_l}")
    return "\n".join(lines)


def raffle_not_enough() -> str:
    return "Недостаточно участников для розыгрыша (нужно минимум 3 уникальных гостя)."


# ===================== ОБРАТНАЯ СВЯЗЬ =====================

FEEDBACK_REQUEST = (
    "Мы готовы меняться для вас!\n"
    "Пожалуйста, напишите отзыв – текстом, голосовым или даже кружочком. "
    "Мы принимаем любую обратную связь. И нам это очень важно!"
)

FEEDBACK_ACK = "Спасибо за отзыв! 🙏 Мы обязательно его учтём."


def feedback_header(reg: dict) -> str:
    uname = f"@{reg['username']}" if reg.get("username") else "(нет ника)"
    return f"💬 <b>Отзыв от гостя</b>\n👤 {reg.get('name', '–')} ({uname})"


# Подсказка на свободный текст от незарегистрированных/не оплативших
FREE_TEXT_HINT = "Чтобы зарегистрироваться на концерт, нажми /start 👇"


def post_cta(segment: str | None, scarcity: str | None) -> str:
    sc = f"\n{scarcity}" if scarcity else ""
    if segment == "C":  # оплатили онлайн
        return "\n\n–––\n🎤 Скоро увидимся! Если захочешь взять ещё билеты – /start"
    if segment == "B":  # оплата на месте
        return (
            "\n\n–––\n📍 Ты пока на оплате на месте. Гарантируй место онлайн и участвуй "
            f"в розыгрыше десертов 🎂 👉 /start{sc}"
        )
    # сегмент A и все остальные (новые/не оплатившие)
    return (
        "\n\n–––\n👉 Успей зарегистрироваться и оплатить онлайн: гарантируешь место "
        f"и участвуешь в розыгрыше десертов 🎂 /start{sc}"
    )
