#!/usr/bin/env bash
# Клонирует (или обновляет) три репозитория в $STACK_DIR/repos.
# Клоны живут ВНЕ git-репозитория офиса и в него не коммитятся.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

clone_or_update() {
  local url="$1" ref="$2" dir="$3" name; name="$(basename "$dir")"
  if [ -d "$dir/.git" ]; then
    log "$name: обновляю ($ref)"
    git -C "$dir" fetch --depth 1 origin "$ref"
    git -C "$dir" checkout -q FETCH_HEAD
  else
    log "$name: клонирую $url ($ref)"
    git clone --depth 1 --branch "$ref" "$url" "$dir" 2>/dev/null \
      || git clone --depth 1 "$url" "$dir"   # ref может быть коммитом, не веткой
  fi
  ok "$name @ $(git -C "$dir" rev-parse --short HEAD)"
}

mkdir -p "$REPOS_DIR"
clone_or_update "$OPENMONTAGE_REPO" "$OPENMONTAGE_REF" "$OM_DIR"
clone_or_update "$OMNIROUTE_REPO"   "$OMNIROUTE_REF"   "$OR_DIR"
clone_or_update "$HERDR_REPO"       "$HERDR_REF"       "$HD_DIR"

log "Размеры:"; du -sh "$REPOS_DIR"/* 2>/dev/null || true
ok "Клонирование завершено → $REPOS_DIR"
