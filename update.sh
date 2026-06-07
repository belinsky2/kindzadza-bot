#!/usr/bin/env bash
# Подтянуть изменения из GitHub и перезапустить бота.
# Запускать на Маке после правок, сделанных с телефона.
cd "$(dirname "$0")" || exit 1
echo "→ git pull"
git pull --ff-only || { echo "Конфликт при pull — разберись вручную."; exit 1; }
echo "→ обновляю зависимости"
.venv/bin/pip install -q -r requirements.txt
echo "→ перезапуск"
bash restart.sh
