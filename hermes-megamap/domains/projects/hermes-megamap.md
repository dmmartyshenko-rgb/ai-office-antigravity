# Hermes Megamap

## Статус
Актив. Обновлено: 2026-08-29.

## Где лежит
Репозиторий `ai-office-antigravity`, каталог `hermes-megamap/` (самодостаточен,
переносим в отдельный репозиторий без правок — корень ищется по `.hermes/`).

## Цель
Система внешней памяти: три слоя, метаболический пайплайн, CLI и линтер

## Артефакты
- `CLAUDE.md` — поведенческий контракт агента Hermes.
- `.hermes/scripts/hermes_cli.py` — CLI: init / add-raw / consolidate / decay / status / lint.
- `.hermes/scripts/metabolism.py` — пайплайн Triage → Consolidate → Decay & Audit.
- `.hermes/scripts/lint_megamap.py` — жёсткая валидация инвариантов (код 0 = зелёный).
- `.hermes/scripts/test_scenario.py` — воспроизводимый тест в temp-каталоге.
- `.hermes/config.json` — пороги decay, gravity, TTL буфера.

## Следующий шаг
обкатать на реальном потоке заметок пользователя (встречи, контакты) и откалибровать пороги decay в config.json

## Риски и блокеры
—
