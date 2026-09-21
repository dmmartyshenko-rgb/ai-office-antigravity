#!/usr/bin/env bash
# Общая библиотека для скриптов стека OpenMontage + OmniRoute + Herdr.
# Подключается через:  source "$(dirname "$0")/lib.sh"
set -euo pipefail

# --- Корни ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"   # .../stack/openmontage-omniroute-herdr

# --- Загрузка .env (если есть), иначе значения по умолчанию из .env.example ---
if [ -f "$STACK_ROOT/.env" ]; then
  set -a; # shellcheck disable=SC1091
  source "$STACK_ROOT/.env"; set +a
fi

# Значения по умолчанию (перекрываются .env)
: "${STACK_DIR:=$HOME/ai-office-stack}"
: "${OPENMONTAGE_REPO:=https://github.com/calesthio/OpenMontage}"
: "${OPENMONTAGE_REF:=main}"
: "${OMNIROUTE_REPO:=https://github.com/diegosouzapw/OmniRoute}"
: "${OMNIROUTE_REF:=release/v3.8.51}"
: "${HERDR_REPO:=https://github.com/herdrdev/herdr}"
: "${HERDR_REF:=master}"
: "${OMNIROUTE_PORT:=20128}"
: "${OMNIROUTE_BASE_URL:=http://localhost:${OMNIROUTE_PORT}}"
: "${OMNIROUTE_INSTALL:=npm}"
: "${OM_MODEL:=auto}"
: "${OMNIROUTE_API_KEY:=}"
: "${HERDR_INSTALL:=script}"
: "${HERDR_SESSION_NAME:=openmontage}"

# Производные пути
REPOS_DIR="$STACK_DIR/repos"
OM_DIR="$REPOS_DIR/OpenMontage"
OR_DIR="$REPOS_DIR/OmniRoute"
HD_DIR="$REPOS_DIR/herdr"

# --- Логирование ---
_c() { printf '\033[%sm' "$1"; }
log()  { printf '%s==>%s %s\n' "$(_c '1;36')" "$(_c 0)" "$*"; }
ok()   { printf '%s ok %s %s\n' "$(_c '1;32')" "$(_c 0)" "$*"; }
warn() { printf '%swarn%s %s\n' "$(_c '1;33')" "$(_c 0)" "$*" >&2; }
die()  { printf '%sERR %s %s\n' "$(_c '1;31')" "$(_c 0)" "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

# Проверить, что порт отвечает по HTTP
http_ok() { curl -fsS -o /dev/null --max-time 5 "$1" 2>/dev/null; }

# Дождаться готовности URL (аргументы: url, попыток, пауза_сек)
wait_http() {
  local url="$1" tries="${2:-30}" gap="${3:-2}" i
  for i in $(seq 1 "$tries"); do
    if http_ok "$url"; then return 0; fi
    sleep "$gap"
  done
  return 1
}
