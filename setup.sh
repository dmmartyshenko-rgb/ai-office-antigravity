#!/bin/bash
# =============================================================
# MiMo Code Bot — Vercel setup script
# Usage: bash setup.sh
# Requires: curl, jq
# =============================================================
set -e

VERCEL_TOKEN="${VERCEL_TOKEN:-}"
TELEGRAM_TOKEN="${TELEGRAM_TOKEN:-}"
OPENROUTER_KEY="${OPENROUTER_KEY:-}"

# ---- prompt if not set via env ----
if [ -z "$VERCEL_TOKEN" ]; then
  read -rsp "Vercel API token: " VERCEL_TOKEN; echo
fi
if [ -z "$TELEGRAM_TOKEN" ]; then
  read -rsp "Telegram Bot token: " TELEGRAM_TOKEN; echo
fi
if [ -z "$OPENROUTER_KEY" ]; then
  read -rsp "OpenRouter API key: " OPENROUTER_KEY; echo
fi

REPO="dmmartyshenko-rgb/ai-office-antigravity"
PROJECT_NAME="ai-office-antigravity"
BRANCH="claude/xiaomi-code-install-9uxwre"

echo
echo "[1/4] Creating Vercel project..."

CREATE_RESP=$(curl -sf -X POST https://api.vercel.com/v10/projects \
  -H "Authorization: Bearer $VERCEL_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"$PROJECT_NAME\",
    \"gitRepository\": {
      \"type\": \"github\",
      \"repo\": \"$REPO\"
    },
    \"framework\": null
  }")

PROJECT_ID=$(echo "$CREATE_RESP" | jq -r '.id // empty')

if [ -z "$PROJECT_ID" ]; then
  # project may already exist — fetch it
  echo "  Project exists or error, fetching..."
  PROJECT_ID=$(curl -sf "https://api.vercel.com/v9/projects/$PROJECT_NAME" \
    -H "Authorization: Bearer $VERCEL_TOKEN" | jq -r '.id')
fi

echo "  Project ID: $PROJECT_ID"

echo "[2/4] Setting environment variables..."

for ENV_ENTRY in \
  "TELEGRAM_BOT_TOKEN|$TELEGRAM_TOKEN" \
  "OPENROUTER_API_KEY|$OPENROUTER_KEY"
do
  KEY="${ENV_ENTRY%%|*}"
  VAL="${ENV_ENTRY##*|}"
  curl -sf -X POST "https://api.vercel.com/v10/projects/$PROJECT_ID/env" \
    -H "Authorization: Bearer $VERCEL_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"key\":\"$KEY\",\"value\":\"$VAL\",\"type\":\"encrypted\",\"target\":[\"production\",\"preview\"]}" \
    > /dev/null && echo "  Set $KEY"
done

echo "[3/4] Triggering deployment..."

DEPLOY_RESP=$(curl -sf -X POST https://api.vercel.com/v13/deployments \
  -H "Authorization: Bearer $VERCEL_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"$PROJECT_NAME\",
    \"gitSource\": {
      \"type\": \"github\",
      \"repoId\": \"$REPO\",
      \"ref\": \"$BRANCH\"
    },
    \"projectId\": \"$PROJECT_ID\",
    \"target\": \"production\"
  }")

DEPLOY_URL=$(echo "$DEPLOY_RESP" | jq -r '.url // empty')
DEPLOY_ID=$(echo "$DEPLOY_RESP" | jq -r '.id // empty')

if [ -z "$DEPLOY_URL" ]; then
  echo "  Could not get deploy URL from API response."
  echo "  Check https://vercel.com/dashboard manually."
else
  echo "  Deploy URL: https://$DEPLOY_URL"
fi

echo "[4/4] Waiting for deployment to finish..."
for i in $(seq 1 24); do
  sleep 5
  STATE=$(curl -sf "https://api.vercel.com/v13/deployments/$DEPLOY_ID" \
    -H "Authorization: Bearer $VERCEL_TOKEN" | jq -r '.readyState // .state')
  echo "  State: $STATE"
  if [ "$STATE" = "READY" ]; then break; fi
  if [ "$STATE" = "ERROR" ] || [ "$STATE" = "CANCELED" ]; then
    echo "  Deployment failed. Check Vercel dashboard."
    exit 1
  fi
done

echo
echo "[OK] Setting Telegram webhook..."
WEBHOOK_URL="https://$DEPLOY_URL/api/webhook"
WH_RESP=$(curl -sf "https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook?url=${WEBHOOK_URL}")
echo "  $WH_RESP"

echo
echo "================================================"
echo " Done! Bot is live:"
echo " https://$DEPLOY_URL"
echo " Webhook: $WEBHOOK_URL"
echo "================================================"
