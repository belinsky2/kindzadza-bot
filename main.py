"""Точка входа: инициализация бота, БД, планировщика и запуск polling."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeChat

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
    # Команды для всех пользователей (личка с ботом)
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать / регистрация"),
        BotCommand(command="status", description="Мой статус и номера розыгрыша"),
        BotCommand(command="reset", description="Сбросить регистрацию и начать заново"),
    ])

    # Команды только для админ-группы (всплывают при наборе «/»)
    if config.ADMIN_GROUP_ID:
        await bot.set_my_commands(
            [
                BotCommand(command="help", description="Список всех команд"),
                BotCommand(command="stats", description="Статистика по регистрациям"),
                BotCommand(command="guests", description="Список всех гостей"),
                BotCommand(command="announce", description="Разослать анонс всем"),
                BotCommand(command="set_announce", description="Запомнить афишу (ответом на фото)"),
                BotCommand(command="broadcast", description="Рассылка по сегментам"),
                BotCommand(command="addpost", description="Добавить пост в очередь"),
                BotCommand(command="post_now", description="Опубликовать следующий пост"),
                BotCommand(command="close", description="Закрыть бота для новых гостей"),
                BotCommand(command="open", description="Открыть бота снова"),
                BotCommand(command="soldout", description="Солд-аут (off — выключить)"),
                BotCommand(command="reset_event", description="Сброс под новое мероприятие"),
                BotCommand(command="refund", description="Вернуть билет (user_id/@username)"),
                BotCommand(command="raffle", description="Провести розыгрыш"),
                BotCommand(command="feedback", description="Запросить обратную связь"),
                BotCommand(command="feedback_off", description="Остановить сбор отзывов"),
                BotCommand(command="sync_sheets", description="Выгрузить в Google Таблицу"),
            ],
            scope=BotCommandScopeChat(chat_id=config.ADMIN_GROUP_ID),
        )


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
