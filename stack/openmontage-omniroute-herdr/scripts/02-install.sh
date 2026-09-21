#!/usr/bin/env bash
# Ставит зависимости и окружения всех трёх компонентов.
#   - OpenMontage: python venv + requirements + remotion-composer (make setup)
#   - OmniRoute:   npm i -g omniroute  (или сборка из клона при OMNIROUTE_INSTALL=source)
#   - Herdr:       официальный install.sh (или cargo build при HERDR_INSTALL=cargo)
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# ---------------------------------------------------------------------------
install_openmontage() {
  log "OpenMontage: make setup (venv + requirements + remotion-composer)"
  [ -d "$OM_DIR" ] || die "нет клона OpenMontage — сначала 01-clone.sh"
  have python3 || die "нужен python3"
  ( cd "$OM_DIR" && make setup ) \
    && ok "OpenMontage установлен (.venv в $OM_DIR/.venv)" \
    || warn "OpenMontage: make setup завершился с ошибкой — см. вывод выше"
}

# ---------------------------------------------------------------------------
install_omniroute() {
  if [ "$OMNIROUTE_INSTALL" = "source" ]; then
    log "OmniRoute: установка из исходников (npm install + build)"
    [ -d "$OR_DIR" ] || die "нет клона OmniRoute — сначала 01-clone.sh"
    ( cd "$OR_DIR" && npm install && npm run build:fast ) \
      && ok "OmniRoute собран из исходников ($OR_DIR)" \
      || warn "OmniRoute: сборка из исходников не удалась"
  else
    log "OmniRoute: npm i -g omniroute"
    have npm || die "нужен npm (node >=22)"
    if npm i -g omniroute; then
      ok "OmniRoute установлен глобально: $(command -v omniroute || echo '?')"
    else
      warn "npm i -g omniroute не удался (реестр/права?). Попробуй OMNIROUTE_INSTALL=source."
    fi
  fi
}

# ---------------------------------------------------------------------------
install_herdr() {
  if have herdr; then ok "herdr уже установлен: $(herdr --version 2>/dev/null || echo ok)"; return; fi
  if [ "$HERDR_INSTALL" = "cargo" ]; then
    log "Herdr: cargo install из клона (долгая сборка Rust)"
    [ -d "$HD_DIR" ] || die "нет клона herdr — сначала 01-clone.sh"
    have cargo || die "нужен cargo (rust toolchain)"
    ( cd "$HD_DIR" && cargo install --path . --locked ) \
      && ok "herdr собран через cargo" \
      || warn "herdr: cargo install не удался"
  else
    log "Herdr: официальный установщик (herdr.dev/install.sh)"
    if curl -fsSL https://herdr.dev/install.sh | sh; then
      ok "herdr установлен через install.sh"
    else
      warn "install.sh недоступен (egress?). Поставь бинарь вручную или задай HERDR_INSTALL=cargo."
    fi
  fi
}

case "${1:-all}" in
  openmontage|om) install_openmontage ;;
  omniroute|or)   install_omniroute ;;
  herdr|hd)       install_herdr ;;
  all)            install_openmontage; install_omniroute; install_herdr ;;
  *) die "usage: 02-install.sh [all|openmontage|omniroute|herdr]" ;;
esac
ok "Установка ($1) завершена"
