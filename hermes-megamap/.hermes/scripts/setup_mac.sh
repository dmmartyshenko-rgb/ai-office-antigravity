#!/bin/bash
# Hermes Megamap — установка «под ключ» на macOS.
#
#   bash .hermes/scripts/setup_mac.sh            # установить и запустить всё
#   bash .hermes/scripts/setup_mac.sh status     # что запущено, хвосты логов
#   bash .hermes/scripts/setup_mac.sh stop       # остановить бота и дашборд
#
# Делает: гасит старые экземпляры бота, сбрасывает webhook, кладёт токен в
# Связку ключей macOS (не в файлы!), ставит Python 3.12 + faster-whisper для
# расшифровки голоса, прописывает бота и дашборд в автозагрузку (launchd:
# старт при входе, авторестарт при падении). Логи: .hermes/logs/.
set -u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KEYCHAIN_SVC="hermes-megamap-telegram"
LA_DIR="$HOME/Library/LaunchAgents"
BOT_PLIST="$LA_DIR/com.hermes-megamap.bot.plist"
UI_PLIST="$LA_DIR/com.hermes-megamap.ui.plist"
LOG_DIR="$ROOT/.hermes/logs"
CMD="${1:-install}"

say()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }

stop_all() {
  launchctl unload "$BOT_PLIST" 2>/dev/null
  launchctl unload "$UI_PLIST" 2>/dev/null
  pkill -f "hermes_cli.py bot" 2>/dev/null
  pkill -f "telegram_bot.py" 2>/dev/null
  pkill -f "hermes_ui.py" 2>/dev/null
  pkill -f "hermes_cli.py ui" 2>/dev/null
  sleep 1
}

case "$CMD" in
  stop)
    say "Останавливаю бота и дашборд…"
    stop_all
    say "Готово. Снова запустить: bash .hermes/scripts/setup_mac.sh"
    exit 0 ;;
  status)
    echo "--- процессы ---"
    pgrep -fl "hermes_cli.py|telegram_bot|hermes_ui" || echo "(ничего не запущено)"
    echo "--- хвост лога бота ---";  tail -n 5 "$LOG_DIR/bot.log" 2>/dev/null || echo "(лога нет)"
    echo "--- хвост лога дашборда ---"; tail -n 3 "$LOG_DIR/ui.log" 2>/dev/null || echo "(лога нет)"
    exit 0 ;;
  install) ;;
  *) warn "Неизвестная команда: $CMD (жду install|status|stop)"; exit 2 ;;
esac

mkdir -p "$LOG_DIR" "$LA_DIR"

# ── 1. Токен: Связка ключей ────────────────────────────────────────────────
TOKEN="$(security find-generic-password -s "$KEYCHAIN_SVC" -w 2>/dev/null || true)"
if [ -z "$TOKEN" ] && [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
  TOKEN="$TELEGRAM_BOT_TOKEN"
fi
if [ -z "$TOKEN" ]; then
  printf 'Вставьте токен бота от @BotFather (ввод скрыт) и нажмите Enter: '
  read -rs TOKEN; echo
fi
if [ -z "$TOKEN" ]; then warn "Без токена не поеду."; exit 1; fi
security add-generic-password -s "$KEYCHAIN_SVC" -a "$USER" -w "$TOKEN" -U >/dev/null
say "Токен сохранён в Связке ключей macOS (сервис: $KEYCHAIN_SVC)."

# ── 2. Прибрать старые экземпляры и webhook (лечит HTTP 409) ───────────────
say "Гашу старые экземпляры бота и сбрасываю webhook…"
stop_all
curl -s "https://api.telegram.org/bot$TOKEN/deleteWebhook" >/dev/null || true

# ── 3. Python для расшифровки: 3.12 (у 3.13+ нет колёс faster-whisper) ─────
PY=""
for cand in python3.12 /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12; do
  command -v "$cand" >/dev/null 2>&1 && { PY="$cand"; break; }
done
if [ -z "$PY" ] && command -v brew >/dev/null 2>&1; then
  say "Ставлю Python 3.12 через Homebrew (нужен для расшифровки голоса)…"
  brew install -q python@3.12 && PY="$(command -v python3.12 || echo /opt/homebrew/bin/python3.12)"
fi

VENV_PY="$ROOT/.venv/bin/python"
need_venv=1
if [ -x "$VENV_PY" ]; then
  case "$("$VENV_PY" -V 2>&1)" in
    *" 3.10."*|*" 3.11."*|*" 3.12."*) need_venv=0 ;;
    *) say "Пересоздаю .venv (в старом слишком новый Python)…"; rm -rf "$ROOT/.venv" ;;
  esac
fi
WHISPER=0
if [ "$need_venv" = 1 ]; then
  if [ -n "$PY" ]; then
    "$PY" -m venv "$ROOT/.venv"
  else
    warn "Python 3.12 не нашёлся — бот заработает, но БЕЗ авторасшифровки голоса."
    python3 -m venv "$ROOT/.venv"
  fi
fi
if [ -x "$VENV_PY" ]; then
  if "$VENV_PY" -c "import faster_whisper" 2>/dev/null; then
    WHISPER=1
  else
    case "$("$VENV_PY" -V 2>&1)" in
      *" 3.10."*|*" 3.11."*|*" 3.12."*)
        say "Ставлю faster-whisper (расшифровка голоса, пара минут)…"
        "$ROOT/.venv/bin/pip" -q install --upgrade pip >/dev/null
        if "$ROOT/.venv/bin/pip" -q install faster-whisper; then WHISPER=1
        else warn "faster-whisper не встал — бот заработает без расшифровки."; fi ;;
    esac
  fi
fi
[ "$WHISPER" = 1 ] && say "Расшифровка голоса: включена (faster-whisper)." \
                   || warn "Расшифровка голоса: выключена (голосовые всё равно сохраняются)."

# ── 4. Автозагрузка: launchd-агенты (бот + дашборд) ────────────────────────
say "Прописываю бота и дашборд в автозагрузку…"
BOT_CMD="export TELEGRAM_BOT_TOKEN=\"\$(security find-generic-password -s $KEYCHAIN_SVC -w)\"; cd '$ROOT'; exec '$ROOT/.venv/bin/python' .hermes/scripts/hermes_cli.py bot --setup"
cat > "$BOT_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.hermes-megamap.bot</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>-c</string>
    <string>$BOT_CMD</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG_DIR/bot.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/bot.log</string>
</dict></plist>
PLIST
cat > "$UI_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.hermes-megamap.ui</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>-c</string>
    <string>cd '$ROOT'; exec '$ROOT/.venv/bin/python' .hermes/scripts/hermes_cli.py ui</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG_DIR/ui.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/ui.log</string>
</dict></plist>
PLIST
launchctl load -w "$BOT_PLIST"
launchctl load -w "$UI_PLIST"

# ── 5. Проверка ────────────────────────────────────────────────────────────
sleep 4
echo
if pgrep -f "hermes_cli.py bot" >/dev/null; then
  if tail -n 20 "$LOG_DIR/bot.log" 2>/dev/null | grep -q "409"; then
    warn "Бот запущен, но токен занят кем-то ещё (HTTP 409)."
    warn "Если через минуту 409 не пройдёт: в @BotFather → /revoke → новый токен,"
    warn "затем снова: bash .hermes/scripts/setup_mac.sh (он спросит новый токен)."
  else
    say "Бот работает: $(tail -n 20 "$LOG_DIR/bot.log" 2>/dev/null | grep -m1 'Бот @' || echo ok)"
  fi
else
  warn "Бот не поднялся — смотрите: tail -n 20 $LOG_DIR/bot.log"
fi
if pgrep -f "hermes_cli.py ui" >/dev/null; then
  say "Дашборд работает: http://127.0.0.1:8137"
  open "http://127.0.0.1:8137" 2>/dev/null || true
else
  warn "Дашборд не поднялся — смотрите: tail -n 20 $LOG_DIR/ui.log"
fi
echo
say "Готово. Бот и дашборд теперь стартуют сами при входе в macOS."
say "Проверка:  bash .hermes/scripts/setup_mac.sh status"
say "Остановка: bash .hermes/scripts/setup_mac.sh stop"
