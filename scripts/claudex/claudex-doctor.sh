#!/usr/bin/env bash
# claudex-doctor.sh — проверка готовности связки Claude Code <-> Codex.
# Ничего не запускает и не тратит квоту моделей: только диагностика окружения.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
# shellcheck source=/dev/null
. "$HERE/claudex.config.sh"

ok=0; warn=0; fail=0
green() { printf '  \033[32mOK\033[0m   %s\n' "$1"; ok=$((ok+1)); }
yellow(){ printf '  \033[33mWARN\033[0m %s\n' "$1"; warn=$((warn+1)); }
red()   { printf '  \033[31mFAIL\033[0m %s\n' "$1"; fail=$((fail+1)); }

echo "Claudex Loop — проверка окружения"
echo "repo: $REPO_ROOT"
echo

echo "[1] Python (нужен 3.10+, рантайм без pip-пакетов):"
if command -v python3 >/dev/null 2>&1; then
  pv="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
  if python3 -c 'import sys;raise SystemExit(0 if sys.version_info[:2]>=(3,10) else 1)'; then
    green "python3 $pv"
  else
    red "python3 $pv — требуется 3.10+"
  fi
else
  red "python3 не найден"
fi

echo "[2] CLI провайдеров (оба нужны для полной перекрёстной связки):"
if command -v "$CLAUDEX_CLAUDE_BIN" >/dev/null 2>&1; then
  green "claude: $("$CLAUDEX_CLAUDE_BIN" --version 2>&1 | head -1)"
else
  red "claude ($CLAUDEX_CLAUDE_BIN) не найден — установи Claude Code"
fi
if command -v "$CLAUDEX_CODEX_BIN" >/dev/null 2>&1; then
  green "codex: $("$CLAUDEX_CODEX_BIN" --version 2>&1 | head -1)"
else
  yellow "codex ($CLAUDEX_CODEX_BIN) не найден — перекрёстная половина (ревью/сборка Codex) работать не будет, пока не установишь и не залогинишь Codex CLI"
fi

echo "[3] Установленные skills:"
for s in claudex-loop claudex-route codex-build codex-review; do
  if [ -f "$REPO_ROOT/.claude/skills/$s/SKILL.md" ]; then
    green ".claude/skills/$s"
  else
    red ".claude/skills/$s отсутствует"
  fi
done

echo "[4] Адаптер runner.py:"
RUNNER="$REPO_ROOT/.claude/skills/claudex-loop/scripts/runner.py"
if [ -f "$RUNNER" ] && python3 "$RUNNER" --help >/dev/null 2>&1; then
  green "runner.py импортируется и отвечает на --help"
else
  red "runner.py не найден или не запускается: $RUNNER"
fi

echo
echo "Итог: OK=$ok  WARN=$warn  FAIL=$fail"
if [ "$fail" -gt 0 ]; then
  echo "Есть блокеры — связка неполная. См. FAIL выше."
  exit 1
fi
if [ "$warn" -gt 0 ]; then
  echo "Связка на стороне Claude готова; для перекрёстных прогонов доустанови/залогинь Codex."
fi
