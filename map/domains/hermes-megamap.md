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
- `.hermes/scripts/hermes_cli.py` — CLI (init/add-raw/consolidate/decay/status/lint);
- `.hermes/scripts/metabolism.py` — метаболический пайплайн + SQLite metadata.db;
- `.hermes/scripts/lint_megamap.py` — валидация инвариантов;
- `.hermes/scripts/test_scenario.py` — воспроизводимый тестовый сценарий (PASS).

## Следующий шаг
Обкатать на реальном потоке заметок (встречи, контакты), откалибровать пороги
в `.hermes/config.json`; решить, выносить ли в отдельный репозиторий.

## Риски / открытые вопросы
- Кластеризация consolidate — эвристическая (директивы @ + gravity по упоминаниям);
  умную кластеризацию делает агент Hermes, скрипт — детерминированную базу.
- Два экземпляра мегакарты в одном репо (map/ среды и hermes-megamap/) — не путать:
  map/ про разработки среды, hermes-megamap/ — про жизнь пользователя.
