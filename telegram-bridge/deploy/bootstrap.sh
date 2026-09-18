#!/usr/bin/env bash
# One-shot bootstrap for the netcup web console (SCP -> Console).
# Run as root. It clones the repo, installs the bridge, logs into Telegram
# interactively, verifies acceptance, and prints BASE_URL + TOKEN.
#
#   curl -fsSL https://raw.githubusercontent.com/dmmartyshenko-rgb/ai-office-antigravity/claude/telegram-bridge-netcup-mtlo1x/telegram-bridge/deploy/bootstrap.sh -o /root/tgb.sh
#   bash /root/tgb.sh
#
# (Two lines, not a pipe: `read`/login prompts need the keyboard, which a
#  `curl | bash` pipe would swallow.)
set -euo pipefail

REPO_URL=https://github.com/dmmartyshenko-rgb/ai-office-antigravity.git
BRANCH=claude/telegram-bridge-netcup-mtlo1x
CHECKOUT=/root/ai-office-antigravity
APP_DIR=/opt/tg-bridge
DOMAIN=v2202609416472518907.goodsrv.de

if [ "$(id -u)" != "0" ]; then
    echo "Run this as root (you are in the netcup console, so you already are)."
    exit 1
fi

echo "############################################################"
echo "# Telegram bridge — full deploy"
echo "# You will be asked for THREE things, in order:"
echo "#   1) api_hash  — from https://my.telegram.org (API development tools)"
echo "#   2) your phone number + the login code Telegram sends you"
echo "#   3) your 2FA password (leave empty if you have none)"
echo "# Nothing else. Grab the api_hash now, keep your phone handy."
echo "############################################################"
echo

command -v git >/dev/null || { apt-get update -qq && apt-get install -y -qq git; }

echo "==> Fetching repo ($BRANCH)"
if [ -d "$CHECKOUT/.git" ]; then
    git -C "$CHECKOUT" fetch --quiet origin "$BRANCH"
    git -C "$CHECKOUT" checkout --quiet "$BRANCH"
    git -C "$CHECKOUT" reset --hard --quiet "origin/$BRANCH"
else
    rm -rf "$CHECKOUT"
    git clone --quiet --branch "$BRANCH" "$REPO_URL" "$CHECKOUT"
fi

echo "==> Running installer (will ask for api_hash)"
bash "$CHECKOUT/telegram-bridge/deploy/install.sh"

echo
echo "==> Telegram login (asks for phone, code, and 2FA)"
if [ -s "$APP_DIR/session.txt" ]; then
    echo "    session.txt already present — skipping login. Delete it to redo."
else
    sudo -u tgbridge TG_BRIDGE_ENV="$APP_DIR/.env" "$APP_DIR/venv/bin/python" "$APP_DIR/login.py"
fi

echo "==> Restarting service"
systemctl restart tg-bridge
sleep 3

echo "==> Acceptance checks"
set +e
bash "$CHECKOUT/telegram-bridge/deploy/check_acceptance.sh"
RC=$?
set -e

TOKEN=$(grep '^TG_BRIDGE_TOKEN=' "$APP_DIR/.env" | cut -d= -f2)
echo
echo "============================================================"
if [ "$RC" -eq 0 ]; then
    echo "ALL ACCEPTANCE CHECKS PASSED."
else
    echo "SOME CHECKS FAILED (code $RC). If it is only TLS (cert still"
    echo "issuing), wait ~60s and re-run:  bash $CHECKOUT/telegram-bridge/deploy/check_acceptance.sh"
fi
echo
echo "Copy these two lines back to the owner:"
echo
echo "BASE_URL=https://$DOMAIN"
echo "TOKEN=$TOKEN"
echo "============================================================"
