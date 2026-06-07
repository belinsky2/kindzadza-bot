#!/usr/bin/env bash
# Перезапуск бота в фоне. Логи пишутся в bot.log
cd "$(dirname "$0")" || exit 1
pkill -f "kindzadza-bot/.venv/bin/python main.py" 2>/dev/null
sleep 1
nohup .venv/bin/python main.py > bot.log 2>&1 &
sleep 3
echo "Бот перезапущен. Последние строки лога:"
tail -n 5 bot.log
