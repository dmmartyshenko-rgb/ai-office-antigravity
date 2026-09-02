#!/usr/bin/env python3
"""Hermes Megamap — веб-дашборд («Экспедиционная карта»).

Локальный сервер на стандартной библиотеке (без зависимостей), тонкая оболочка
над metabolism.py: все изменения идут через triage/consolidate/decay, инварианты
системы не обходятся. Слушает только 127.0.0.1.

Запуск: python3 .hermes/scripts/hermes_ui.py  (или: hermes_cli.py ui)

API:
  GET  /                  — приложение (карточки / радар / домен)
  GET  /api/state         — слой 1: домены, буфер, аудит, линт
  GET  /api/domain/<slug> — слои 2+3 домена
  POST /api/add-raw       — {"text": ...} → triage (source=ui)
  POST /api/consolidate   — пакетная обработка буфера
  POST /api/decay         — Decay & Audit
  POST /api/touch         — {"slug": ...} → зафиксировать контакт + consolidate
"""
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import metabolism as mb  # noqa: E402

ROOT = mb.find_root()


# ------------------------------------------------------------------ парсинг

def section_body(text: str, header: str) -> str:
    m = re.search(rf"^## {re.escape(header)}\s*\n(.*?)(?=^## |\Z)", text,
                  re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def parse_log(root: Path, log_rel: str) -> list:
    path = root / log_rel
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    entries = []
    for m in re.finditer(
            r"^### (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) — (.+?)\n(.*?)(?=^### |\Z)",
            text, re.MULTILINE | re.DOTALL):
        block = m.group(4)
        what = re.search(r"\*\*Что произошло/решено:\*\*\s*(.*)", block)
        why = re.search(r"\*\*Почему:\*\*\s*(.*)", block)
        entries.append({
            "date": m.group(1), "time": m.group(2), "title": m.group(3).strip(),
            "what": what.group(1).strip() if what else "",
            "why": why.group(1).strip() if why else "",
        })
    return entries


def _ring_for(circle: str) -> int:
    low = circle.lower()
    if "ближн" in low:
        return 1
    if "слаб" in low or "дальн" in low or "знаком" in low:
        return 3
    return 2


def _radar_pos(slug: str, ring: int, paused: bool) -> dict:
    """Детерминированная позиция узла на радаре (viewBox 860×860).
    Сектор 150°–195° зарезервирован под Пауза/Архив."""
    h = int(hashlib.sha256(slug.encode()).hexdigest()[:12], 16)
    import math
    if paused:
        ang = 154 + (h % 38)          # внутри сектора
        r = 140 + (h // 360 % 190)
    else:
        a = h % 315                    # 360° минус сектор (45°)
        ang = a if a < 148 else a + 47
        bands = {1: (55, 40), 2: (125, 100), 3: (245, 110)}
        base, spread = bands[ring]
        r = base + (h // 360 % spread)
    rad = math.radians(ang)
    return {"x": round(430 + r * math.cos(rad), 1),
            "y": round(430 - r * math.sin(rad), 1), "ring": ring}


def run_lint() -> dict:
    lint = Path(__file__).resolve().parent / "lint_megamap.py"
    r = subprocess.run([sys.executable, str(lint)], capture_output=True,
                       text=True, cwd=ROOT)
    return {"ok": r.returncode == 0, "output": (r.stdout + r.stderr).strip()}


def get_state() -> dict:
    cfg = mb.load_config(ROOT)
    now = datetime.now()
    domains = []
    for slug, info in mb.parse_index(ROOT).items():
        map_path = ROOT / (info["map"] or "")
        text = map_path.read_text(encoding="utf-8") if map_path.is_file() else ""
        is_project = info["type"].lower().startswith("проект")
        last = mb.last_log_date(ROOT, info["log"]) if info["log"] else None
        days = (now - last).days if last else None
        status_l = info["status"].lower()
        d = {
            "slug": slug, "type": "project" if is_project else "relationship",
            "status": info["status"], "essence": info["essence"],
            "active": status_l.startswith("актив"),
            "paused": "пауза" in status_l or "архив" in status_l,
            "days": days,
            "name": re.sub(r"^#\s*", "", text.splitlines()[0]).strip() if text else slug,
        }
        if is_project:
            d["next_step"] = section_body(text, "Следующий шаг")
            d["blockers"] = section_body(text, "Риски и блокеры")
            limit = cfg["decay"]["project_pause_days"]
            d["vitality"] = max(0, round(100 * (1 - (days or 0) / limit))) if days is not None else None
        else:
            d["next_step"] = section_body(text, "Следующий социальный шаг")
            d["blockers"] = section_body(text, "Блокеры")
            d["circle"] = section_body(text, "Круг / Роль").split("·")[0].strip()
            score = max(0, 100 - (days or 0) * cfg["decay"]["health_decay_per_day"]) \
                if days is not None else None
            d["health"] = score
            rel_status = section_body(text, "Статус отношений")
            d["warm"] = "тепл" in rel_status.lower() or "тёпл" in rel_status.lower()
            d.update(_radar_pos(slug, _ring_for(d["circle"]), d["paused"]))
        domains.append(d)

    buffer = []
    for f in sorted((ROOT / "buffer").glob("*.md")):
        digest, body, source = mb._read_note(f)
        conn = mb.db_connect(ROOT)
        row = conn.execute("SELECT status, created_at FROM entries WHERE hash=?",
                           (digest,)).fetchone()
        conn.close()
        buffer.append({
            "file": f.name, "source": source, "hash": digest[:6],
            "status": row[0] if row else "pending",
            "created": row[1][:16].replace("T", " ") if row else "",
            "preview": body[:120],
        })

    conn = mb.db_connect(ROOT)
    edges = [{"src": r[0], "dst": r[1]} for r in
             conn.execute("SELECT DISTINCT src, dst FROM edges").fetchall()]
    last_audit = conn.execute(
        "SELECT ts, action, detail FROM audit_log ORDER BY id DESC LIMIT 5").fetchall()
    n_entries = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    n_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    conn.close()

    index_lines = len((ROOT / "INDEX.md").read_text(encoding="utf-8").splitlines()) \
        if (ROOT / "INDEX.md").is_file() else 0
    return {
        "domains": domains, "buffer": buffer, "edges": edges,
        "audit": [{"ts": a[0][:16].replace("T", " "), "action": a[1],
                   "detail": a[2]} for a in last_audit],
        "db": {"entries": n_entries, "edges": n_edges},
        "index_lines": index_lines, "lint": run_lint(),
        "config": {"health_pause_score": cfg["decay"]["health_pause_score"],
                   "contact_pause_days": cfg["decay"]["contact_pause_days"],
                   "decay_per_day": cfg["decay"]["health_decay_per_day"]},
    }


def get_domain(slug: str) -> dict | None:
    info = mb.parse_index(ROOT).get(slug)
    if not info:
        return None
    text = (ROOT / info["map"]).read_text(encoding="utf-8")
    sections = {}
    for m in re.finditer(r"^## (.+?)\s*\n(.*?)(?=^## |\Z)", text,
                         re.MULTILINE | re.DOTALL):
        sections[m.group(1).strip()] = m.group(2).strip()
    return {"slug": slug, "type": info["type"], "status": info["status"],
            "map": info["map"], "log": info["log"],
            "name": re.sub(r"^#\s*", "", text.splitlines()[0]).strip(),
            "sections": sections, "entries": parse_log(ROOT, info["log"])}


# ------------------------------------------------------------------ HTTP

def _capture(fn, *args, **kw) -> str:
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args, **kw)
    return buf.getvalue().strip()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # тихий лог
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._json(get_state())
        elif self.path.startswith("/api/domain/"):
            d = get_domain(self.path.rsplit("/", 1)[1])
            self._json(d) if d else self._json({"error": "нет такого домена"}, 404)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "bad json"}, 400)
        if self.path == "/api/add-raw":
            out = _capture(mb.triage, payload.get("text", ""), ROOT, "ui")
            self._json({"output": out})
        elif self.path == "/api/consolidate":
            out = _capture(mb.consolidate, ROOT)
            self._json({"output": out})
        elif self.path == "/api/decay":
            out = _capture(mb.decay_and_audit, ROOT)
            self._json({"output": out})
        elif self.path == "/api/touch":
            slug = payload.get("slug", "")
            note = f"@{slug} ! Контакт зафиксирован\nПочему: поддержание связи."
            out = _capture(mb.triage, note, ROOT, "ui")
            out += "\n" + _capture(mb.consolidate, ROOT)
            self._json({"output": out.strip()})
        else:
            self._json({"error": "not found"}, 404)


def main() -> int:
    cfg = mb.load_config(ROOT).get("ui", {})
    host = cfg.get("host", "127.0.0.1")
    port = int(cfg.get("port", 8137))
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"Hermes Megamap UI: http://{host}:{port}  (хранилище: {ROOT})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nостановлен")
    return 0


# ------------------------------------------------------------------ страница

PAGE = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hermes Megamap</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=PT+Mono&family=PT+Serif:wght@400;700&family=Playfair+Display:wght@600;700&display=swap">
<style>
:root {
  --bg:#EBDDBB; --panel:#F5EDD8; --panel2:#F1E7CC; --card:#F9F2E0; --inner:#F1E7CC;
  --line:#B99B6B; --line2:#C4A87A; --line3:#D6C29A; --bronze:#8C5A2B;
  --ink:#33230F; --ink2:#4A3925; --sec:#6E573B; --mut:#99815D;
  --green:#3E6B3A; --ochre:#A9611C; --ochre2:#C9A46B; --red:#7A2E1D;
  --gray:#A79878; --track:#E2D3AE;
}
* { box-sizing: border-box; }
body { margin:0; font-family:'PT Serif',Georgia,serif; color:var(--ink);
  background-color:var(--bg);
  background-image:radial-gradient(ellipse at 50% 30%, #F2E7CC 0%, #EBDDBB 60%, #D9C69C 100%);
  min-height:100vh; }
a { color: var(--green); } a:hover { color:#2C5228; }
.mono { font-family:'PT Mono',monospace; }
.serif { font-family:'Playfair Display',Georgia,serif; }
button { font:inherit; cursor:pointer; border-radius:2px; }
.btn-dark { background:#4A2E14; color:#F5EAD2; border:1px solid #33200D;
  font-weight:700; padding:9px 18px; box-shadow:inset 0 1px 0 rgba(245,234,210,.25); }
.btn-ochre { background:transparent; color:var(--ochre); border:1.5px solid var(--ochre2);
  font-weight:700; padding:9px 18px; }
.btn-green { background:rgba(62,107,58,.08); color:var(--green);
  border:1.5px solid var(--green); font-weight:700; padding:9px 14px; width:100%; }
.stamp { display:inline-block; padding:3px 9px; border-radius:1px; font-size:10.5px;
  letter-spacing:1.5px; font-weight:700; border:1.5px solid; font-family:'PT Serif',serif; }
.card { background:var(--card); border:1px solid #A9885A; border-radius:2px;
  box-shadow: inset 0 0 0 1px rgba(169,136,90,.3), 0 1px 3px rgba(90,60,20,.15); }
.label { font-size:10.5px; color:var(--mut); letter-spacing:1.5px; font-weight:700; }
header { display:flex; align-items:center; gap:22px; padding:10px 28px; background:var(--panel);
  border-bottom:2px solid var(--line); box-shadow:0 1px 0 var(--bronze); flex-wrap:wrap; }
.vr { width:1px; height:34px; background:var(--line2); }
.count b { font-family:'PT Mono',monospace; font-size:20px; display:block; line-height:1.1; }
.lintchip { display:flex; align-items:center; gap:8px; padding:6px 14px;
  border:1.5px solid var(--green); background:rgba(62,107,58,.07);
  font-family:'PT Mono',monospace; font-size:12px; color:var(--green); letter-spacing:1px; }
.lintchip.bad { border-color:var(--red); background:rgba(122,46,29,.07); color:var(--red); }
.layout { display:flex; align-items:stretch; min-height:calc(100vh - 70px); }
aside { width:336px; flex-shrink:0; background:var(--panel2); border-right:2px solid var(--line);
  padding:20px; display:flex; flex-direction:column; gap:16px; }
main { flex-grow:1; padding:20px 28px; min-width:0; display:flex; flex-direction:column; gap:16px; }
textarea { width:100%; background:var(--card); border:1px solid var(--line2); border-radius:2px;
  padding:11px 12px; height:84px; font-family:'PT Mono',monospace; font-size:12px;
  line-height:1.6; color:var(--ink2); box-shadow:inset 0 1px 2px rgba(90,60,20,.1); resize:vertical; }
.bufitem { background:var(--card); border:1px solid var(--line2); border-radius:2px;
  padding:10px 12px; display:flex; flex-direction:column; gap:5px;
  box-shadow:0 1px 2px rgba(90,60,20,.12); font-size:12.5px; }
.seg { display:flex; gap:2px; background:var(--panel); border:1px solid var(--line);
  border-radius:2px; padding:3px; }
.seg button { border:none; background:none; color:var(--sec); font-size:12.5px; padding:6px 15px; }
.seg button.on { background:#E4D4AC; color:var(--ink); font-weight:700;
  box-shadow:inset 0 0 0 1px var(--line2); border-radius:1px; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:14px; }
.dcard { padding:16px 18px; display:flex; flex-direction:column; gap:11px; cursor:pointer; }
.dcard:hover { box-shadow: inset 0 0 0 1px rgba(140,90,43,.55), 0 2px 5px rgba(90,60,20,.25); }
.track { height:4px; background:var(--track); border-radius:1px; overflow:hidden; }
.nextbox { background:var(--inner); border:1px solid var(--line3); border-radius:2px;
  padding:10px 12px; display:flex; gap:9px; align-items:flex-start; font-size:12.5px; line-height:1.5; }
.footer { display:flex; align-items:center; gap:18px; padding:10px 16px; background:var(--panel);
  border:1px solid var(--line); border-radius:2px; font-family:'PT Mono',monospace;
  font-size:11px; color:var(--mut); flex-wrap:wrap; }
.toast { position:fixed; bottom:18px; right:18px; max-width:440px; background:#4A2E14;
  color:#F5EAD2; padding:12px 16px; border-radius:2px; font-family:'PT Mono',monospace;
  font-size:11.5px; white-space:pre-wrap; display:none; z-index:50;
  box-shadow:0 3px 10px rgba(40,25,10,.4); }
.sect-title { font-family:'Playfair Display',Georgia,serif; font-size:15px; font-weight:700; }
.timeline-dot { width:10px; height:10px; border-radius:50%; margin-top:5px; flex-shrink:0; }
.hidden { display:none !important; }
h1.red { font-family:'Playfair Display',Georgia,serif; color:var(--red); margin:0; }
@media (max-width: 1000px) { aside { display:none; } }
</style>
</head>
<body>
<header>
  <div style="display:flex; align-items:center; gap:12px;">
    <svg width="30" height="30" viewBox="0 0 30 30" fill="none" stroke="#8C5A2B" stroke-width="1.4"><circle cx="15" cy="15" r="12.5"/><circle cx="15" cy="15" r="2.2" fill="#8C5A2B"/><path d="M15 3.5L17 13l-2 2-2-2z" fill="#7A2E1D" stroke="none"/><path d="M15 26.5L13 17l2-2 2 2z" fill="#8C5A2B" stroke="none"/><path d="M3.5 15H8M22 15h4.5M15 8V5.5M15 24.5V22" stroke-width="1"/></svg>
    <div>
      <h1 class="red" style="font-size:18px;">Hermes Megamap</h1>
      <div class="mono" style="font-size:9.5px; color:var(--mut); letter-spacing:2px;">АТЛАС ВНЕШНЕЙ ПАМЯТИ · СЛОЙ 1</div>
    </div>
  </div>
  <div class="vr"></div>
  <div class="count"><span class="label">ДОМЕНЫ</span><b id="c-domains">–</b></div>
  <div class="count"><span class="label">БУФЕР L0</span><b id="c-buffer" style="color:var(--ochre)">–</b></div>
  <div class="count"><span class="label">INDEX</span><b id="c-index">–</b></div>
  <div style="flex-grow:1"></div>
  <div class="lintchip" id="lint">LINT …</div>
  <button class="btn-dark" onclick="act('consolidate')">Consolidate</button>
  <button class="btn-ochre" onclick="act('decay')">Decay / Audit</button>
</header>

<div class="layout">
<aside>
  <div class="card" style="padding:14px 15px; display:flex; flex-direction:column; gap:10px;">
    <div style="display:flex; align-items:center; gap:9px;">
      <svg width="17" height="17" viewBox="0 0 18 18" fill="none" stroke="#7A2E1D" stroke-width="1.5"><rect x="6" y="1.5" width="6" height="9.5" rx="3"/><path d="M3.5 8.5a5.5 5.5 0 0 0 11 0M9 14v2.5M6.5 16.5h5"/></svg>
      <span class="serif" style="font-weight:700; font-size:14.5px; color:var(--red);">Голосовая заметка</span>
    </div>
    <div style="font-size:12.5px; color:var(--ink2); line-height:1.55;">Наговорите в Telegram-бота — расшифровка упадёт в буфер сама (см. <span class="mono" style="font-size:11px;">telegram_bot.py</span>).</div>
    <div class="mono" style="font-size:10.5px; color:var(--mut);">ГОЛОС → РАСШИФРОВКА → TRIAGE</div>
  </div>
  <div style="display:flex; flex-direction:column; gap:8px;">
    <div class="serif" style="font-size:13.5px; font-weight:700;">Или текстом</div>
    <textarea id="raw" placeholder="@домен ! Заголовок&#10;Текст заметки…&#10;Почему: …&#10;Следующий шаг: …"></textarea>
    <button class="btn-green" onclick="addRaw()">↑ В буфер</button>
    <div style="font-size:11px; color:var(--mut); line-height:1.5;">Директивы: <span class="mono" style="color:var(--sec)">@домен</span> · <span class="mono" style="color:var(--sec)">@new-project slug | Имя | Суть</span> · <span class="mono" style="color:var(--sec)">@new-contact</span></div>
  </div>
  <div style="height:1px; background:var(--line2);"></div>
  <div style="display:flex; justify-content:space-between; align-items:center;">
    <span class="serif" style="font-size:13.5px; font-weight:700;">Очередь буфера</span>
    <span class="mono" id="bufcount" style="font-size:11px; color:var(--mut);"></span>
  </div>
  <div id="buflist" style="display:flex; flex-direction:column; gap:8px; overflow-y:auto;"></div>
  <div style="flex-grow:1"></div>
  <div class="mono" id="lastops" style="font-size:10.5px; color:var(--mut); line-height:1.7; border-top:1px solid var(--line2); padding-top:12px;"></div>
</aside>

<main>
  <!-- панель фильтров -->
  <div id="toolbar" style="display:flex; align-items:center; gap:16px; flex-wrap:wrap;">
    <div class="seg" id="typefilter">
      <button class="on" data-f="all">Все</button>
      <button data-f="project">Проекты</button>
      <button data-f="relationship">Связи</button>
    </div>
    <div id="statuscounts" style="display:flex; gap:14px; font-size:12px; color:var(--ink2);"></div>
    <div style="flex-grow:1"></div>
    <div class="seg" id="viewswitch">
      <button class="on" data-v="cards">Карточки</button>
      <button data-v="radar">Радар</button>
    </div>
    <input id="search" placeholder="Поиск по атласу…" style="font:inherit; font-size:12.5px; padding:7px 12px; background:var(--card); border:1px solid var(--line2); border-radius:2px; width:200px; color:var(--ink);">
  </div>

  <div id="view-cards" class="grid"></div>

  <div id="view-radar" class="hidden" style="display:flex; gap:20px; align-items:flex-start;">
    <svg id="radar" viewBox="0 0 860 860" style="flex-grow:1; max-width:720px;"></svg>
    <div style="width:320px; display:flex; flex-direction:column; gap:14px;">
      <div class="sect-title">Требуют внимания</div>
      <div id="attention" style="display:flex; flex-direction:column; gap:8px;"></div>
      <div style="height:1px; background:var(--line2);"></div>
      <div class="sect-title">Обозначения</div>
      <div style="display:flex; flex-direction:column; gap:7px; font-size:12.5px; color:var(--ink2);">
        <div><span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:var(--green);vertical-align:-1px;"></span> Тёплая связь (score ≥ 50)</div>
        <div><span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:var(--ochre);vertical-align:-1px;"></span> Остывает — пунктирное гало</div>
        <div><span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:var(--gray);vertical-align:-1px;"></span> Пауза / Архив — серый сектор</div>
        <div><span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:#4A2E14;vertical-align:-1px;"></span> Я — центр атласа</div>
      </div>
      <div style="font-size:11.5px; color:var(--mut); line-height:1.6;">Клик по узлу открывает карточку домена.</div>
    </div>
  </div>

  <div id="view-domain" class="hidden"></div>

  <div style="flex-grow:1"></div>
  <div class="footer" id="auditline"></div>
</main>
</div>
<div class="toast" id="toast"></div>

<script>
let STATE = null, FILTER = 'all', VIEW = 'cards', QUERY = '';

async function api(path, body) {
  const r = await fetch(path, body ? {method:'POST', body: JSON.stringify(body)} : {});
  return r.json();
}
function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.style.display = 'block';
  clearTimeout(t._h); t._h = setTimeout(() => t.style.display = 'none', 6000);
}
async function refresh() { STATE = await api('/api/state'); render(); }
async function act(what) {
  const r = await api('/api/' + what, {});
  toast(r.output || JSON.stringify(r)); refresh();
}
async function addRaw() {
  const el = document.getElementById('raw');
  if (!el.value.trim()) return;
  const r = await api('/api/add-raw', {text: el.value});
  toast(r.output); el.value = ''; refresh();
}
async function touch(slug) {
  const r = await api('/api/touch', {slug});
  toast(r.output); openDomain(slug);
}
function esc(s) { return (s || '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

function statusStamp(d) {
  const c = d.paused ? 'var(--ochre)' : (d.active ? 'var(--green)' : 'var(--gray)');
  return `<span class="stamp" style="color:${c}; border-color:${c};">${esc(d.status.toUpperCase())}</span>`;
}
function healthRing(score, size) {
  const r = size/2 - 4, cf = 2*Math.PI*r, on = cf*Math.max(0,Math.min(100,score))/100;
  const col = score >= 50 ? 'var(--green)' : 'var(--ochre)';
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
    <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="var(--track)" stroke-width="4"/>
    <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="${col}" stroke-width="4"
      stroke-linecap="round" stroke-dasharray="${on} ${cf}" transform="rotate(-90 ${size/2} ${size/2})"/>
    <text x="50%" y="54%" text-anchor="middle" font-family="PT Mono,monospace" font-size="14" font-weight="700" fill="var(--ink)">${score}</text></svg>`;
}

function render() {
  if (!STATE) return;
  const s = STATE;
  document.getElementById('c-domains').textContent = s.domains.length;
  document.getElementById('c-buffer').textContent = s.buffer.length;
  document.getElementById('c-index').innerHTML = s.index_lines + '<span style="color:var(--mut);font-size:13px;">/60</span>';
  const lint = document.getElementById('lint');
  lint.textContent = s.lint.ok ? 'LINT OK' : 'LINT FAIL';
  lint.className = 'lintchip' + (s.lint.ok ? '' : ' bad');
  lint.title = s.lint.output; lint.onclick = () => toast(s.lint.output);

  const na = s.domains.filter(d => d.active).length,
        np = s.domains.filter(d => d.paused).length;
  document.getElementById('statuscounts').innerHTML =
    `<span><span style="color:var(--green)">●</span> Актив · <span class="mono">${na}</span></span>
     <span><span style="color:var(--ochre)">●</span> Пауза · <span class="mono">${np}</span></span>`;

  document.getElementById('bufcount').textContent = s.buffer.length + ' PENDING';
  document.getElementById('buflist').innerHTML = s.buffer.map(b => {
    const src = b.source.startsWith('telegram') ? (b.source.endsWith('voice') ? 'ГОЛОС · TELEGRAM' : 'ТЕКСТ · TELEGRAM')
              : (b.source === 'ui' ? 'ТЕКСТ · ДАШБОРД' : 'ТЕКСТ · CLI');
    const st = b.status === 'unmatched'
      ? '<span class="mono" style="color:var(--ochre);font-size:10px;">⚠ UNMATCHED</span>'
      : '<span class="mono" style="color:var(--green);font-size:10px;">PENDING</span>';
    return `<div class="bufitem" style="${b.status==='unmatched'?'border-color:var(--ochre2);':''}">
      <div style="display:flex;justify-content:space-between;"><span class="mono" style="font-size:10px;color:var(--bronze);">${src}</span>${st}</div>
      <div style="color:var(--ink2);line-height:1.45;">${esc(b.preview)}</div>
      <div class="mono" style="font-size:10px;color:var(--mut);">${b.created} · ${b.hash}</div></div>`;
  }).join('') || '<div style="font-size:12px;color:var(--mut);">Буфер пуст — всё разобрано.</div>';

  const audits = s.audit.map(a => `${a.ts} · ${a.action}`).slice(0, 2).join('<br>');
  document.getElementById('lastops').innerHTML = audits || '&nbsp;';
  document.getElementById('auditline').innerHTML =
    `<span style="color:var(--green)">▮</span>
     <span>${s.audit[0] ? 'AUDIT · ' + s.audit[0].ts + ' · ' + esc(s.audit[0].action) : 'журнал аудита пуст'}</span>
     <span style="flex-grow:1"></span>
     <span>metadata.db · entries <span style="color:var(--sec)">${s.db.entries}</span> · edges <span style="color:var(--sec)">${s.db.edges}</span></span>`;

  if (VIEW === 'cards') renderCards();
  if (VIEW === 'radar') renderRadar();
}

function visibleDomains() {
  return STATE.domains.filter(d =>
    (FILTER === 'all' || d.type === FILTER) &&
    (!QUERY || (d.name + ' ' + d.slug + ' ' + d.essence).toLowerCase().includes(QUERY)));
}

function renderCards() {
  document.getElementById('view-cards').innerHTML = visibleDomains().map(d => {
    const typ = d.type === 'project' ? 'ПРОЕКТ' : 'СВЯЗЬ · ' + esc((d.circle || '').toUpperCase());
    let meter = '', right = statusStamp(d);
    if (d.type === 'project') {
      const col = d.paused ? 'var(--ochre)' : 'var(--green)';
      meter = `<div><div style="display:flex;justify-content:space-between;font-size:10.5px;">
        <span class="label">АКТИВНОСТЬ</span><span class="mono" style="color:${col}">${d.days ?? '–'} дн. назад</span></div>
        <div class="track"><div style="width:${d.vitality ?? 0}%;height:100%;background:${col};"></div></div></div>`;
    } else if (d.health != null) {
      right = `<div style="width:54px;flex-shrink:0;">${healthRing(d.health, 54)}</div>`;
      meter = `<div style="display:flex;justify-content:space-between;font-size:12px;">
        <span>${statusStamp(d)}</span>
        <span style="color:var(--sec)">контакт: <span class="mono" style="color:${d.health>=50?'var(--ink2)':'var(--ochre)'}">${d.days ?? '–'} дн. назад</span></span></div>`;
    }
    const step = d.next_step && d.next_step !== '—' ? d.next_step
      : (d.blockers && d.blockers !== '—' ? d.blockers : '—');
    const stepCol = d.paused ? 'var(--ochre)' : 'var(--green)';
    return `<div class="card dcard" onclick="openDomain('${d.slug}')">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;">
        <div><div class="serif" style="font-weight:700;font-size:16px;">${esc(d.name)}</div>
        <div class="mono" style="font-size:10px;color:var(--mut);letter-spacing:1.5px;">${typ}</div></div>${right}</div>
      <div style="font-size:12.5px;color:var(--sec);line-height:1.5;">${esc(d.essence)}</div>
      ${meter}
      <div class="nextbox"><svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="${stepCol}" stroke-width="1.6" style="margin-top:1px;flex-shrink:0;"><path d="M2 7h9M7.5 3.5L11 7l-3.5 3.5"/></svg>
      <div>${esc(step)}</div></div></div>`;
  }).join('') || '<div style="color:var(--mut);">Ничего не найдено.</div>';
}

function renderRadar() {
  const rels = STATE.domains.filter(d => d.type === 'relationship');
  const pos = Object.fromEntries(rels.map(d => [d.slug, d]));
  const edges = STATE.edges
    .filter(e => pos[e.src] && pos[e.dst])
    .map(e => `<line x1="${pos[e.src].x}" y1="${pos[e.src].y}" x2="${pos[e.dst].x}" y2="${pos[e.dst].y}" stroke="#B49A6C" stroke-width="1.2"/>`).join('');
  const centerEdges = rels.filter(d => d.ring === 1 && !d.paused)
    .map(d => `<line x1="430" y1="430" x2="${d.x}" y2="${d.y}" stroke="#B49A6C" stroke-width="1.2"/>`).join('');
  const nodes = rels.map(d => {
    const col = d.paused ? 'var(--gray)' : (d.health >= 50 ? 'var(--green)' : 'var(--ochre)');
    const halo = (!d.paused && d.health < 50)
      ? `<circle cx="${d.x}" cy="${d.y}" r="20" fill="none" stroke="#B0763B" stroke-width="1.5" stroke-dasharray="4 3"/>` : '';
    const lab = d.paused ? '' :
      `<text x="${d.x + 18}" y="${d.y - 2}" font-family="PT Serif,serif" font-size="14" font-weight="700" fill="var(--ink)">${esc(d.name)}</text>
       <text x="${d.x + 18}" y="${d.y + 14}" font-family="PT Mono,monospace" font-size="11.5" fill="${col}">${d.health ?? '–'} · ${d.days ?? '–'} дн.</text>`;
    return `<g style="cursor:pointer" onclick="openDomain('${d.slug}')">${halo}
      <circle cx="${d.x}" cy="${d.y}" r="${d.ring === 1 ? 13 : 11}" fill="${col}" stroke="#F5EDD8" stroke-width="2.5"/>${lab}</g>`;
  }).join('');
  document.getElementById('radar').innerHTML = `
    <circle cx="430" cy="430" r="370" fill="#E7DAB6" stroke="#8C5A2B" stroke-width="2"/>
    <circle cx="430" cy="430" r="373.5" fill="none" stroke="#B99B6B" stroke-width="1"/>
    <circle cx="430" cy="430" r="280" fill="none" stroke="#C0A87C"/>
    <circle cx="430" cy="430" r="190" fill="none" stroke="#C0A87C"/>
    <circle cx="430" cy="430" r="100" fill="#F1E7CC" stroke="#B99B6B"/>
    <path d="M430,430 L109.6,245 A370,370 0 0 0 72.6,525.8 Z" fill="#D8CCAF" stroke="#B99B6B"/>
    <text x="150" y="300" font-family="PT Mono,monospace" font-size="12" fill="#8A7A5C">ПАУЗА / АРХИВ</text>
    ${centerEdges}${edges}${nodes}
    <circle cx="430" cy="430" r="11" fill="#4A2E14" stroke="#F5EDD8" stroke-width="2.5"/>
    <text x="430" y="466" text-anchor="middle" font-family="PT Serif,serif" font-size="13" font-weight="700" fill="#4A2E14">Я</text>
    <g font-family="PT Mono,monospace" font-size="12" fill="#8A7A5C" text-anchor="middle">
      <text x="430" y="352">БЛИЖНИЙ КРУГ</text><text x="430" y="637">СРЕДНИЙ КРУГ</text>
      <text x="430" y="782">СЛАБЫЕ СВЯЗИ</text></g>`;
  const att = rels.filter(d => !d.paused && d.health < 50)
    .sort((a, b) => a.health - b.health);
  document.getElementById('attention').innerHTML = att.map(d =>
    `<div class="card" style="padding:12px 14px; border-color:var(--ochre2); cursor:pointer;" onclick="openDomain('${d.slug}')">
      <div style="display:flex;justify-content:space-between;align-items:baseline;">
        <span class="serif" style="font-weight:700;font-size:14px;">${esc(d.name)}</span>
        <span class="mono" style="font-size:12px;color:var(--ochre);">${d.health} · ${d.days} дн.</span></div>
      <div style="font-size:12.5px;color:var(--ink2);margin-top:5px;">${esc(d.next_step || '')}</div></div>`
  ).join('') || '<div style="font-size:12.5px;color:var(--mut);">Все связи в тепле.</div>';
}

async function openDomain(slug) {
  const d = await api('/api/domain/' + slug);
  if (d.error) { toast(d.error); return; }
  const isRel = !d.type.toLowerCase().startsWith('проект');
  const stepKey = isRel ? 'Следующий социальный шаг' : 'Следующий шаг';
  const order = isRel
    ? ['Круг / Роль', 'Статус отношений', 'Friend Health Score', 'Ключевой контекст и ресурсы', 'Блокеры']
    : ['Статус', 'Где лежит', 'Цель', 'Артефакты', 'Риски и блокеры'];
  const secs = order.filter(k => d.sections[k]).map(k =>
    `<div style="margin-bottom:14px;"><div class="label" style="margin-bottom:5px;">${k.toUpperCase()}</div>
     <div style="font-size:13px;color:var(--ink2);line-height:1.6;white-space:pre-line;">${esc(d.sections[k])}</div></div>`).join('');
  const entries = d.entries.map((e, i) => `
    <div style="display:flex;gap:16px;">
      <div style="display:flex;flex-direction:column;align-items:center;width:12px;flex-shrink:0;">
        <div class="timeline-dot" style="${i === 0 ? 'background:var(--green);' : 'border:2px solid var(--gray);background:var(--bg);'}"></div>
        ${i < d.entries.length - 1 ? '<div style="width:1px;flex-grow:1;background:var(--line2);"></div>' : ''}</div>
      <div style="padding-bottom:18px;">
        <div style="display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;">
          <span class="mono" style="font-size:11.5px;color:${i === 0 ? 'var(--green)' : 'var(--mut)'};">${e.date} ${e.time}</span>
          <span class="serif" style="font-weight:700;font-size:15px;">${esc(e.title)}</span></div>
        ${e.what ? `<div style="font-size:13px;color:var(--ink2);line-height:1.55;margin-top:5px;"><span style="color:var(--mut)">Что:</span> ${esc(e.what)}</div>` : ''}
        ${e.why ? `<div style="font-size:13px;color:var(--sec);line-height:1.55;"><span style="color:var(--mut)">Почему:</span> ${esc(e.why)}</div>` : ''}
      </div></div>`).join('');
  document.getElementById('view-domain').innerHTML = `
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:16px;flex-wrap:wrap;">
      <button class="btn-ochre" style="border-color:var(--line2);color:var(--sec);padding:7px 14px;" onclick="closeDomain()">‹ Атлас</button>
      <h1 class="red" style="font-size:23px;">${esc(d.name)}</h1>
      <span class="stamp" style="color:var(--green);border-color:var(--green);">${esc(d.status.toUpperCase())}</span>
      <span class="mono" style="font-size:11px;color:var(--mut);">${esc(d.map)}</span>
      <div style="flex-grow:1"></div>
      ${isRel ? `<button class="btn-dark" onclick="touch('${d.slug}')">✓ Зафиксировать контакт</button>` : ''}
    </div>
    <div style="display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap;">
      <div class="card" style="width:440px;max-width:100%;padding:20px 22px;">
        <div class="sect-title" style="margin-bottom:14px;">Слой 2 · Карта состояния</div>
        <div class="card" style="border-color:var(--green);padding:12px 14px;margin-bottom:16px;">
          <div class="label" style="color:var(--green);margin-bottom:5px;">${stepKey.toUpperCase()}</div>
          <div style="font-size:14px;line-height:1.55;">${esc(d.sections[stepKey] || '—')}</div></div>
        ${secs}</div>
      <div style="flex:1;min-width:340px;">
        <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px;">
          <div class="sect-title">Слой 3 · Бортовой журнал</div>
          <span class="mono" style="font-size:10.5px;color:var(--mut);">APPEND-ONLY · новые сверху</span></div>
        ${entries || '<div style="color:var(--mut)">Журнал пуст.</div>'}</div>
    </div>`;
  show('domain');
}
function closeDomain() { show(VIEW); render(); }

function show(view) {
  for (const v of ['cards', 'radar', 'domain'])
    document.getElementById('view-' + v).classList.toggle('hidden', v !== view);
  document.getElementById('toolbar').classList.toggle('hidden', view === 'domain');
}

document.getElementById('typefilter').onclick = e => {
  if (!e.target.dataset.f) return;
  FILTER = e.target.dataset.f;
  for (const b of e.currentTarget.children) b.classList.toggle('on', b === e.target);
  render();
};
document.getElementById('viewswitch').onclick = e => {
  if (!e.target.dataset.v) return;
  VIEW = e.target.dataset.v;
  for (const b of e.currentTarget.children) b.classList.toggle('on', b === e.target);
  show(VIEW); render();
};
document.getElementById('search').oninput = e => { QUERY = e.target.value.toLowerCase(); render(); };

const qp = new URLSearchParams(location.search);
if (['cards', 'radar'].includes(qp.get('view'))) {
  VIEW = qp.get('view');
  for (const b of document.getElementById('viewswitch').children)
    b.classList.toggle('on', b.dataset.v === VIEW);
  show(VIEW);
}
refresh().then(() => { const d = qp.get('domain'); if (d) openDomain(d); });
setInterval(refresh, 30000);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    sys.exit(main())
