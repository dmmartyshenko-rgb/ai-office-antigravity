# Telegram Bridge (netcup)

Постоянный мост к **пользовательской** сессии Telegram (Telethon/MTProto, от лица владельца, не бот). Наружу — только HTTPS-API за Bearer-токеном через Caddy (авто-TLS Let's Encrypt) на `https://v2202609416472518907.goodsrv.de`.

Это полный доступ к Telegram владельца: токен и файлы `.env` / `session.txt` — секреты уровня пароля от аккаунта.

## Установка на сервере (152.53.225.111, Debian 13)

### Проще всего — через веб-консоль netcup (без SSH и ключей)

Панель netcup → SCP → сервер → **Console**, вход `root` по паролю. В консоли две строки:

```bash
curl -fsSL https://raw.githubusercontent.com/dmmartyshenko-rgb/ai-office-antigravity/claude/telegram-bridge-netcup-mtlo1x/telegram-bridge/deploy/bootstrap.sh -o /root/tgb.sh
bash /root/tgb.sh
```

`bootstrap.sh` сам: клонирует репозиторий, ставит сервис (спросит api_hash), проводит вход в Telegram (телефон, код, 2FA), запускает приёмку и печатает `BASE_URL` и `TOKEN`. От человека — только api_hash, код из Telegram и 2FA.

### Или вручную (если уже есть SSH)

```bash
git clone https://github.com/dmmartyshenko-rgb/ai-office-antigravity.git
cd ai-office-antigravity && git checkout claude/telegram-bridge-netcup-mtlo1x
sudo bash telegram-bridge/deploy/install.sh        # спросит api_hash с my.telegram.org, сгенерирует токен
sudo -u tgbridge TG_BRIDGE_ENV=/opt/tg-bridge/.env /opt/tg-bridge/venv/bin/python /opt/tg-bridge/login.py
sudo systemctl restart tg-bridge
sudo bash telegram-bridge/deploy/check_acceptance.sh
```

`login.py` запускается один раз: спрашивает телефон, код из Telegram и пароль 2FA, сохраняет StringSession в `/opt/tg-bridge/session.txt` (chmod 600). Сервис при старте только читает этот файл; если сессия невалидна — `/health` отдаёт `authorized:false`, остальные эндпоинты — 503, сервис не падает.

## Архитектура

- **FastAPI + uvicorn** — слушает только `127.0.0.1:8080`
- **Caddy** — реверс-прокси c авто-TLS на 443; сертификат берётся через 443 (TLS-ALPN-01), порт 80 не нужен
- **systemd** (`tg-bridge.service`) — `Restart=always`, непривилегированный пользователь `tgbridge`, sandbox-хардening
- **ufw** — входящие только 22 и 443 (плюс проверить облачный firewall в панели netcup)
- **Аудит-лог** `/opt/tg-bridge/audit.log` — JSON-строки: время, эндпоинт, peer; тел сообщений нет
- **Rate-limit** на `/send` — 20 запросов/мин (настраивается в `.env`)

## API

Все эндпоинты требуют `Authorization: Bearer <токен>` (сравнение постоянного времени). Без токена — 401.

| Метод | Путь | Параметры | Ответ |
|---|---|---|---|
| GET | `/health` | — | `{status, connected, authorized}` |
| GET | `/dialogs` | `limit` (≤100), `offset` | id, тип (user/group/channel), имя, последнее сообщение (текст/дата/направление/прочитано), непрочитанные |
| GET | `/messages` | `peer`, `limit` (≤100), `offset_id` | id, дата, отправитель, текст, тип, reply_to |
| POST | `/send` | `{peer, text, reply_to?}` | `{id, date}` |
| POST | `/read` | `{peer}` | `{ok:true}` |

`peer` — `me` (Избранное), `@username`, телефон или числовой id.

Ошибки Telegram — понятный JSON, не 500: flood wait → 429 `{"error":"flood_wait","retry_after_seconds":N}`; невалидный peer → 400 `{"error":"invalid_peer"}`; нет прав писать → 403; прочие RPC-ошибки → 502 с кодом и сообщением.

## Примеры

```bash
TOKEN=...   # из /opt/tg-bridge/.env
BASE=https://v2202609416472518907.goodsrv.de

curl -H "Authorization: Bearer $TOKEN" "$BASE/health"
curl -H "Authorization: Bearer $TOKEN" "$BASE/dialogs?limit=5"
curl -H "Authorization: Bearer $TOKEN" "$BASE/messages?peer=me&limit=10"
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"peer":"me","text":"привет"}' "$BASE/send"
```

## Эксплуатация

```bash
systemctl status tg-bridge        # состояние сервиса
journalctl -u tg-bridge -f        # логи
tail -f /opt/tg-bridge/audit.log  # аудит запросов
```

Отзыв доступа: сменить `TG_BRIDGE_TOKEN` в `.env` и перезапустить сервис; полный отзыв — завершить сессию в Telegram (Настройки → Устройства) и удалить `session.txt`.

## Известные грабли на netcup (по итогам первого развёртывания)

- **Права на новые файлы.** Слишком строгий `umask` мешает `apt` прочитать ключ
  репозитория Caddy. Если установка Caddy падает на чтении ключа — проверь права
  на `/usr/share/keyrings/caddy-stable-archive-keyring.gpg` (должен быть читаем).
- **Let's Encrypt на общем `goodsrv.de`.** Хостнейм по умолчанию входит в общий
  домен netcup, у которого недельный лимит сертификатов Let's Encrypt часто
  исчерпан другими клиентами → отказ. Рабочий обход — выпустить сертификат через
  **ZeroSSL** (Caddy умеет: добавить issuer zerossl в блок `tls`).
- **ZeroSSL проверяет только через порт 80.** Приёмка требует, чтобы наружу были
  открыты только 22 и 443. Решение — таймер, который раз в час открывает порт 80
  лишь когда сертификата нет или до конца срока < ~32 дней, и закрывает в
  остальное время. В штатном состоянии открыты только 22 и 443.
- **Повторный запуск `bootstrap.sh` безопасен для Caddy:** установщик больше не
  перезаписывает кастомный `/etc/caddy/Caddyfile` (только стоковый или
  отсутствующий), бэкап — `.bootstrap-bak`.
