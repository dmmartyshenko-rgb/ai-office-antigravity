#!/usr/bin/env bash
# Запускает сессию OpenMontage (Claude Code, идущий через OmniRoute) внутри
# ФОНОВОГО сервера Herdr. Панель живёт в headless-сервере herdr и переживает
# отключение клиента; подключиться глазами — командой `herdr`.
#
#   start-openmontage-session.sh [start] ["первый бриф агенту"]
#   start-openmontage-session.sh status
#   start-openmontage-session.sh stop
#
# Поток: OmniRoute(:20128) ←— Claude Code ——(водит)——> OpenMontage-пайплайны
#        всё это — в панели фонового Herdr.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

have herdr     || die "herdr не установлен — сначала 02-install.sh"
[ -d "$OM_DIR" ] || die "нет клона OpenMontage — сначала 01-clone.sh"

HERDR_LOG="$STACK_DIR/logs/herdr-server.log"; mkdir -p "$STACK_DIR/logs"

herdr_server_up() { herdr workspace list >/dev/null 2>&1; }

ensure_herdr_server() {
  if herdr_server_up; then ok "herdr сервер уже работает"; return; fi
  log "Стартую headless herdr сервер → $HERDR_LOG"
  nohup herdr server >"$HERDR_LOG" 2>&1 &
  echo $! > "$STACK_DIR/logs/herdr-server.pid"
  for _ in $(seq 1 20); do herdr_server_up && break; sleep 1; done
  herdr_server_up && ok "herdr сервер поднят" || die "herdr сервер не поднялся — см. $HERDR_LOG"
}

ensure_router() {
  if http_ok "$OMNIROUTE_BASE_URL"; then ok "OmniRoute отвечает на $OMNIROUTE_BASE_URL"; return; fi
  warn "OmniRoute не отвечает — поднимаю через 03-omniroute-up.sh"
  "$SCRIPT_DIR/03-omniroute-up.sh" || warn "не удалось поднять роутер автоматически"
}

# Извлечь id из вывода herdr (json → jq, иначе первый похожий на id токен)
extract_id() {
  local out="$1" key="$2"
  if have jq && printf '%s' "$out" | jq -e . >/dev/null 2>&1; then
    printf '%s' "$out" | jq -r "..|.${key}? // empty" 2>/dev/null | head -1 && return
  fi
  printf '%s' "$out" | grep -oiE "[0-9a-f]{6,}(-[0-9a-f]+)*" | head -1
}

cmd_start() {
  local brief="${1:-}"
  ensure_router
  ensure_herdr_server

  log "Создаю herdr workspace в $OM_DIR (env → роутер)"
  local ws_out ws_id
  ws_out="$(herdr workspace create \
      --cwd "$OM_DIR" \
      --label "$HERDR_SESSION_NAME" \
      --env "ANTHROPIC_BASE_URL=$OMNIROUTE_BASE_URL" \
      --env "ANTHROPIC_AUTH_TOKEN=${OMNIROUTE_API_KEY:-omniroute}" \
      --env "ANTHROPIC_MODEL=$OM_MODEL" \
      --no-focus 2>&1)" || die "herdr workspace create не удался:\n$ws_out"
  ws_id="$(extract_id "$ws_out" workspace_id)"; ws_id="${ws_id:-$(extract_id "$ws_out" id)}"
  ok "workspace: ${ws_id:-<см. herdr workspace list>}"

  log "Нахожу панель рабочего пространства"
  local pane_out pane_id
  pane_out="$(herdr pane list ${ws_id:+--workspace "$ws_id"} 2>&1)"
  pane_id="$(extract_id "$pane_out" pane_id)"; pane_id="${pane_id:-$(extract_id "$pane_out" id)}"
  [ -n "$pane_id" ] || die "не нашёл id панели:\n$pane_out"
  ok "панель: $pane_id"

  log "Запускаю Claude Code через роутер в панели (omniroute run claude, model=$OM_MODEL)"
  herdr pane run "$pane_id" "omniroute run claude --model '$OM_MODEL' --port '$OMNIROUTE_PORT'" \
    || die "не удалось запустить команду в панели"
  ok "Claude Code запущен в OpenMontage-панели фонового Herdr"

  if [ -n "$brief" ]; then
    log "Жду обнаружения агента и отправляю первый бриф"
    herdr agent wait "$pane_id" --until idle --timeout 60000 2>/dev/null || true
    herdr agent prompt "$pane_id" "$brief" --wait --until idle --timeout 600000 \
      && ok "бриф выполнен" \
      || warn "бриф не отправлен автоматически — подключись через 'herdr' и продолжи вручную"
  fi

  echo
  ok "Сессия OpenMontage живёт в фоновом Herdr."
  echo "   Посмотреть глазами:   herdr           (детач: ctrl+b q)"
  echo "   Список панелей:       herdr pane list"
  echo "   Отправить задачу:     herdr agent prompt $pane_id \"<текст>\""
  echo "   Остановить всё:       $(basename "$0") stop"
}

cmd_status() {
  printf '• OmniRoute: '; http_ok "$OMNIROUTE_BASE_URL" && echo "up ($OMNIROUTE_BASE_URL)" || echo "down"
  printf '• herdr сервер: '; herdr_server_up && echo "up" || echo "down"
  herdr_server_up && { echo "— workspaces —"; herdr workspace list 2>/dev/null; echo "— agents —"; herdr agent list 2>/dev/null; }
}

cmd_stop() {
  herdr_server_up && herdr server stop 2>/dev/null && ok "herdr сервер остановлен" || warn "herdr сервер не был запущен"
  if [ -f "$STACK_DIR/logs/omniroute.pid" ]; then
    kill "$(cat "$STACK_DIR/logs/omniroute.pid")" 2>/dev/null && ok "OmniRoute остановлен" || true
    rm -f "$STACK_DIR/logs/omniroute.pid"
  fi
}

case "${1:-start}" in
  start)  shift || true; cmd_start "${1:-}" ;;
  status) cmd_status ;;
  stop)   cmd_stop ;;
  *) die "usage: $(basename "$0") [start [\"бриф\"] | status | stop]" ;;
esac
