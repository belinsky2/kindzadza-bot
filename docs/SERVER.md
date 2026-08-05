# Сервер (Hetzner) — заметки по эксплуатации

Сервер: `root@88.99.39.12`, Ubuntu 24.04. Ориентировочно CX22: **2 vCPU / 4 ГБ RAM / 75 ГБ диск**.
Бот развёрнут в `/opt/kindzadza-bot`, запущен через systemd: `kindzadza-bot.service` (enabled, автозапуск).

## Загрузка (замер 08.07.2026)

| Ресурс | Всего | Ест бот | Свободно |
|---|---|---|---|
| CPU | 2 ядра | ~0% (пики на рассылках) | ~весь |
| RAM | 3.7 ГБ | ~105 МБ | ~3 ГБ |
| Диск | 75 ГБ | ~3 ГБ (весь system) | ~69 ГБ |

Вывод: бот занимает ~3% сервера, запаса на несколько таких же проектов.

## ⚠️ ЧЕК-ЛИСТ ПЕРЕД ЗАЛИВКОЙ НОВОГО ПРОЕКТА НА ЭТОТ СЕРВЕР

1. **Применить обновления + перезагрузить** (на 08.07 висели 9 обновлений и «restart required», аптайм 30 дней). В спокойное время, НЕ перед мероприятием:
   ```bash
   apt update && apt upgrade -y && reboot
   ```
   Бот поднимется сам (systemd enabled). После ребута проверить: `systemctl status kindzadza-bot`.

2. **Добавить swap** (сейчас swap = 0 — подушка от пиков памяти):
   ```bash
   fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
   echo '/swapfile none swap sw 0 0' >> /etc/fstab
   ```

3. **Настроить бэкап бота** (сейчас при потере сервера данные пропадут — важнее «мощностей»):
   - Бэкапить `/opt/kindzadza-bot/bot.db` и `/opt/kindzadza-bot/.env` (в них — регистрации и реквизиты/токены).
   - `credentials.json` (доступ к Google Sheets).

4. **Изоляция проектов**: каждый новый проект — в свой каталог `/opt/<name>`, свой venv, свой systemd-сервис. Не смешивать зависимости с ботом.

5. **Мониторинг** (по желанию): Uptime Kuma (~80 МБ) — алерт, если бот/новый проект упал.

## Полезные команды

```bash
# загрузка сервера и бота
nproc && free -h && df -h / && systemctl status kindzadza-bot --no-pager | head -12

# логи бота
journalctl -u kindzadza-bot -n 100 --no-pager

# перезапуск бота после обновления кода
cd /opt/kindzadza-bot && git pull && systemctl restart kindzadza-bot
```
