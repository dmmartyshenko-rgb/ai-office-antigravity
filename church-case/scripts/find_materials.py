#!/usr/bin/env python3
"""Поиск материалов дела на компьютере — только опись, ничего не копирует.

    python3 find_materials.py --term Слово1 --term Слово2 [--root ~] [--root /Volumes/Диск]

macOS: Spotlight (mdfind) — ищет и в именах, и в содержимом (PDF, docx, заметки).
Иначе/дополнительно: обход папок по именам файлов и папок.
Также отмечает папки WhatsApp Desktop с голосовыми (если есть).
Выход: private/work/found.csv (путь, размер, изменён, тип, чем найден) —
человек просматривает список и передаёт нужное в ingest_whatsapp.py --extra.
"""
import argparse
import csv
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import AUDIO_EXT, PRIVATE, WORK  # noqa: E402

SKIP_DIRS = {".git", "node_modules", "Library", ".Trash", "private", "__pycache__", ".cache"}
WHATSAPP_MAC = [
    "~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/Message/Media",
    "~/Library/Containers/net.whatsapp.WhatsApp/Data/Library/Application Support",
]


def spotlight(term: str, roots: list) -> set:
    out = set()
    for root in roots:
        try:
            r = subprocess.run(["mdfind", "-onlyin", str(root), term],
                               capture_output=True, text=True, timeout=120)
            out.update(l for l in r.stdout.splitlines() if l)
        except (OSError, subprocess.TimeoutExpired):
            pass
    return out


def walk(terms: list, roots: list) -> set:
    low = [t.lower() for t in terms]
    out = set()
    for root in roots:
        for d, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(".")]
            for name in dirs + files:
                if any(t in name.lower() for t in low):
                    out.add(os.path.join(d, name))
    return out


def kind(p: Path) -> str:
    if p.is_dir():
        return "folder"
    s = p.suffix.lower()
    if s in AUDIO_EXT:
        return "audio"
    if s in {".zip"}:
        return "archive"
    if s in {".pdf", ".doc", ".docx", ".rtf", ".txt", ".pages", ".odt", ".md"}:
        return "document"
    if s in {".jpg", ".jpeg", ".png", ".heic"}:
        return "image"
    if s in {".mov", ".mp4", ".m4v"}:
        return "video"
    return "other"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--term", action="append", required=True)
    ap.add_argument("--root", action="append", type=Path)
    args = ap.parse_args()
    roots = [r.expanduser() for r in (args.root or [Path.home()])]
    hits = {}
    if platform.system() == "Darwin":
        for t in args.term:
            for p in spotlight(t, roots):
                hits.setdefault(p, set()).add(f"spotlight:{t}")
    for p in walk(args.term, roots):
        hits.setdefault(p, set()).add("name")
    for wa in WHATSAPP_MAC:
        wp = Path(wa).expanduser()
        if wp.is_dir():
            hits.setdefault(str(wp), set()).add("whatsapp-desktop-media")

    rows = []
    for p, how in hits.items():
        pp = Path(p)
        if not pp.exists() or str(PRIVATE) in p:  # не описывать собственные копии дела
            continue
        st = pp.stat()
        rows.append({"path": p, "kind": kind(pp), "size": st.st_size,
                     "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes"),
                     "found_by": ";".join(sorted(how))})
    rows.sort(key=lambda r: (r["kind"], r["path"]))
    out = WORK / "found.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["path", "kind", "size", "modified", "found_by"])
        w.writeheader()
        w.writerows(rows)
    by = {}
    for r in rows:
        by[r["kind"]] = by.get(r["kind"], 0) + 1
    print(f"найдено: {len(rows)} → {out}")
    print(", ".join(f"{k}={v}" for k, v in sorted(by.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
