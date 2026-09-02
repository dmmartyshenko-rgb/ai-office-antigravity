# Hermes Megamap

## Статус
Актив. Обновлено: 2026-08-30.

## Где лежит
Репозиторий `ai-office-antigravity`, каталог `hermes-megamap/` (самодостаточен,
переносим в отдельный репозиторий без правок — корень ищется по `.hermes/`).

## Цель
Система внешней памяти: три слоя, метаболический пайплайн, CLI и линтер

## Артефакты
- `CLAUDE.md` — поведенческий контракт агента Hermes.
- `.hermes/scripts/hermes_cli.py` — CLI: init / add-raw / consolidate / decay / status / lint / ui / bot.
- `.hermes/scripts/metabolism.py` — пайплайн Triage → Consolidate → Decay & Audit.
- `.hermes/scripts/hermes_ui.py` — веб-дашборд «Экспедиционная карта» (127.0.0.1:8137).
- `.hermes/scripts/telegram_bot.py` — приёмная в Telegram: голос/текст → буфер.
- `.hermes/scripts/lint_megamap.py` — жёсткая валидация инвариантов (код 0 = зелёный).
- `.hermes/scripts/test_scenario.py` — воспроизводимый тест в temp-каталоге.
- `.hermes/config.json` — пороги decay, gravity, TTL буфера.

## Следующий шаг
создать бота у BotFather, вписать chat_id в config.json и обкатать голосовой поток

## Риски и блокеры
—
