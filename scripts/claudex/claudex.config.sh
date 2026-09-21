# shellcheck shell=sh
# claudex.config.sh — единый конфиг связки Claude Code <-> Codex для Claudex Loop.
#
# Это НЕ отдельная программа. Claudex Loop — набор skills (см. tools/claudex-loop
# и .claude/skills/claudex-loop). Скилы работают внутри одного сеанса CLI (host)
# и делегируют второму провайдеру ревью/сборку через runner.py. Этот файл задаёт
# ПРОЕКТНЫЕ ДЕФОЛТЫ связки; скрипты запуска в этой папке его подхватывают (source),
# а уже заданные в окружении переменные имеют приоритет над значениями отсюда.
#
# Соответствие ключам из README проекта (раздел Controls) указано в комментариях.

# --- Кто с кем в связке -------------------------------------------------------

# Host — CLI, ИЗ КОТОРОГО стартует сеанс. Планирует host, ревьюит всегда другой.
#   claude | codex
: "${CLAUDEX_HOST:=claude}"

# Builder — кто реализует после утверждения плана (README: builder).
# Инспектор выбирается автоматически как противоположный провайдер.
#   claude | codex
: "${CLAUDEX_BUILDER:=claude}"

# --- Файлы плана и журнала (README: plan / log) -------------------------------
: "${CLAUDEX_PLAN_FILE:=PLAN.md}"
: "${CLAUDEX_LOG_FILE:=PLAN-REVIEW-LOG.md}"

# --- Бюджеты циклов (README: rounds / MAX_FIX_ROUNDS / MAX_INSPECTION_ROUNDS) -
: "${CLAUDEX_ROUNDS:=5}"
: "${CLAUDEX_MAX_FIX_ROUNDS:=2}"
: "${CLAUDEX_MAX_INSPECTION_ROUNDS:=2}"

# --- Явные модели по ролям (README: *_model). Пусто = дефолт соответствующего CLI.
# Рекомендованные проектом при доступности: Claude Fable 5.1 и GPT-6 Astra.
: "${CLAUDEX_REVIEWER_MODEL:=}"
: "${CLAUDEX_BUILDER_MODEL:=}"
: "${CLAUDEX_INSPECTOR_MODEL:=}"

# --- Уровень reasoning по ролям (README: *_effort). Пусто = дефолт CLI.
#   low | medium | high | xhigh | max
: "${CLAUDEX_REVIEWER_EFFORT:=}"
: "${CLAUDEX_BUILDER_EFFORT:=}"
: "${CLAUDEX_INSPECTOR_EFFORT:=}"

# --- Прочие контролы ----------------------------------------------------------
# Глубина исследования (README: research): none | web | deep
: "${CLAUDEX_RESEARCH:=web}"

# Финальная независимая инспекция кода (README: inspect): on | off
: "${CLAUDEX_INSPECT:=on}"

# Команда-доказательство, проверяющая результат (README: PROOF_CMD).
# Для этого репозитория осмысленный дефолт — проверка целостности мегакарты.
: "${CLAUDEX_PROOF_CMD:=python3 scripts/check_map.py}"

# Каталог диагностики прогонов — ВНЕ рабочего чекаута (README: artifacts).
: "${CLAUDEX_ARTIFACTS:=$HOME/.claudex-loop/artifacts}"

# Пути к CLI, если в PATH оказалась устаревшая установка (runner: --cli).
: "${CLAUDEX_CLAUDE_BIN:=claude}"
: "${CLAUDEX_CODEX_BIN:=codex}"
