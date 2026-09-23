#!/usr/bin/env bash
# Сквозной тест харнеса на синтетических данных (вымышленные «Иван» и «Пётр»).
# Реальные материалы дела тест не трогает: работает во временной папке.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
S="$HERE/../scripts"
export CHURCH_CASE_PRIVATE="$(mktemp -d)"
trap 'rm -rf "$CHURCH_CASE_PRIVATE"' EXIT
T="$CHURCH_CASE_PRIVATE/in"; mkdir -p "$T/export"
cp "$HERE/fixtures/chat_ios.txt" "$T/export/_chat.txt"
printf 'FAKEOPUS' > "$T/export/00000003-AUDIO-2023-03-12-14-07-40.opus"
(cd "$T" && python3 -m zipfile -c export.zip export/_chat.txt export/00000003-AUDIO-2023-03-12-14-07-40.opus)
fail() { echo "TEST FAIL: $*"; exit 1; }

echo "== ingest"
python3 "$S/ingest_whatsapp.py" "$T/export.zip"
W="$CHURCH_CASE_PRIVATE/work"
[ "$(wc -l < "$W/messages.jsonl")" -eq 5 ] || fail "ожидалось 5 сообщений"
grep -q 'критиковать' "$W/messages.jsonl" || fail "многострочное сообщение потеряно"
grep -q '"attachment_sha256": "[0-9a-f]\{64\}"' "$W/messages.jsonl" || fail "вложение не связано с sha256"
AUD=$(python3 -c "import json;m=json.load(open('$W/manifest.json'));print([h for h,e in m.items() if e['kind']=='audio'][0])")

echo "== transcribe (поддельный mlx_whisper вместо модели)"
FAKE="$CHURCH_CASE_PRIVATE/fake"; mkdir -p "$FAKE"
cat > "$FAKE/mlx_whisper.py" <<'P'
def transcribe(path, **kw):
    return {"language": "ru", "segments": [{"start": 0.0, "end": 5.0, "text": " Это недоросли, а не власть."}]}
P
PYTHONPATH="$FAKE" python3 "$S/transcribe.py" --backend mlx
[ -f "$W/transcripts/$AUD.json" ] || fail "расшифровка не записана под sha256 оригинала"
PYTHONPATH="$FAKE" python3 "$S/transcribe.py" | grep -q "к расшифровке: 0" || fail "повторный запуск не идемпотентен"

echo "== find_materials"
MAC="$(mktemp -d)"; trap 'rm -rf "$CHURCH_CASE_PRIVATE" "$MAC"' EXIT
mkdir -p "$MAC/Документы/Досье Тестов" && echo x > "$MAC/Документы/Досье Тестов/устав.pdf"
python3 "$S/find_materials.py" --term "тестов" --root "$MAC"
grep -q "folder" "$W/found.csv" || fail "поиск не нашёл папку"

echo "== scan"
python3 "$S/scan_candidates.py" --author Иван
grep -q '"insult"' "$W/candidates.jsonl" || fail "сканер не нашёл insult"
grep -q '"divine_authority"' "$W/candidates.jsonl" || fail "сканер не нашёл divine_authority"
grep -q '"kind": "audio"' "$W/candidates.jsonl" || fail "сканер пропустил аудио"
if grep -q '"author": "Пётр"' "$W/candidates.jsonl"; then fail "фильтр по автору не сработал"; fi

E="$CHURCH_CASE_PRIVATE/episodes"; mkdir -p "$E"
ep() { cat > "$E/$1.json"; }
# Хороший эпизод-цитата
ep E-001 <<J
{"id":"E-001","date":"2023-03-12","summary":"Ответчик в переписке назвал членов совета и призвал на них Божье наказание.",
 "category":"divine_authority","role":"charge","statement_type":"quote",
 "sources":[{"sha256_or_url":"$AUD","locator":"msg:2","level":"B","quote_verbatim":"Они воры, украли организацию. Бог их накажет."}],
 "canonical_basis":["Еф 4:29","Втор 18:20"],"opinion":"Расцениваю как присвоение Божьего суда.",
 "verification":{"status":"verified_primary"},
 "defense":{"rebuttal":"Эмоциональная реплика в частной переписке, не проповедь.","assessment":"weakens","reply":"Сказано в статусе епископа."}}
J
ep E-002 <<J
{"id":"E-002","date":"2023-03-13","summary":"Ответчик: всякая власть от Бога.","category":"authority_claim","role":"context","statement_type":"quote",
 "sources":[{"sha256_or_url":"$AUD","locator":"msg:4","level":"B","quote_verbatim":"Всякая власть от Бога, критиковать её нельзя."}],
 "canonical_basis":["Рим 13:1"],"verification":{"status":"verified_primary"},"legal_risk_reviewed":true,
 "defense":{"rebuttal":"Цитата Писания.","assessment":"holds"}}
J
ep E-003 <<J
{"id":"E-003","date":"2023-03-14","summary":"Ответчик об иной власти: не от Бога.","category":"double_standard","role":"charge","statement_type":"quote",
 "linked_episodes":["E-002"],
 "sources":[{"sha256_or_url":"$AUD","locator":"msg:5","level":"B","quote_verbatim":"Эта власть не от Бога."}],
 "canonical_basis":["Мф 7:1-5"],"verification":{"status":"verified_primary"},"legal_risk_reviewed":true,
 "defense":{"rebuttal":"Разные контексты.","assessment":"holds"}}
J
echo "== check (ожидается чисто)"
python3 "$S/check_case.py" || fail "валидный набор не прошёл"

echo "== check ловит выдуманную цитату, непереслушанное аудио, уголовное по СМИ, политику без ревью"
ep E-004 <<J
{"id":"E-004","date":"2023-03-12","summary":"Ответчик назвал власть недорослями.","category":"insult","role":"charge","statement_type":"quote",
 "sources":[{"sha256_or_url":"$AUD","locator":"audio:$AUD@1.0","level":"B","quote_verbatim":"Это недоросли, а не власть."},
            {"sha256_or_url":"$AUD","locator":"msg:2","level":"B","quote_verbatim":"Они все мошенники и бандиты"}],
 "canonical_basis":["Еф 4:29"],"verification":{"status":"verified_primary"},
 "defense":{"rebuttal":"—","assessment":"holds"}}
J
ep E-005 <<J
{"id":"E-005","date":"2019-01-01","summary":"Осуждён за вождение в нетрезвом виде.","category":"criminal_record","role":"charge","statement_type":"fact",
 "sources":[{"sha256_or_url":"https://example.org/news","locator":"статья","level":"D"}],
 "canonical_basis":["1 Тим 3:3"],"verification":{"status":"verified_secondary"},
 "defense":{"rebuttal":"","assessment":"pending"}}
J
OUT=$(python3 "$S/check_case.py" || true)
echo "$OUT" | tail -12
for pat in "цитата не найдена" "не переслушана" "только verified_primary" "legal_risk_reviewed" \
           "нет довода защиты" "defense.assessment=pending" "≥2 независимых"; do
  echo "$OUT" | grep -q "$pat" || fail "валидатор не поймал: $pat"
done
rm "$E/E-004.json" "$E/E-005.json"

echo "== черновик: ярлык вне цитаты и битая ссылка"
mkdir -p "$CHURCH_CASE_PRIVATE/drafts"
cat > "$CHURCH_CASE_PRIVATE/drafts/predstavlenie.md" <<'D'
Ответчик написал: «Они воры, украли организацию» [E-001].
Очевидно, он лицемер [E-003]. См. также [E-099].
D
OUT=$(python3 "$S/check_case.py" --strict || true)
echo "$OUT" | grep -q "\[E-099\]" || fail "не поймана битая ссылка"
echo "$OUT" | grep -q "«лицемер»" || fail "не пойман ярлык вне цитаты"
if echo "$OUT" | grep -q "«воры»"; then fail "ярлык внутри цитаты ложно помечен"; fi
echo "$OUT" | grep -q "«Очевидно»" || fail "не поймана категоричность"

echo "== dossier"
python3 "$S/build_dossier.py"
grep -q "Возможное возражение" "$CHURCH_CASE_PRIVATE/drafts/prilozhenie_epizody.md" || fail "нет доводов защиты в приложении"
echo "ВСЕ ТЕСТЫ ПРОЙДЕНЫ"
