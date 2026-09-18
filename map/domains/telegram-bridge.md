# telegram-bridge — мост к пользовательской сессии Telegram на netcup

## Статус
Код готов, ждёт развёртывания на сервере владельцем. Обновлено: 2026-09-18.

## Ветка
`claude/telegram-bridge-netcup-mtlo1x`.

## Цель
Постоянный сервис на netcup (152.53.225.111, Debian 13): держит пользовательскую
сессию Telegram (Telethon/MTProto, не бот) и отдаёт защищённый HTTPS-API
(`https://v2202609416472518907.goodsrv.de`), через который внешний ассистент
читает и шлёт сообщения от лица владельца.

## Артефакты
- `telegram-bridge/app/` — FastAPI-сервис (Bearer-токен, rate-limit на /send,
  аудит-лог без тел сообщений, ошибки Telegram как понятный JSON).
- `telegram-bridge/login.py` — одноразовый интерактивный вход (код + 2FA),
  сохраняет StringSession chmod 600.
- `telegram-bridge/deploy/install.sh` — установщик: пользователь tgbridge, venv,
  systemd (Restart=always), Caddy c авто-TLS, ufw 22/80/443.
- `telegram-bridge/deploy/check_acceptance.sh` — приёмочные проверки.
- `telegram-bridge/README.md` — инструкция и API.

## Следующий шаг
Владелец на сервере: клонировать ветку → `install.sh` (спросит api_hash с
my.telegram.org) → `login.py` → `check_acceptance.sh`. Проверить облачный
firewall в панели netcup (только 22/80/443).

## Риски / открытые вопросы
- Токен API = полный доступ к Telegram владельца; хранить как пароль.
- Из облачной сессии Claude SSH на сервер недоступен — деплой только руками
  владельца или из окружения с SSH-доступом.
