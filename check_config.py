"""Проверка .env перед запуском: запусти `python check_config.py`.

Показывает, что заполнено, что нет, и какие файлы-картинки на месте.
Секреты (токен, кошелёк) маскируются. Ничего не отправляет и не меняет.
"""
from __future__ import annotations

import os

import config

OK = "✅"
WARN = "⚠️ "
BAD = "❌"


def _mask(value: str, keep: int = 4) -> str:
    if not value:
        return "(пусто)"
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}…{value[-keep:]}"


def main() -> None:
    print("=" * 50)
    print("ПРОВЕРКА КОНФИГА KINDZADZA-BOT")
    print("=" * 50)

    if not os.path.exists(".env"):
        print(f"{BAD} Файл .env не найден! Скопируй .env.example → .env и заполни.")
        return

    errors = 0
    warns = 0

    # --- Обязательное ---
    print("\n[ ОБЯЗАТЕЛЬНОЕ ]")
    checks = [
        ("BOT_TOKEN", config.BOT_TOKEN, _mask(config.BOT_TOKEN), True),
        ("BOT_USERNAME", config.BOT_USERNAME, config.BOT_USERNAME, True),
        ("ADMIN_GROUP_ID", config.ADMIN_GROUP_ID, str(config.ADMIN_GROUP_ID), True),
        ("EVENT_LOCATION", config.EVENT_LOCATION, config.EVENT_LOCATION, True),
        ("REQUISITES_VND", config.REQUISITES["vnd"], config.REQUISITES["vnd"], True),
        ("REQUISITES_RUB", config.REQUISITES["rub"], config.REQUISITES["rub"], True),
        ("REQUISITES_USDT", config.REQUISITES["usdt"], _mask(config.REQUISITES["usdt"], 6), True),
    ]
    for name, raw, shown, required in checks:
        filled = bool(raw) and "уточня" not in str(raw)
        mark = OK if filled else BAD
        if not filled:
            errors += 1
        print(f"  {mark} {name}: {shown}")

    # --- Желательное ---
    print("\n[ ЖЕЛАТЕЛЬНОЕ ]")
    soft = [
        ("ADMIN_IDS", config.ADMIN_IDS, str(config.ADMIN_IDS or "(пусто)")),
        ("ORGANIZER_USERNAME", config.ORGANIZER_USERNAME, config.ORGANIZER_USERNAME or "(пусто)"),
        ("SPREADSHEET_ID", config.SPREADSHEET_ID, _mask(config.SPREADSHEET_ID)),
        ("TG_LINK", config.TG_LINK, config.TG_LINK or "(пусто)"),
        ("INSTA_LINK", config.INSTA_LINK, config.INSTA_LINK or "(пусто)"),
        ("EVENT_MAP_URL", config.EVENT_MAP_URL, config.EVENT_MAP_URL or "(пусто)"),
    ]
    for name, raw, shown in soft:
        mark = OK if raw else WARN
        if not raw:
            warns += 1
        print(f"  {mark} {name}: {shown}")

    # --- Параметры события ---
    print("\n[ СОБЫТИЕ ]")
    print(f"  • Дата/время: {config.EVENT_DATE}, {config.EVENT_TIME} (двери {config.DOORS_TIME})")
    print(f"  • Таймзона: {config.TZ_NAME}")
    print(f"  • Вместимость: {config.EVENT_CAPACITY}")
    print(f"  • Цена за билет: "
          f"{config.format_amount('vnd')} / {config.format_amount('rub')} / "
          f"{config.format_amount('usdt')} / на месте {config.format_amount('door')}")
    print(f"  • Ежедневный пост в: {config.DAILY_POST_TIME}")
    print(f"  • Напоминания: {config.REMINDER_EVE} | {config.REMINDER_DAY}")

    # --- Картинки ---
    print("\n[ КАРТИНКИ ]")
    images = [
        ("Анонс (/start)", config.ANNOUNCE_IMAGE, False),
        ("Меню (после QR)", config.MENU_IMAGE, False),
        ("QR оплаты VND", config.PAYMENT_QR_VND, False),
    ]
    for label, path, required in images:
        exists = os.path.exists(path)
        mark = OK if exists else WARN
        note = "" if exists else "  ← нет файла (бот просто не покажет картинку)"
        if not exists:
            warns += 1
        print(f"  {mark} {label}: {path}{note}")

    # --- Итог ---
    print("\n" + "=" * 50)
    if errors:
        print(f"{BAD} ОШИБОК: {errors} — без них бот не будет работать корректно.")
    else:
        print(f"{OK} Все обязательные поля заполнены.")
    if warns:
        print(f"{WARN} Предупреждений: {warns} (необязательно, но желательно).")
    print("=" * 50)


if __name__ == "__main__":
    main()
