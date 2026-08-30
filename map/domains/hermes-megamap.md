# hermes-megamap — система социальной и проектной внешней памяти

## Статус
Активен. Обновлено: 2026-08-29.

## Ветка
`claude/hermes-megamap-system-q18hl3`

## Цель
Локальная CLI-система долговременной внешней памяти по ТЗ «Hermes Megamap»:
трёхслойное мегакартирование (INDEX → карты доменов → append-only журналы)
+ принципы Memory as Metabolism (Triage → Consolidate → Decay & Audit) для
проектных доменов и социальных связей (Friend Health Score).

## Артефакты
Всё в `hermes-megamap/` (самодостаточный каталог, переносим в отдельный репозиторий):
- `CLAUDE.md` — контракт агента; `INDEX.md` — слой 1 (≤ 60 строк);
- `buffer/`, `domains/{projects,relationships}/`, `logs/…/*.log.md`, `cold/sources/`;
- `.hermes/scripts/hermes_cli.py` — CLI (init/add-raw/consolidate/decay/status/lint/ui/bot);
- `.hermes/scripts/metabolism.py` — метаболический пайплайн + SQLite metadata.db;
- `.hermes/scripts/hermes_ui.py` — веб-дашборд «Экспедиционная карта»: карточки,
  радар связей, экран домена; stdlib-сервер на 127.0.0.1:8137;
- `.hermes/scripts/telegram_bot.py` — приёмная: голос/текст → Triage-буфер,
  белый список chat_id, расшифровка faster-whisper (опционально);
- `.hermes/scripts/lint_megamap.py` — валидация инвариантов;
- `.hermes/scripts/test_scenario.py` — 34 проверки в temp-каталоге (PASS);
- дизайн-макет (3 экрана, «Экспедиционная карта») — артефакт
  claude.ai/code/artifact/a4439f45-58d2-4f1f-b803-351da1af5766.

## Следующий шаг
Пользователь заводит бота у BotFather (токен → TELEGRAM_BOT_TOKEN, chat_id →
config.json) и обкатывает голосовой поток; по итогам — калибровка порогов decay.

## Риски / открытые вопросы
- Кластеризация consolidate — эвристическая (директивы @ + gravity по упоминаниям);
  умную кластеризацию делает агент Hermes, скрипт — детерминированную базу.
- Два экземпляра мегакарты в одном репо (map/ среды и hermes-megamap/) — не путать:
  map/ про разработки среды, hermes-megamap/ — про жизнь пользователя.
