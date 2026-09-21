#!/usr/bin/env bash
# Связывает OpenMontage с роутером на уровне Claude Code и проверяет готовность.
# OpenMontage управляется Claude Code (см. его AGENT_GUIDE.md); LLM-трафик Claude
# Code идёт через OmniRoute, а медиа-провайдеры (FLUX/Veo/TTS...) — из .env самого
# OpenMontage. Это две независимые плоскости, и мы настраиваем обе.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

[ -d "$OM_DIR" ] || die "нет клона OpenMontage — сначала 01-clone.sh"

# --- 1. .env OpenMontage (медиа-ключи) ---
if [ ! -f "$OM_DIR/.env" ]; then
  cp "$OM_DIR/.env.example" "$OM_DIR/.env"
  ok "создан $OM_DIR/.env из примера — впиши туда ключи медиа-провайдеров"
else
  ok "$OM_DIR/.env уже есть"
fi

# --- 2. Рендер env Claude Code → роутер (в STACK_DIR, не в git) ---
CC_ENV="$STACK_DIR/openmontage.claude.env"
cat > "$CC_ENV" <<EOF
# Автоген $(date -u +%FT%TZ) — связка Claude Code → OmniRoute для OpenMontage.
export ANTHROPIC_BASE_URL="$OMNIROUTE_BASE_URL"
export ANTHROPIC_AUTH_TOKEN="${OMNIROUTE_API_KEY:-omniroute}"
export ANTHROPIC_MODEL="$OM_MODEL"
export ANTHROPIC_SMALL_FAST_MODEL="$OM_MODEL"
EOF
ok "env Claude Code → роутер: $CC_ENV"

# --- 3. Постоянный профиль Claude Code через OmniRoute (best-effort) ---
if have omniroute; then
  log "omniroute setup-claude (профиль Claude Code, направленный на роутер)"
  omniroute setup-claude --port "$OMNIROUTE_PORT" ${OMNIROUTE_API_KEY:+--api-key "$OMNIROUTE_API_KEY"} \
    && ok "профиль Claude Code записан (см. ~/.claude/profiles/)" \
    || warn "setup-claude не выполнен — используется runtime-способ (omniroute run claude)"
fi

# --- 4. Проверка достижимости роутера ---
if http_ok "$OMNIROUTE_BASE_URL"; then
  ok "роутер отвечает на $OMNIROUTE_BASE_URL"
else
  warn "роутер не отвечает — сначала запусти 03-omniroute-up.sh"
fi

echo
ok "Связка готова. Запуск сессии: scripts/start-openmontage-session.sh"
