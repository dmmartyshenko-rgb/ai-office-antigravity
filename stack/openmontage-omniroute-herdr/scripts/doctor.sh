#!/usr/bin/env bash
# Диагностика стека: инструменты, клоны, окружения, порт роутера, egress.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

row() { printf '  %-26s %s\n' "$1" "$2"; }
check() { if eval "$2" >/dev/null 2>&1; then row "$1" "ok"; else row "$1" "— нет"; fi; }

echo "== Инструменты =="
for t in git node npm python3 cargo tmux jq curl ffmpeg; do
  if have "$t"; then row "$t" "$($t --version 2>&1 | head -1)"; else row "$t" "— нет"; fi
done
for t in omniroute herdr claude; do check "$t" "have $t"; done

echo "== Клоны ($REPOS_DIR) =="
for d in "$OM_DIR" "$OR_DIR" "$HD_DIR"; do
  n="$(basename "$d")"
  [ -d "$d/.git" ] && row "$n" "$(git -C "$d" rev-parse --short HEAD)" || row "$n" "— не склонирован"
done

echo "== Окружения =="
check "OpenMontage .venv" "[ -x '$OM_DIR/.venv/bin/python' ]"
check "OpenMontage .env"  "[ -f '$OM_DIR/.env' ]"
check "remotion node_modules" "[ -d '$OM_DIR/remotion-composer/node_modules' ]"

echo "== Роутер =="
printf '  %-26s ' "OmniRoute $OMNIROUTE_BASE_URL"; http_ok "$OMNIROUTE_BASE_URL" && echo "up" || echo "down"

echo "== Egress к провайдерам (через прокси окружения) =="
for h in api.anthropic.com generativelanguage.googleapis.com api.openai.com openrouter.ai; do
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 12 "https://$h" 2>/dev/null)" || true
  case "$code" in
    000|"") row "$h" "ЗАБЛОКИРОВАН" ;;
    *) row "$h" "доступен (HTTP $code)" ;;
  esac
done
