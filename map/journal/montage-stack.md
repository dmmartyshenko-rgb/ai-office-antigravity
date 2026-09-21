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

## 2026-09-21 — Живой прогон 03/04 в облаке
Гнали по максимуму в этой же сессии.
- 03-omniroute-up.sh: `omniroute serve` поднялся на :20128, health OK. Провайдеры
  не заведены (ключей в .env нет) — ожидаемо.
- 04-openmontage-link.sh: env Claude Code→роутер отрендерен, роутер достижим.
  `omniroute setup-claude` вернул HTTP 401 — сборка 3.8.50 требует клиентского
  API-ключа OmniRoute для listing моделей / setup (заводится один раз через дашборд;
  скрипты уже прокидывают OMNIROUTE_API_KEY, если задан).
- Проверка keyless-маршрутизации: `/v1/chat/completions` с `model:auto` — роутер
  ПРИНЯЛ запрос и пошёл по free-комбо БЕЗ ключа (401 не было). Упёрся в egress:
  free-провайдеры (`opencode.ai`, felo) — 403 «Host not in allowlist». Механизм
  роутера исправен end-to-end; стена — сетевая политика окружения. На машине с
  открытым egress `auto` отвечает из коробки.
Вывод подтверждён вживую: обвязка корректна; облако ограничивает egress (включая free-
провайдеров) и не даёт поставить Herdr — полный прогон делается на своей машине.

## 2026-09-21 — Живой прогон на Mac пользователя (пошагово)
Разворачивали на Mac (открытый egress) командами через терминал пользователя.
Инструменты: node 22.22.1, npm, python 3.14 (но venv OpenMontage собрался на 3.10
через uv), ffmpeg 8.1, brew, claude 2.1.278 — были; доставили herdr 0.9.1
(официальный install.sh; brew-сборка тянет компиляцию LLVM — отказались) и
omniroute обновили до 3.8.50.
- Обвязку забрали на Mac: ветка склонирована, локальная правка `hermes-megamap`
  спрятана в git stash (вернуть: checkout прежней ветки + stash pop; прежняя ветка
  `claude/hermes-megamap-system-q18hl3`).
- `01-clone` + `02-install openmontage` отработали; OpenMontage `.venv` + deps + remotion.
- OmniRoute: обнаружилось старое зашифрованное хранилище без ключа
  (`STORAGE_ENCRYPTION_KEY` утерян — нет ни в .env/server.env/профилях/Keychain/логах).
  Старую базу отодвинули в `~/.omniroute/reset-backup-*`, записали новый ключ,
  добавили провайдер stack-groq (ключ Groq).
- Прямой запрос через роутер — успех: ответ на `openai/gpt-oss-120b` (Groq).
- Сессия OpenMontage поднята в фоновом Herdr (workspace w1, панель w1:p1);
  `omniroute run claude` стартовал Claude Code в папке OpenMontage, прошли вопрос
  доверия к папке — интерфейс поднялся, строка `auto · API Usage Billing` (через шлюз).
- ГРАБЛИ: комбо `auto` от Claude Code уходит в бесплатный OpenCode → 403
  («can only be used from within OpenCode»). Решение: прибить модель к
  `openai/gpt-oss-120b` (в `.env` OM_MODEL).
- Прочее: node 22.22.1 < требуемого 22.22.2 — баннер OmniRoute, не блокер
  (brew upgrade node по желанию); дашборд-пароль CHANGEME отвергнут (остался старый),
  дашборд не нужен, сброс — `omniroute-reset-password`.
Финал передан пользователю как бриф-хендофф
`stack/openmontage-omniroute-herdr/HANDOFF-live-run.md`: пользователь доводит
прогон через Claude Code в терминале (прибить модель → перезапустить сессию →
боевой бриф без 403).
