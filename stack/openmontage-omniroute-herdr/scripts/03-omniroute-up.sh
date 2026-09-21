#!/usr/bin/env bash
# Поднимает OmniRoute как локальный proxy-роутер и (best-effort) заводит
# резервные провайдеры из ключей в .env. Идемпотентно: уже запущенный сервер
# не дублируется.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

have omniroute || die "omniroute не установлен — сначала 02-install.sh"

LOG_DIR="$STACK_DIR/logs"; mkdir -p "$LOG_DIR"
HEALTH="$OMNIROUTE_BASE_URL/v1/models"

# --- 1. Старт сервера (если ещё не отвечает) ---
if http_ok "$HEALTH" || http_ok "$OMNIROUTE_BASE_URL"; then
  ok "OmniRoute уже слушает на $OMNIROUTE_BASE_URL — переиспользую"
else
  log "Стартую omniroute serve (порт $OMNIROUTE_PORT) → $LOG_DIR/omniroute.log"
  PORT="$OMNIROUTE_PORT" nohup omniroute serve >"$LOG_DIR/omniroute.log" 2>&1 &
  echo $! > "$LOG_DIR/omniroute.pid"
  if wait_http "$OMNIROUTE_BASE_URL" 45 2; then
    ok "OmniRoute поднялся на $OMNIROUTE_BASE_URL (pid $(cat "$LOG_DIR/omniroute.pid"))"
  else
    warn "Сервер не ответил за отведённое время — смотри $LOG_DIR/omniroute.log"
  fi
fi

# --- 2. Резервные провайдеры из .env (best-effort) ---
add_provider() {
  local slug="$1" env_name="$2"; local val="${!env_name:-}"
  [ -n "$val" ] || return 0
  log "Провайдер $slug ← \$$env_name"
  export "$env_name"="$val"
  omniroute providers add "$slug" --credential-env "$env_name" --name "stack-$slug" \
    && ok "провайдер $slug подключён" \
    || warn "не удалось добавить $slug (возможно уже есть) — проверь: omniroute providers list"
}
add_provider anthropic  ANTHROPIC_API_KEY
add_provider gemini     GEMINI_API_KEY
add_provider openai     OPENAI_API_KEY
add_provider openrouter OPENROUTER_API_KEY
add_provider groq       GROQ_API_KEY

# --- 3. Статус ---
log "Провайдеры/здоровье:"
omniroute providers list 2>/dev/null || true
echo
ok "Роутер готов. Эндпоинт для Claude Code: $OMNIROUTE_BASE_URL/v1"
echo "   Дашборд: $OMNIROUTE_BASE_URL   |   комбо/фоллбэк: config/omniroute.combo.json"
