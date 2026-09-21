#!/usr/bin/env bash
# claudex-review.sh — перекрёстное ревью через Claudex Loop (mode=review).
# Другой провайдер независимо разбирает существующий план/код и возвращает
# findings с доказательствами; host координирует ограниченный цикл правок.
# Сборку НЕ запускает: запрос на ревью не авторизует реализацию.
#
# Использование:
#   scripts/claudex/claudex-review.sh "<что ревьюить>" [путь-к-плану]
#   scripts/claudex/claudex-review.sh "миграция БД" docs/migration.md
#   CLAUDEX_ROUNDS=3 scripts/claudex/claudex-review.sh "план рефактора"
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
# shellcheck source=claudex.config.sh
. "$HERE/claudex.config.sh"

TASK="${1:-}"
PLAN_ARG="${2:-$CLAUDEX_PLAN_FILE}"
if [ -z "$TASK" ]; then
  echo "Не задано, что ревьюить." >&2
  echo "Пример: $0 \"план миграции\" docs/migration.md" >&2
  exit 2
fi

case "$CLAUDEX_HOST" in
  claude) HOST_BIN="$CLAUDEX_CLAUDE_BIN"; PEER_BIN="$CLAUDEX_CODEX_BIN"; PEER="codex" ;;
  codex)  HOST_BIN="$CLAUDEX_CODEX_BIN";  PEER_BIN="$CLAUDEX_CLAUDE_BIN"; PEER="claude" ;;
  *) echo "CLAUDEX_HOST должен быть claude или codex (сейчас: $CLAUDEX_HOST)" >&2; exit 2 ;;
esac

command -v "$HOST_BIN" >/dev/null 2>&1 || {
  echo "host CLI '$HOST_BIN' не найден. Запусти scripts/claudex/claudex-doctor.sh" >&2; exit 1; }

if ! command -v "$PEER_BIN" >/dev/null 2>&1; then
  echo "ВНИМАНИЕ: ревьюер '$PEER' ($PEER_BIN) не установлен — перекрёстное ревью не пройдёт." >&2
  if [ "${CLAUDEX_ALLOW_MISSING_PEER:-0}" != "1" ]; then
    echo "Установи и залогинь $PEER, либо запусти с CLAUDEX_ALLOW_MISSING_PEER=1." >&2
    exit 1
  fi
  echo "CLAUDEX_ALLOW_MISSING_PEER=1 — продолжаю по явному указанию." >&2
fi

controls="mode=review, plan=${PLAN_ARG}, log=${CLAUDEX_LOG_FILE}, rounds=${CLAUDEX_ROUNDS}"
[ -n "$CLAUDEX_REVIEWER_MODEL" ]  && controls="${controls}, reviewer_model=${CLAUDEX_REVIEWER_MODEL}"
[ -n "$CLAUDEX_REVIEWER_EFFORT" ] && controls="${controls}, reviewer_effort=${CLAUDEX_REVIEWER_EFFORT}"

PROMPT="/claudex-loop ${TASK}, ${controls}"

mkdir -p "$CLAUDEX_ARTIFACTS"
export CLAUDEX_ARTIFACTS

echo "host=$CLAUDEX_HOST  reviewer=$PEER  plan=$PLAN_ARG  rounds=$CLAUDEX_ROUNDS"
echo "вызов: $PROMPT"
echo "-------------------------------------------------------------"
cd "$REPO_ROOT"
exec "$HOST_BIN" "$PROMPT"
