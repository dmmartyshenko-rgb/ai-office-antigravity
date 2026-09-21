# Стек: OpenMontage × OmniRoute × Herdr

Воспроизводимая обвязка, которая собирает три внешних проекта в один рабочий контур:

```
   ┌──────────────────────── фоновый сервер Herdr ────────────────────────┐
   │  workspace "openmontage"  (cwd = клон OpenMontage)                     │
   │  ┌────────────────────────────────────────────────────────────────┐  │
   │  │  Claude Code  ──водит──▶  пайплайны OpenMontage (видео-продакшн) │  │
   │  │      │ LLM-трафик                                                │  │
   │  └──────┼─────────────────────────────────────────────────────────┘  │
   └─────────┼─────────────────────────────────────────────────────────────┘
             ▼
     OmniRoute :20128  ──комбо/фоллбэк──▶  Anthropic / Gemini / OpenAI / free…
     (локальный proxy-роутер с резервными API)
```

- **OmniRoute** (`diegosouzapw/OmniRoute`) — локальный AI-gateway. Один эндпоинт
  `http://localhost:20128/v1`, за ним — цепочка провайдеров с авто-фоллбэком по
  квоте/здоровью. Это и есть «резервные API» для Claude Code.
- **OpenMontage** (`calesthio/OpenMontage`) — агентная система видео-продакшна.
  Её «мозг» — это Claude Code, читающий `AGENT_GUIDE.md` и запускающий пайплайны.
  Связка с роутером живёт на уровне запуска Claude Code, а не внутри кода OpenMontage.
- **Herdr** (`herdrdev/herdr`) — Rust-мультиплексор терминала, «runtime, на котором
  живут агенты». Держит панели в фоновом сервере — сессия переживает отключение клиента.

## Почему обвязка, а не клоны в репозитории

Клоны, `.venv` и `node_modules` — **эфемерны**: их пересоздают скрипты. В git-репозиторий
офиса коммитятся только скрипты и конфиги. Клоны кладутся в `$STACK_DIR` (по умолчанию
`~/ai-office-stack`) — вне репозитория. Это «плот, а не груз»: инструмент служит запуску,
а не тащит за собой чужую историю на тысячи файлов.

## Где это работает

Стек рассчитан на **постоянную машину с открытым egress** (твой Mac/сервер). В облачном
Claude Code окружении часть шагов упирается в сетевую политику (см. ниже) — там это
годится для сборки/проверки обвязки, но не для живого прогона.

## Системные зависимости

Ставятся системным пакетным менеджером (не скриптами):
`git`, `node>=22`, `python3>=3.10`, `ffmpeg` (нужен OpenMontage для рендера видео),
плюс `rust/cargo` — только если ставишь Herdr сборкой из исходников.

## Быстрый старт

```bash
cd stack/openmontage-omniroute-herdr
cp .env.example .env          # заполни STACK_DIR и ключи провайдеров (в git не попадёт)

scripts/01-clone.sh           # клонировать три репозитория в $STACK_DIR/repos
scripts/02-install.sh         # поставить зависимости и окружения всех трёх
scripts/03-omniroute-up.sh    # поднять роутер :20128 + завести резервные провайдеры
scripts/04-openmontage-link.sh# связать OpenMontage (Claude Code) с роутером
scripts/start-openmontage-session.sh start "Собери 30-сек ролик про X"
```

Посмотреть на живую сессию глазами: `herdr` (детач — `ctrl+b q`).
Проверить состояние: `scripts/doctor.sh` и `scripts/start-openmontage-session.sh status`.

## Скрипты

| Файл | Что делает |
|---|---|
| `scripts/lib.sh` | общая библиотека: загрузка `.env`, пути, логирование, ожидание портов |
| `scripts/01-clone.sh` | клон/обновление трёх репо в `$STACK_DIR/repos` (ref настраивается) |
| `scripts/02-install.sh` | OpenMontage `make setup`; OmniRoute `npm i -g omniroute`; Herdr `install.sh`/`cargo` |
| `scripts/03-omniroute-up.sh` | старт `omniroute serve`, ожидание health, `omniroute providers add` из `.env` |
| `scripts/04-openmontage-link.sh` | `.env` OpenMontage + env Claude Code→роутер + `omniroute setup-claude` |
| `scripts/start-openmontage-session.sh` | headless `herdr server` → workspace в папке OpenMontage → `omniroute run claude`; умеет `status`/`stop` |
| `scripts/doctor.sh` | диагностика: инструменты, клоны, окружения, порт, egress |

## Конфиги

- `.env.example` — все параметры и ключи (копируется в `.env`, который git игнорирует).
- `config/omniroute.combo.json` — образец цепочки фоллбэка для Claude Code.
- `config/claude-code.env.example` — ручной способ направить Claude Code на роутер.

## Связка OpenMontage → роутер: две плоскости

1. **LLM** (мозг агента): Claude Code ходит через OmniRoute. Основной способ —
   `omniroute run claude` (его выполняет стартовый скрипт внутри панели Herdr).
   Постоянный вариант — `omniroute setup-claude` (профиль в `~/.claude/profiles/`).
2. **Медиа-провайдеры** (FLUX, Veo, Kling, TTS, Sora…): ключи в `.env` самого
   OpenMontage (`$STACK_DIR/repos/OpenMontage/.env`). Роутер их не трогает.

## Клиентский ключ OmniRoute

Маршрутизация запросов (`/v1/chat/completions` с `model: auto`) работает **без ключа** —
роутер отвечает из коробки. Но команды вроде `omniroute setup-claude` и листинг
`/v1/models` требуют клиентского API-ключа OmniRoute. Заведи его один раз в дашборде
(`http://localhost:20128` → онбординг/API Keys), затем впиши в `.env`:
`OMNIROUTE_API_KEY=...` — скрипты сами прокинут его в `setup-claude`, в env Claude Code
и в панель Herdr.

## Ограничения egress облачного окружения (проверено 2026-09-21)

| Хост | Статус здесь | Нужен для |
|---|---|---|
| `api.anthropic.com` | ✅ доступен | Claude через роутер |
| `generativelanguage.googleapis.com` | ✅ доступен | Gemini-резерв, медиа OpenMontage |
| `api.openai.com` | ⛔ 403 (политика) | OpenAI-резерв, Sora |
| `openrouter.ai` | ⛔ 403 (политика) | OpenRouter-резерв |
| `pypi.org`, `registry.npmjs.org` | ✅ доступны | установка OpenMontage/OmniRoute |
| `herdr.dev/install.sh`, `crates.io` | ⛔ 403 (политика) | **установка Herdr — здесь невозможна** |

Вывод: в этом облаке можно собрать и проверить обвязку, установить OpenMontage и
OmniRoute, поднять роутер на доступных провайдерах. Herdr и полный фоллбэк
(OpenAI/OpenRouter) требуют машины с открытым egress. На своей машине весь контур
работает как задумано.
