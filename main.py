"""Точка входа: инициализация бота, БД, планировщика и запуск polling."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

import config
import db
import scheduler
from handlers import admin, checkin, registration

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("kindzadza-bot")


async def _set_commands(bot: Bot) -> None:
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать / регистрация"),
        BotCommand(command="status", description="Мой статус и номера розыгрыша"),
    ])


async def main() -> None:
    for issue in config.validate():
        log.warning("Конфиг: %s", issue)
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не задан — заполни .env (см. .env.example).")

    await db.init_db()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    # admin-роутер ограничен админ-группой и подключается первым
    dp.include_router(admin.router)
    dp.include_router(checkin.router)
    dp.include_router(registration.router)

    scheduler.setup_scheduler(bot)
    await _set_commands(bot)

    log.info("Бот запущен.")
    try:
        await dp.start_polling(bot)
    finally:
        await db.close_db()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
