# Журнал: montage-stack

## 2026-09-21 — Домен создан, обвязка написана и валидирована
Задача: склонировать OpenMontage/OmniRoute/Herdr, поставить зависимости, настроить
OmniRoute локальным proxy-роутером для Claude Code с резервными API, связать с ним
OpenMontage и подготовить старт сессий OpenMontage в фоновом Herdr.

Определены реальные репозитории: `calesthio/OpenMontage`, `diegosouzapw/OmniRoute`,
`herdrdev/herdr`. Все три склонированы (в `$STACK_DIR/repos`, вне git-репо офиса).

Разобрана механика каждого:
- OmniRoute: `npm i -g omniroute` → `omniroute serve` (:20128); связка Claude Code —
  `omniroute run claude` (runtime) или `omniroute setup-claude` (профиль); резервы —
  `omniroute providers add <p> --credential-env <ENV>`; фоллбэк — комбо.
- OpenMontage: `make setup` (venv + requirements + remotion-composer); LLM — это сам
  Claude Code, поэтому связка с роутером на уровне запуска Claude Code, а медиа-ключи
  (FLUX/Veo/TTS) — в `.env` OpenMontage, роутера не касаются.
- Herdr: headless `herdr server`; `herdr workspace create --cwd --env`, `herdr pane run`,
  `herdr agent start/prompt/wait` — программный запуск и вождение сессий агента.

Написана обвязка в `stack/openmontage-omniroute-herdr/` (скрипты 01–04, стартовый
скрипт сессии, doctor, конфиги, README). Клоны/venv намеренно вне репозитория —
воспроизводимость важнее, чем таскать чужой код (23k файлов OmniRoute) в git.

Валидация в этой облачной сессии:
- OpenMontage `make setup` → exit 0; `.venv` (py3.10.20), импорты pydantic/fastapi/yaml
  OK, remotion `node_modules` на месте, `.env` создан. ffmpeg на PATH отсутствует.
- OmniRoute `npm i -g omniroute` → exit 0; `omniroute serve` поднялся, health OK,
  отдаёт `http://localhost:20128/v1`.
- Herdr: установка невозможна в этом окружении — `herdr.dev/install.sh` и `crates.io`
  отдают 403 (egress-политика). Стартовый скрипт написан против документированного
  CLI, но вживую не прогнан — первый живой прогон на машине пользователя.

Egress окружения (проверено): anthropic + gemini + pypi + npm — доступны;
api.openai.com, openrouter.ai, herdr.dev, crates.io — 403. Тот же класс блокера,
что зафиксирован в route-loop: полноценный контур — на постоянной машine с открытым
egress.
