#!/usr/bin/env bash
# Acceptance checks for the Telegram bridge. Run on the server as root.
set -uo pipefail

DOMAIN=v2202609416472518907.goodsrv.de
BASE="https://$DOMAIN"
TOKEN=$(grep '^TG_BRIDGE_TOKEN=' /opt/tg-bridge/.env | cut -d= -f2)
PASS=0; FAIL=0

check() {  # check <name> <condition-result (0/1)> <detail>
    if [ "$2" -eq 0 ]; then echo "PASS: $1"; PASS=$((PASS+1));
    else echo "FAIL: $1 — $3"; FAIL=$((FAIL+1)); fi
}

echo "== 1. /health -> authorized:true"
H=$(curl -sS -H "Authorization: Bearer $TOKEN" "$BASE/health")
echo "$H" | grep -q '"authorized":true'; check "/health authorized:true" $? "$H"

echo "== 2. /dialogs?limit=5 returns real dialogs"
D=$(curl -sS -H "Authorization: Bearer $TOKEN" "$BASE/dialogs?limit=5")
echo "$D" | grep -q '"id":'; check "/dialogs has entries" $? "$D"

echo "== 3. /send to Saved Messages"
S=$(curl -sS -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"peer":"me","text":"tg-bridge acceptance test"}' "$BASE/send")
echo "$S" | grep -q '"id":'; check "/send to Saved Messages" $? "$S"

echo "== 4. No token -> 401 on every endpoint"
ALL401=0
for EP in "/health" "/dialogs" ; do
    CODE=$(curl -sS -o /dev/null -w '%{http_code}' "$BASE$EP")
    [ "$CODE" = "401" ] || ALL401=1
done
CODE=$(curl -sS -o /dev/null -w '%{http_code}' -X POST -H "Content-Type: application/json" -d '{}' "$BASE/send")
[ "$CODE" = "401" ] || ALL401=1
check "401 without token" $ALL401 "got non-401"

echo "== 5. Only 22/80/443 open on the host firewall"
UFW=$(ufw status | grep ALLOW | grep -vE '(^| )(22|80|443)/tcp' | grep -v '(v6)')
[ -z "$UFW" ]; check "ufw: only 22/80/443" $? "$UFW"
echo "   (also verify the netcup cloud firewall in the customer panel)"

echo
echo "Result: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
