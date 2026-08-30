#!/usr/bin/env python3
"""Hermes Megamap — метаболический движок памяти (Memory as Metabolism).

Пайплайн: TRIAGE (сырой ввод → буфер) → CONSOLIDATE (буфер → слои 2/3 + INDEX)
→ DECAY & AUDIT (Friend Health Score, живучесть проектов, TTL буфера).

Инварианты:
- triage() не читает и не модифицирует domains/ и INDEX.md;
- logs/ — только дозапись (новые записи добавляются сверху);
- каждая карта в domains/ обязана иметь строку в INDEX.md.

Модуль импортируется из hermes_cli.py; может запускаться и напрямую:
    python3 metabolism.py {triage <text> | consolidate | decay}
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------- корень/конфиг

def find_root(start: Path | None = None) -> Path:
    """Корень системы = каталог, содержащий .hermes/. Ищем от cwd вверх,
    иначе от расположения скрипта (…/.hermes/scripts → корень)."""
    env = os.environ.get("HERMES_ROOT")
    if env:
        return Path(env).resolve()
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / ".hermes").is_dir():
            return p
    return Path(__file__).resolve().parent.parent.parent


ROOT = find_root()

DEFAULT_CONFIG = {
    "buffer_ttl_days": 7,
    "gravity": {"min_score": 1},
    "decay": {
        "project_pause_days": 21,
        "contact_pause_days": 45,
        "health_decay_per_day": 2,
        "health_pause_score": 30,
    },
}


def load_config(root: Path = None) -> dict:
    root = root or ROOT
    cfg_path = root / ".hermes" / "config.json"
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if cfg_path.is_file():
        loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
        for k, v in loaded.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


# ---------------------------------------------------------------------- SQLite

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    hash         TEXT UNIQUE NOT NULL,
    path         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending|unmatched|processed
    domain       TEXT,
    created_at   TEXT NOT NULL,
    processed_at TEXT
);
CREATE TABLE IF NOT EXISTS edges (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    src        TEXT NOT NULL,
    dst        TEXT NOT NULL,
    relation   TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT
);
"""


def db_connect(root: Path = None) -> sqlite3.Connection:
    root = root or ROOT
    conn = sqlite3.connect(root / ".hermes" / "metadata.db")
    conn.executescript(SCHEMA)
    return conn


def audit(conn: sqlite3.Connection, action: str, detail: str = "") -> None:
    conn.execute("INSERT INTO audit_log (ts, action, detail) VALUES (?, ?, ?)",
                 (datetime.now().isoformat(timespec="seconds"), action, detail))
    conn.commit()


# ------------------------------------------------------------------- INDEX.md

INDEX_HEADER = """# HERMES MEGAMAP — Слой 1: Индекс доменов

> Один экран (не более 60 строк). Контракт агента: CLAUDE.md.
> Проверка: `python3 .hermes/scripts/lint_megamap.py`.

| Домен / Имя | Тип | Статус | Суть одной фразой | Файл Карты | Файл Журнала |
|---|---|---|---|---|---|
"""


def index_path(root: Path = None) -> Path:
    return (root or ROOT) / "INDEX.md"


def parse_index(root: Path = None) -> dict:
    """{slug: {type, status, essence, map, log, line_no}} из таблицы INDEX.md."""
    root = root or ROOT
    domains = {}
    path = index_path(root)
    if not path.is_file():
        return domains
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 6 or cells[0] in ("Домен / Имя", "---"):
            continue
        if set(cells[0]) <= {"-"}:
            continue
        m_map = re.search(r"\((domains/[^)]+\.md)\)", cells[4])
        m_log = re.search(r"\((logs/[^)]+\.md)\)", cells[5])
        slug = Path(m_map.group(1)).stem if m_map else cells[0]
        domains[slug] = {
            "name": cells[0], "type": cells[1], "status": cells[2],
            "essence": cells[3],
            "map": m_map.group(1) if m_map else None,
            "log": m_log.group(1) if m_log else None,
            "line_no": i,
        }
    return domains


def index_add_row(root: Path, slug: str, dtype: str, status: str,
                  essence: str, map_rel: str, log_rel: str) -> None:
    path = index_path(root)
    text = path.read_text(encoding="utf-8") if path.is_file() else INDEX_HEADER
    row = (f"| {slug} | {dtype} | {status} | {essence} "
           f"| [карта]({map_rel}) | [журнал]({log_rel}) |")
    path.write_text(text.rstrip("\n") + "\n" + row + "\n", encoding="utf-8")


def index_set_status(root: Path, slug: str, new_status: str) -> None:
    path = index_path(root)
    lines = path.read_text(encoding="utf-8").splitlines()
    info = parse_index(root).get(slug)
    if not info:
        return
    cells = [c.strip() for c in lines[info["line_no"]].strip().strip("|").split("|")]
    cells[2] = new_status
    lines[info["line_no"]] = "| " + " | ".join(cells) + " |"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------- работа с разделами

def replace_section(text: str, header: str, new_body: str) -> str:
    """Заменяет тело раздела `## header` (до следующего ## или конца файла)."""
    pattern = re.compile(rf"(^## {re.escape(header)}\s*\n)(.*?)(?=^## |\Z)",
                        re.MULTILINE | re.DOTALL)
    if not pattern.search(text):
        return text.rstrip("\n") + f"\n\n## {header}\n{new_body.rstrip()}\n"
    return pattern.sub(lambda m: m.group(1) + new_body.rstrip() + "\n\n", text, count=1)


def append_to_section(text: str, header: str, line: str) -> str:
    pattern = re.compile(rf"(^## {re.escape(header)}\s*\n)(.*?)(?=^## |\Z)",
                        re.MULTILINE | re.DOTALL)
    m = pattern.search(text)
    if not m:
        return replace_section(text, header, line)
    body = m.group(2).rstrip()
    body = line if body in ("", "—") else body + "\n" + line
    return pattern.sub(m.group(1) + body + "\n\n", text, count=1)


def log_prepend(root: Path, log_rel: str, title: str, what: str, why: str,
                now: datetime | None = None) -> None:
    """Append-only журнал: новая запись дописывается сверху, под заголовком H1.
    Существующие записи не модифицируются."""
    now = now or datetime.now()
    path = root / log_rel
    entry = (f"### {now.strftime('%Y-%m-%d %H:%M')} — {title}\n"
             f"**Что произошло/решено:** {what}\n"
             f"**Почему:** {why}\n")
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    m = re.match(r"(# .+?\n)", old)
    if m:
        head, rest = old[:m.end()], old[m.end():].lstrip("\n")
        path.write_text(head + "\n" + entry + ("\n" + rest if rest else ""),
                        encoding="utf-8")
    else:
        path.write_text(entry + ("\n" + old if old.strip() else ""), encoding="utf-8")


def last_log_date(root: Path, log_rel: str):
    """Дата последней НАСТОЯЩЕЙ активности: служебные записи самого движка
    (Авто-пауза и т.п.) не в счёт — иначе decay сбрасывал бы себе же часы."""
    path = root / log_rel
    if not path.is_file():
        return None
    dates = [d for d, title in
             re.findall(r"^### (\d{4}-\d{2}-\d{2}) \d{2}:\d{2} — (.+)$",
                        path.read_text(encoding="utf-8"), re.MULTILINE)
             if not title.strip().startswith("Авто-")]
    if not dates:
        return None
    return datetime.strptime(max(dates), "%Y-%m-%d")


# --------------------------------------------------------------------- шаблоны

def template(root: Path, kind: str) -> str:
    p = root / ".hermes" / "templates" / f"{kind}.md"
    if p.is_file():
        return p.read_text(encoding="utf-8")
    # запасной вариант, если шаблоны не установлены
    if kind == "project":
        return ("# {name}\n\n## Статус\nАктив. Обновлено: {date}.\n\n"
                "## Где лежит\n—\n\n## Цель\n{essence}\n\n## Артефакты\n—\n\n"
                "## Следующий шаг\nОпределить следующий шаг.\n\n"
                "## Риски и блокеры\n—\n")
    return ("# {name}\n\n## Круг / Роль\n{essence}\n\n"
            "## Статус отношений\nТеплый\n\n"
            "## Friend Health Score\n100/100. Последний контакт: {date}.\n\n"
            "## Ключевой контекст и ресурсы\n—\n\n"
            "## Следующий социальный шаг\nОпределить следующий шаг.\n\n"
            "## Блокеры\n—\n")


# ---------------------------------------------------------------- 1. TRIAGE

def triage(text: str, root: Path = None, source: str = "cli") -> Path | None:
    """Streaming ingestion: сырая заметка → /buffer/, статус pending.
    По контракту НЕ трогает domains/ и INDEX.md.
    source: cli | ui | telegram | telegram-voice — метка канала поступления."""
    root = root or ROOT
    text = text.strip()
    if not text:
        print("triage: пустая заметка, нечего сохранять")
        return None
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    conn = db_connect(root)
    dup = conn.execute("SELECT path, status FROM entries WHERE hash = ?",
                       (digest,)).fetchone()
    if dup:
        print(f"triage: дубликат (hash уже в базе, {dup[1]}): {dup[0]}")
        conn.close()
        return None
    now = datetime.now()
    fname = f"{now.strftime('%Y-%m-%d_%H%M%S')}_{digest[:12]}.md"
    rel = f"buffer/{fname}"
    body = (f"---\nhash: {digest}\ncreated: {now.isoformat(timespec='seconds')}\n"
            f"source: {source}\nstatus: pending\n---\n{text}\n")
    (root / rel).write_text(body, encoding="utf-8")
    conn.execute(
        "INSERT INTO entries (hash, path, status, created_at) VALUES (?, ?, 'pending', ?)",
        (digest, rel, now.isoformat(timespec="seconds")))
    audit(conn, "triage", rel)
    conn.close()
    print(f"triage: заметка принята → {rel}")
    return root / rel


# ------------------------------------------------------------ 2. CONSOLIDATE

def _read_note(path: Path) -> tuple[str, str, str]:
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", raw, re.DOTALL)
    front = m.group(1) if m else ""
    body = raw[m.end():] if m else raw
    hm = re.search(r"^hash:\s*(\S+)", front, re.MULTILINE)
    sm = re.search(r"^source:\s*(\S+)", front, re.MULTILINE)
    return (hm.group(1) if hm else hashlib.sha256(raw.encode()).hexdigest(),
            body.strip(), sm.group(1) if sm else "cli")


def _parse_note(body: str) -> dict:
    """Директивы: @slug / @new-project / @new-contact в первой строке,
    `! Заголовок`, `Почему: …`, `Следующий шаг: …`."""
    note = {"target": None, "new": None, "title": None, "why": "не зафиксировано",
            "next_step": None, "text_lines": []}
    for i, line in enumerate(body.splitlines()):
        s = line.strip()
        if i == 0 and s.startswith(("@new-project", "@new-contact")):
            kind = "project" if s.startswith("@new-project") else "relationship"
            rest = s.split(None, 1)[1] if len(s.split(None, 1)) > 1 else ""
            parts = [p.strip() for p in rest.split("|")]
            note["new"] = {"kind": kind,
                           "slug": parts[0] if parts else "unnamed",
                           "name": parts[1] if len(parts) > 1 else parts[0],
                           "essence": parts[2] if len(parts) > 2 else "—"}
            note["target"] = note["new"]["slug"]
            continue
        if i == 0 and s.startswith("@"):
            note["target"] = s.split()[0][1:]
            tail = s[len(s.split()[0]):].strip()
            if tail.startswith("! "):          # «@домен ! Заголовок» одной строкой
                note["title"] = tail[2:].strip()
            elif tail:
                note["text_lines"].append(tail)
            continue
        if s.startswith("! "):
            note["title"] = s[2:].strip()
            continue
        low = s.lower()
        if low.startswith("почему:"):
            note["why"] = s.split(":", 1)[1].strip()
            continue
        if low.startswith(("следующий шаг:", "следующий социальный шаг:")):
            note["next_step"] = s.split(":", 1)[1].strip()
            continue
        note["text_lines"].append(s)
    text = " ".join(l for l in note["text_lines"] if l).strip()
    note["empty"] = not text and not note["title"] and not note["next_step"]
    if not note["title"]:
        note["title"] = (text[:60] + "…") if len(text) > 60 else (text or "Заметка")
    note["what"] = text or note["title"]
    return note


def _gravity_match(note: dict, domains: dict, min_score: int) -> str | None:
    """Кластеризация без LLM: заметка «притягивается» к домену по упоминаниям
    slug/имени в тексте. Привязка только при однозначном лучшем совпадении."""
    hay = (note["what"] + " " + (note["title"] or "")).lower()
    scores = {}
    for slug, info in domains.items():
        score = 0
        if slug.lower() in hay:
            score += 2
        for word in re.findall(r"\w{4,}", info["name"].lower()):
            if word != slug.lower() and word in hay:
                score += 1
        if score:
            scores[slug] = score
    if not scores:
        return None
    best = max(scores.values())
    winners = [s for s, sc in scores.items() if sc == best]
    return winners[0] if len(winners) == 1 and best >= min_score else None


def _create_domain(root: Path, new: dict, now: datetime) -> dict:
    kind = new["kind"]
    sub = "projects" if kind == "project" else "relationships"
    dtype = "Проект" if kind == "project" else "Связь"
    map_rel = f"domains/{sub}/{new['slug']}.md"
    log_rel = f"logs/{sub}/{new['slug']}.log.md"
    date = now.strftime("%Y-%m-%d")
    (root / map_rel).write_text(
        template(root, kind).format(name=new["name"], essence=new["essence"],
                                    date=date),
        encoding="utf-8")
    (root / log_rel).write_text(f"# {new['name']} — бортовой журнал\n", encoding="utf-8")
    log_prepend(root, log_rel, "Домен создан",
                f"Зарегистрирован новый домен «{new['name']}» ({dtype}).",
                "Заведён через Triage-буфер (директива @new-*).", now)
    index_add_row(root, new["slug"], dtype, "Актив", new["essence"], map_rel, log_rel)
    return {"name": new["name"], "type": dtype, "status": "Актив",
            "essence": new["essence"], "map": map_rel, "log": log_rel}


def consolidate(root: Path = None) -> int:
    """Sleep/batch-цикл: буфер → журналы (слой 3), карты (слой 2), INDEX (слой 1).
    Обработанные оригиналы уходят в cold/sources/."""
    root = root or ROOT
    cfg = load_config(root)
    conn = db_connect(root)
    now = datetime.now()
    processed = unmatched = 0

    # Два прохода: сначала заметки, создающие домены (@new-*), затем остальные —
    # чтобы встреча, пришедшая в ту же секунду, нашла свежесозданный домен.
    files = sorted((root / "buffer").glob("*.md"))
    files.sort(key=lambda p: 0 if _read_note(p)[1].startswith("@new-") else 1)
    for f in files:
        digest, body, source = _read_note(f)
        if not body:
            continue
        note = _parse_note(body)
        domains = parse_index(root)

        if note["new"]:
            if note["new"]["slug"] in domains:
                print(f"consolidate: домен «{note['new']['slug']}» уже существует — "
                      f"заметка пойдёт в него")
            else:
                domains[note["new"]["slug"]] = _create_domain(root, note["new"], now)
                audit(conn, "domain-created", note["new"]["slug"])
            if note["empty"]:
                # чистая директива создания: домен заведён, дублировать записью
                # «Заметка» нечего — оригинал сразу в холодный архив
                dest = root / "cold" / "sources" / f.name
                shutil.move(str(f), dest)
                conn.execute("UPDATE entries SET status='processed', domain=?, "
                             "processed_at=?, path=? WHERE hash=?",
                             (note["new"]["slug"], now.isoformat(timespec="seconds"),
                              f"cold/sources/{f.name}", digest))
                conn.commit()
                processed += 1
                print(f"consolidate: {f.name} → создан домен «{note['new']['slug']}»")
                continue

        target = note["target"]
        if target not in domains:
            target = _gravity_match(note, domains, cfg["gravity"]["min_score"])
        if not target or target not in domains:
            conn.execute("UPDATE entries SET status='unmatched' WHERE hash=?", (digest,))
            audit(conn, "consolidate-unmatched", f.name)
            conn.commit()
            unmatched += 1
            print(f"consolidate: не удалось привязать {f.name} — остаётся в буфере "
                  f"(добавьте @<домен> в первую строку)")
            continue

        info = domains[target]
        # Слой 3: дельта в журнал (голосовые заметки помечаются источником)
        title = note["title"]
        if source == "telegram-voice":
            title += " [голос]"
        log_prepend(root, info["log"], title, note["what"], note["why"], now)
        # Слой 2: обновление снимка состояния
        map_path = root / info["map"]
        text = map_path.read_text(encoding="utf-8")
        if note["next_step"]:
            step_header = ("Следующий шаг" if info["type"].lower().startswith("проект")
                           else "Следующий социальный шаг")
            text = replace_section(text, step_header, note["next_step"])
        if info["type"].lower().startswith("проект"):
            text = re.sub(r"Обновлено: \d{4}-\d{2}-\d{2}",
                          f"Обновлено: {now.strftime('%Y-%m-%d')}", text)
        else:
            text = replace_section(text, "Friend Health Score",
                                   f"100/100. Последний контакт: {now.strftime('%Y-%m-%d')}.")
        map_path.write_text(text, encoding="utf-8")
        # Рёбра графа: упоминания других доменов
        for other in domains:
            if other != target and other.lower() in note["what"].lower():
                conn.execute("INSERT INTO edges (src, dst, relation, created_at) "
                             "VALUES (?, ?, 'упомянут', ?)",
                             (target, other, now.isoformat(timespec="seconds")))
        # Оригинал — в холодный архив, метка processed
        dest = root / "cold" / "sources" / f.name
        shutil.move(str(f), dest)
        row = conn.execute("SELECT id FROM entries WHERE hash=?", (digest,)).fetchone()
        if row:
            conn.execute("UPDATE entries SET status='processed', domain=?, "
                         "processed_at=?, path=? WHERE hash=?",
                         (target, now.isoformat(timespec="seconds"),
                          f"cold/sources/{f.name}", digest))
        else:
            conn.execute("INSERT INTO entries (hash, path, status, domain, "
                         "created_at, processed_at) VALUES (?, ?, 'processed', ?, ?, ?)",
                         (digest, f"cold/sources/{f.name}", target,
                          now.isoformat(timespec="seconds"),
                          now.isoformat(timespec="seconds")))
        audit(conn, "consolidate", f"{f.name} → {target}")
        conn.commit()
        processed += 1
        print(f"consolidate: {f.name} → домен «{target}»")

    conn.close()
    print(f"consolidate: обработано {processed}, не привязано {unmatched}")
    return 0 if unmatched == 0 else 2


# ---------------------------------------------------------- 3. DECAY & AUDIT

def decay_and_audit(root: Path = None) -> int:
    """Friend Health Score, живучесть проектов, TTL буфера.
    Просроченное бездействие → статус «Пауза» с фиксацией блокера."""
    root = root or ROOT
    cfg = load_config(root)["decay"]
    ttl = load_config(root)["buffer_ttl_days"]
    conn = db_connect(root)
    now = datetime.now()
    changes = 0

    for slug, info in parse_index(root).items():
        if not info["map"] or not (root / info["map"]).is_file():
            continue
        last = last_log_date(root, info["log"]) if info["log"] else None
        days = (now - last).days if last else None
        map_path = root / info["map"]
        text = map_path.read_text(encoding="utf-8")

        if info["type"].lower().startswith("проект"):
            if days is None:
                continue
            if days > cfg["project_pause_days"] and "актив" in info["status"].lower():
                blocker = (f"- [auto {now.strftime('%Y-%m-%d')}] Decay: "
                           f"{days} дн. без активности — статус переведён в Пауза.")
                text = replace_section(text, "Статус",
                                       f"Пауза. Обновлено: {now.strftime('%Y-%m-%d')} "
                                       f"(авто-decay: {days} дн. без активности).")
                text = append_to_section(text, "Риски и блокеры", blocker)
                map_path.write_text(text, encoding="utf-8")
                index_set_status(root, slug, "Пауза")
                log_prepend(root, info["log"], "Авто-пауза (decay)",
                            f"Проект переведён в Пауза: {days} дн. без активности "
                            f"(порог {cfg['project_pause_days']}).",
                            "Метаболический цикл DECAY: карта не должна врать про статус.",
                            now)
                audit(conn, "decay-pause-project", f"{slug}: {days}d")
                changes += 1
                print(f"decay: проект «{slug}» → Пауза ({days} дн. без активности)")
        else:
            if days is None:
                continue
            score = max(0, 100 - days * cfg["health_decay_per_day"])
            text = replace_section(
                text, "Friend Health Score",
                f"{score}/100. Последний контакт: {last.strftime('%Y-%m-%d')} "
                f"({days} дн. назад). Порог паузы: score < {cfg['health_pause_score']} "
                f"или молчание > {cfg['contact_pause_days']} дн.")
            paused = (score < cfg["health_pause_score"]
                      or days > cfg["contact_pause_days"])
            if paused and "пауза" not in info["status"].lower():
                blocker = (f"- [auto {now.strftime('%Y-%m-%d')}] Decay: контакт "
                           f"остыл ({days} дн., score {score}) — статус Пауза.")
                text = replace_section(text, "Статус отношений",
                                       f"Пауза (авто-decay {now.strftime('%Y-%m-%d')}: "
                                       f"{days} дн. без контакта)")
                text = append_to_section(text, "Блокеры", blocker)
                index_set_status(root, slug, "Пауза")
                log_prepend(root, info["log"], "Авто-пауза (decay)",
                            f"Связь переведена в Пауза: {days} дн. без контакта, "
                            f"Friend Health Score {score}.",
                            "Метаболический цикл DECAY.", now)
                audit(conn, "decay-pause-contact", f"{slug}: {days}d, score {score}")
                changes += 1
                print(f"decay: связь «{slug}» → Пауза (score {score}, {days} дн.)")
            map_path.write_text(text, encoding="utf-8")

    # TTL буфера
    stale = 0
    for f in sorted((root / "buffer").glob("*.md")):
        m = re.search(r"^created:\s*(\S+)", f.read_text(encoding="utf-8"), re.MULTILINE)
        if not m:
            continue
        age = (now - datetime.fromisoformat(m.group(1))).days
        if age > ttl:
            stale += 1
            audit(conn, "audit-buffer-stale", f"{f.name}: {age}d > TTL {ttl}d")
            print(f"audit: {f.name} висит в буфере {age} дн. (TTL {ttl}) — "
                  f"требуется consolidate или ручной разбор")
    conn.close()
    print(f"decay: изменений статуса {changes}, просроченных заметок в буфере {stale}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    cmd = sys.argv[1]
    if cmd == "triage":
        triage(" ".join(sys.argv[2:]))
    elif cmd == "consolidate":
        sys.exit(consolidate())
    elif cmd == "decay":
        sys.exit(decay_and_audit())
    else:
        print(f"неизвестная команда: {cmd}")
        sys.exit(2)
