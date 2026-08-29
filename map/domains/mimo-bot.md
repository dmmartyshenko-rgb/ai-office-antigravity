# mimo-bot — MiMo Code CLI + Telegram-бот

## Статус
Пауза (задеплоен, активной разработки нет). Обновлено: 2026-08-29.

## Ветка
`claude/xiaomi-code-install-9uxwre`.

## Цель
Два бесплатных инструмента: инструкция/скрипт установки Xiaomi MiMo Code CLI и
AI-кодер в Telegram на базе MiMo (через OpenRouter), задеплоенный на Vercel.

## Артефакты
- `api/webhook.py` — обработчик Telegram-webhook (serverless-функция Vercel).
- `install_mimo_code.sh`, `setup.sh` — установка CLI.
- `vercel.json`, `requirements.txt`, `pyproject.toml` — конфигурация деплоя.
- `.github/workflows/deploy.yml` (на `main`) — ручной деплой на Vercel:
  синхронизирует секреты `OPENROUTER_API_KEY` и `TELEGRAM_BOT_TOKEN`,
  деплоит, ставит Telegram-webhook. Деплоит именно эту ветку.

## Следующий шаг
Проверить, жив ли бот (webhook отвечает), прежде чем что-либо менять.

## Риски / открытые вопросы
- Workflow на `main` жёстко привязан к этой ветке и к project id Vercel —
  при переносе кода ветку в workflow надо менять.
- Зависимость от бесплатности MiMo на OpenRouter.
