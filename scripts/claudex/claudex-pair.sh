#!/usr/bin/env bash
# claudex-pair.sh — парная разработка через Claudex Loop.
# Открывает УПРАВЛЯЕМЫЙ сеанс host-CLI и запускает полный цикл:
#   recon -> requirements/plan -> независимое ревью другим провайдером
#   -> сборка авторизованным builder -> proof-проверки -> независимая инспекция.
# Человек рулит согласованиями; скрипт лишь корректно собирает вызов скила.
#
# Использование:
#   scripts/claudex/claudex-pair.sh "<что построить/изменить>"
#   CLAUDEX_BUILDER=codex scripts/claudex/claudex-pair.sh "..."   # переопределить на лету
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
# shellcheck source=claudex.config.sh
. "$HERE/claudex.config.sh"

TASK="${*:-}"
if [ -z "$TASK" ]; then
  echo "Задача не задана." >&2
  echo "Пример: $0 \"добавить экспорт домена мегакарты в JSON\"" >&2
  exit 2
fi

# --- Разрешить исполняемые файлы host и peer -----------------------------------
case "$CLAUDEX_HOST" in
  claude) HOST_BIN="$CLAUDEX_CLAUDE_BIN"; PEER_BIN="$CLAUDEX_CODEX_BIN"; PEER="codex" ;;
  codex)  HOST_BIN="$CLAUDEX_CODEX_BIN";  PEER_BIN="$CLAUDEX_CLAUDE_BIN"; PEER="claude" ;;
  *) echo "CLAUDEX_HOST должен быть claude или codex (сейчас: $CLAUDEX_HOST)" >&2; exit 2 ;;
esac

command -v "$HOST_BIN" >/dev/null 2>&1 || {
  echo "host CLI '$HOST_BIN' не найден. Запусти scripts/claudex/claudex-doctor.sh" >&2; exit 1; }

if ! command -v "$PEER_BIN" >/dev/null 2>&1; then
  echo "ВНИМАНИЕ: второй провайдер '$PEER' ($PEER_BIN) не установлен." >&2
  echo "Полный перекрёстный цикл (ревью/инспекция силами $PEER) не пройдёт." >&2
  if [ "${CLAUDEX_ALLOW_MISSING_PEER:-0}" != "1" ]; then
    echo "Установи и залогинь $PEER, либо запусти с CLAUDEX_ALLOW_MISSING_PEER=1 для явного обхода." >&2
    exit 1
  fi
  echo "CLAUDEX_ALLOW_MISSING_PEER=1 — продолжаю по явному указанию." >&2
fi

# --- Собрать строку контролов из непустых значений конфига ---------------------
controls="builder=${CLAUDEX_BUILDER}"
controls="${controls}, plan=${CLAUDEX_PLAN_FILE}, log=${CLAUDEX_LOG_FILE}"
controls="${controls}, rounds=${CLAUDEX_ROUNDS}"
controls="${controls}, MAX_FIX_ROUNDS=${CLAUDEX_MAX_FIX_ROUNDS}"
controls="${controls}, MAX_INSPECTION_ROUNDS=${CLAUDEX_MAX_INSPECTION_ROUNDS}"
controls="${controls}, research=${CLAUDEX_RESEARCH}, inspect=${CLAUDEX_INSPECT}"
[ -n "$CLAUDEX_REVIEWER_MODEL" ]   && controls="${controls}, reviewer_model=${CLAUDEX_REVIEWER_MODEL}"
[ -n "$CLAUDEX_BUILDER_MODEL" ]    && controls="${controls}, builder_model=${CLAUDEX_BUILDER_MODEL}"
[ -n "$CLAUDEX_INSPECTOR_MODEL" ]  && controls="${controls}, inspector_model=${CLAUDEX_INSPECTOR_MODEL}"
[ -n "$CLAUDEX_REVIEWER_EFFORT" ]  && controls="${controls}, reviewer_effort=${CLAUDEX_REVIEWER_EFFORT}"
[ -n "$CLAUDEX_BUILDER_EFFORT" ]   && controls="${controls}, builder_effort=${CLAUDEX_BUILDER_EFFORT}"
[ -n "$CLAUDEX_INSPECTOR_EFFORT" ] && controls="${controls}, inspector_effort=${CLAUDEX_INSPECTOR_EFFORT}"
[ -n "$CLAUDEX_PROOF_CMD" ]        && controls="${controls}, PROOF_CMD=${CLAUDEX_PROOF_CMD}"

PROMPT="/claudex-loop ${TASK}, ${controls}"

mkdir -p "$CLAUDEX_ARTIFACTS"
export CLAUDEX_ARTIFACTS

echo "host=$CLAUDEX_HOST  builder=$CLAUDEX_BUILDER  reviewer/inspector=$PEER"
echo "вызов: $PROMPT"
echo "-------------------------------------------------------------"
cd "$REPO_ROOT"
exec "$HOST_BIN" "$PROMPT"
