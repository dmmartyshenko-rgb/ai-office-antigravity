# montage-stack — OpenMontage × OmniRoute × Herdr

## Статус
Активен. Обвязка написана и валидирована в облачной сессии (2026-09-21).
OpenMontage и OmniRoute установлены и проверены здесь; Herdr — только в обвязке
(установка в этом облаке заблокирована egress'ом, разворачивается на своей машине).

## Ветка
`claude/openmontage-omniroute-herdr-setup-6p1cw5`.

## Цель
Собрать три внешних проекта в один контур: **OmniRoute** — локальный proxy-роутер
(:20128) с резервными API и авто-фоллбэком; **Claude Code** ходит через роутер и
**водит OpenMontage** (агентный видео-продакшн); всё это живёт в панели фонового
сервера **Herdr** и переживает отключение клиента.

## Артефакты
- `stack/openmontage-omniroute-herdr/README.md` — архитектура, egress, использование.
- `stack/openmontage-omniroute-herdr/.env.example` — параметры и ключи (→ `.env`, вне git).
- `scripts/01-clone.sh … 04-openmontage-link.sh` — клон, установка, роутер, связка.
- `scripts/start-openmontage-session.sh` — запуск сессии OpenMontage в фоновом Herdr (`start`/`status`/`stop`).
- `scripts/doctor.sh` — диагностика (инструменты, клоны, окружения, порт, egress).
- `config/omniroute.combo.json` — образец цепочки фоллбэка для Claude Code.
- `config/claude-code.env.example` — ручной способ направить Claude Code на роутер.
- Клоны/venv — в `$STACK_DIR` (`~/ai-office-stack`), эфемерны, вне репозитория.

## Следующий шаг
На постоянной машине с открытым egress: `cp .env.example .env` (вписать ключи) →
`01…04` → `start-openmontage-session.sh start "<бриф>"`. В облаке Herdr и
резервы OpenAI/OpenRouter недоступны — либо открыть сетевую политику окружения
(`herdr.dev`, `crates.io`, `api.openai.com`, `openrouter.ai`), либо запускать локально.

## Риски / открытые вопросы
- Egress облака (проверено 2026-09-21): anthropic + gemini + pypi + npm доступны;
  `api.openai.com`, `openrouter.ai`, `herdr.dev/install.sh`, `crates.io` — 403.
  Тот же класс блокера, что у route-loop.
- Стартовый скрипт валидирован против документированного CLI Herdr
  (`workspace create`/`pane run`/`agent prompt`), но не прогнан вживую здесь —
  Herdr в этом окружении не установить. Первый живой прогон — на машине пользователя.
- OpenMontage требует `ffmpeg` на PATH (в облачном образе отсутствовал) — системная зависимость.
- Ключи провайдеров и медиа-ключи OpenMontage — за пользователем; в git не коммитятся.
