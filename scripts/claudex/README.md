# Claudex Loop — связка Claude Code ↔ Codex

Обвязка над [chaseai-yt/claudex-loop](https://github.com/chaseai-yt/claudex-loop)
для парной разработки и перекрёстного ревью в едином сеансе CLI.

## Что это и чем НЕ является

Claudex Loop — не сервис и не отдельная программа, а **набор skills**. Ты
работаешь внутри одного host-CLI (Claude Code или Codex); host планирует и
координирует, а второй провайдер независимо ревьюит план, а затем инспектирует
код. Кто строил — тот не ставит себе оценку.

- Исходник завендорен в `tools/claudex-loop/` (commit зафиксирован в
  `tools/claudex-loop/.source-commit`; обновление — `git pull` в апстриме и
  повторное копирование скилов).
- Скилы установлены в `.claude/skills/`: `claudex-loop`, `claudex-route`,
  `codex-build`, `codex-review` — доступны как `/claudex-loop` и т.д. в сеансе
  Claude Code с этим репозиторием.

## Зависимости

- **Python 3.10+** — рантайм-адаптер `runner.py`, без pip-пакетов.
- **Claude Code CLI** и **Codex CLI** — оба установлены и залогинены для полной
  перекрёстной связки. Для dev-проверки апстрима нужен только `PyYAML`
  (см. `tools/claudex-loop/requirements-dev.txt`).

Проверить готовность:

```bash
scripts/claudex/claudex-doctor.sh
```

> ⚠️ В окружении, где создавалась эта обвязка, **Codex CLI отсутствовал** —
> перекрёстная половина там не проверялась вживую (это требует установки и
> логина Codex и тратит квоту моделей). Апстрим-тесты (`23 passed`) и
> `validate.py` пройдены; сами скрипты проверены на preflight.

## Конфиг связки

Единый файл дефолтов — `claudex.config.sh`. Скрипты его подхватывают (`source`),
переменные окружения имеют приоритет. Ключи повторяют раздел *Controls* из README
апстрима (`builder`, `plan`, `log`, `rounds`, `PROOF_CMD`, `*_model`, `*_effort`,
`research`, `inspect`, …). Дефолт `PROOF_CMD` для этого репо —
`python3 scripts/check_map.py` (целостность мегакарты).

## Скрипты запуска

| Скрипт | Для чего | Что делает |
|---|---|---|
| `claudex-doctor.sh` | проверка | диагностика окружения, ничего не запускает |
| `claudex-pair.sh "<задача>"` | парная разработка | полный цикл: recon → план → ревью → сборка → инспекция |
| `claudex-review.sh "<что>" [план]` | перекрёстное ревью | `mode=review`, независимый разбор плана/кода без сборки |

Скрипты открывают **управляемый** (интерактивный) сеанс host-CLI: согласования
и авторизацию держит человек. Обход отсутствия второго провайдера — только явно,
через `CLAUDEX_ALLOW_MISSING_PEER=1`.

### Примеры

```bash
# полный цикл, builder по умолчанию (claude), ревьюер/инспектор — codex
scripts/claudex/claudex-pair.sh "добавить JSON-экспорт домена мегакарты"

# сборку ведёт Codex, ревью/инспекцию — Claude
CLAUDEX_BUILDER=codex scripts/claudex/claudex-pair.sh "починить парсер журнала"

# перекрёстное ревью существующего плана, 3 раунда
CLAUDEX_ROUNDS=3 scripts/claudex/claudex-review.sh "план миграции" docs/migration.md
```

## Границы

Ревью-режимы работают в read-only песочнице (Codex — read-only shell; Claude —
только чтение/поиск, без MCP и кастомизаций). Чистый структурированный результат
не доказывает правоту модели: журнал (`PLAN-REVIEW-LOG.md`) хранит покрытие,
ограничения и доказательства. Коммиты и публикация следуют твоим обычным правилам.
Лицензия апстрима — MIT (`tools/claudex-loop/LICENSE`).
