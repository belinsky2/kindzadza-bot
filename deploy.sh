#!/usr/bin/env bash
#
# Автоматическая установка бота на сервер Ubuntu.
# Запускать ОТ root в папке /opt/kindzadza-bot:
#   bash deploy.sh
#
# Скрипт ставит зависимости, создаёт виртуальное окружение,
# проверяет конфиг и регистрирует systemd-сервис.
# Безопасно запускать повторно (например, после обновления кода).

set -e  # выходить при первой же ошибке

APP_DIR="/opt/kindzadza-bot"
SERVICE="kindzadza-bot"

echo "=================================================="
echo "  УСТАНОВКА KINDZADZA-BOT"
echo "=================================================="

cd "$APP_DIR"

# 1. Системные пакеты
echo ""
echo "[1/6] Устанавливаю системные пакеты..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git

# 2. Виртуальное окружение
echo "[2/6] Создаю виртуальное окружение..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

# 3. Зависимости Python
echo "[3/6] Устанавливаю зависимости Python..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

# 4. Проверка .env
echo "[4/6] Проверяю конфигурацию..."
if [ ! -f ".env" ]; then
    echo ""
    echo "  ❌ Файл .env не найден!"
    echo "     Выполни: cp .env.example .env && nano .env"
    echo "     Заполни значения и запусти deploy.sh снова."
    exit 1
fi
.venv/bin/python check_config.py || true

# 5. systemd-сервис
echo ""
echo "[5/6] Регистрирую сервис автозапуска..."
cp "$APP_DIR/${SERVICE}.service" "/etc/systemd/system/${SERVICE}.service"
systemctl daemon-reload
systemctl enable "$SERVICE"

# 6. Запуск / перезапуск
echo "[6/6] Запускаю бота..."
systemctl restart "$SERVICE"
sleep 2

echo ""
echo "=================================================="
systemctl --no-pager status "$SERVICE" | head -n 6 || true
echo "=================================================="
echo ""
echo "  ✅ Готово! Бот запущен и будет стартовать сам после перезагрузки."
echo ""
echo "  Полезные команды:"
echo "    journalctl -u $SERVICE -f      # смотреть логи в реальном времени"
echo "    systemctl restart $SERVICE     # перезапустить"
echo "    systemctl stop $SERVICE        # остановить"
echo "    systemctl status $SERVICE      # статус"
echo ""
