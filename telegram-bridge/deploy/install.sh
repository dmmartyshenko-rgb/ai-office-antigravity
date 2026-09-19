#!/usr/bin/env bash
# One-shot installer for the Telegram bridge on Debian 12/13.
# Run as root from the repo checkout:  sudo bash telegram-bridge/deploy/install.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR=/opt/tg-bridge
DOMAIN=v2202609416472518907.goodsrv.de

echo "==> Installing packages (python3-venv, caddy, ufw)"
apt-get update -qq
apt-get install -y -qq python3 python3-venv curl ufw debian-keyring debian-archive-keyring apt-transport-https gnupg

if ! command -v caddy >/dev/null; then
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq && apt-get install -y -qq caddy
fi

echo "==> Creating unprivileged user tgbridge"
id tgbridge &>/dev/null || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin tgbridge

echo "==> Deploying app to $APP_DIR"
mkdir -p "$APP_DIR"
cp -r "$REPO_DIR/app" "$REPO_DIR/login.py" "$REPO_DIR/requirements.txt" "$APP_DIR/"

if [ ! -d "$APP_DIR/venv" ]; then
    python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

echo "==> Writing .env (kept out of git, chmod 600)"
if [ ! -f "$APP_DIR/.env" ]; then
    TOKEN=$(openssl rand -hex 32)
    read -rp "Telegram api_hash (from https://my.telegram.org): " API_HASH
    cat > "$APP_DIR/.env" <<EOF
TG_API_ID=32490345
TG_API_HASH=$API_HASH
TG_BRIDGE_TOKEN=$TOKEN
TG_SESSION_FILE=$APP_DIR/session.txt
TG_AUDIT_LOG=$APP_DIR/audit.log
TG_LISTEN_HOST=127.0.0.1
TG_LISTEN_PORT=8080
TG_SEND_RATE_LIMIT=20
TG_SEND_RATE_WINDOW=60
EOF
else
    TOKEN=$(grep '^TG_BRIDGE_TOKEN=' "$APP_DIR/.env" | cut -d= -f2)
    echo "    .env already exists — keeping it."
fi
chmod 600 "$APP_DIR/.env"
touch "$APP_DIR/audit.log"
chown -R tgbridge:tgbridge "$APP_DIR"

echo "==> Installing systemd unit"
cp "$REPO_DIR/deploy/tg-bridge.service" /etc/systemd/system/tg-bridge.service
systemctl daemon-reload
systemctl enable tg-bridge

echo "==> Configuring Caddy for $DOMAIN"
# Install our Caddyfile ONLY on a fresh box (missing, or the stock Debian default).
# If the file was customised on the server (e.g. a ZeroSSL issuer / port-80 ACME
# workaround for the shared goodsrv.de rate limit), keep it — never clobber a
# working TLS setup on a re-run.
if [ ! -f /etc/caddy/Caddyfile ] || grep -q "easy way to configure" /etc/caddy/Caddyfile; then
    cp "$REPO_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
else
    cp -n /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bootstrap-bak 2>/dev/null || true
    echo "    Existing custom /etc/caddy/Caddyfile kept (backup: .bootstrap-bak). Not overwriting."
fi
mkdir -p /var/log/caddy && chown caddy:caddy /var/log/caddy
systemctl enable caddy
systemctl restart caddy

echo "==> Firewall: allow only 22 (SSH) and 443 (API); Caddy gets TLS via 443 (ALPN)"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 443/tcp
ufw --force enable
echo "    NOTE: also check the netcup cloud firewall in the customer panel —"
echo "    only 22 and 443 inbound should be open there as well."

echo "==> Starting service (will report authorized:false until login)"
systemctl restart tg-bridge

cat <<EOF

============================================================
Install done. Next steps:

1) Log in to Telegram ONCE (interactive; asks for the code and 2FA):
     sudo -u tgbridge TG_BRIDGE_ENV=$APP_DIR/.env $APP_DIR/venv/bin/python $APP_DIR/login.py
     sudo systemctl restart tg-bridge

2) Verify acceptance:
     sudo bash $REPO_DIR/deploy/check_acceptance.sh

Base URL:      https://$DOMAIN
Bearer token:  $TOKEN
(also stored in $APP_DIR/.env)
============================================================
EOF
