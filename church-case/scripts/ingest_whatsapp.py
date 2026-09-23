#!/usr/bin/env python3
"""Приём WhatsApp-экспорта: цепочка хранения + индекс сообщений.

    python3 ingest_whatsapp.py <export.zip | папка_экспорта>
    python3 ingest_whatsapp.py --extra <папка>   # прочие материалы: только манифест

1. Копирует экспорт в private/raw/<имя>/ (zip распаковывается; оригинал zip
   тоже хэшируется — это главный «вещдок»).
2. Снимает sha256 каждого файла → private/work/manifest.json.
3. Разбирает _chat.txt / «Чат WhatsApp с ….txt» (форматы iOS и Android)
   → private/work/messages.jsonl: {n, ts, author, text, attachment, attachment_sha256}.

Повторный запуск идемпотентен: файлы с тем же sha256 не дублируются.
"""
import argparse
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (AUDIO_EXT, MANIFEST, MESSAGES, RAW, dump_json, load_json,  # noqa: E402
                    sha256, write_jsonl)

# iOS:     [12.03.23, 14:05:33] Анатолий: текст
# Android: 12.03.2023, 14:05 - Анатолий: текст   (также «12/03/2023, 14:05 - »)
RE_IOS = re.compile(r"^‎?\[(\d{1,2}[./]\d{1,2}[./]\d{2,4}),? (\d{1,2}:\d{2}(?::\d{2})?)\] ([^:]+?): (.*)$")
RE_AND = re.compile(r"^‎?(\d{1,2}[./]\d{1,2}[./]\d{2,4}),? (\d{1,2}:\d{2}(?::\d{2})?) [-–] ([^:]+?): (.*)$")
# Вложения: «<attached: 00000012-AUDIO-2023-03-12-14-05-33.opus>»,
# «<приложено: …>», «PTT-20230312-WA0001.opus (файл добавлен)», «… (file attached)»
RE_ATT = [
    re.compile(r"<(?:attached|приложено|вложение):\s*([^>]+)>", re.I),
    re.compile(r"^‎?(\S+\.\w{2,4}) \((?:файл добавлен|file attached|файл прикреплен)\)", re.I),
]


def parse_ts(d: str, t: str) -> str:
    d = d.replace("/", ".")
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            day = datetime.strptime(d, fmt)
            break
        except ValueError:
            day = None
    if day is None:
        return f"{d} {t}"
    parts = [int(x) for x in t.split(":")] + [0]
    return day.replace(hour=parts[0], minute=parts[1], second=parts[2]).isoformat()


def parse_chat(path: Path, files_by_name: dict) -> list:
    msgs = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        m = RE_IOS.match(line) or RE_AND.match(line)
        if m:
            d, t, author, text = m.groups()
            msgs.append({"n": len(msgs) + 1, "ts": parse_ts(d, t),
                         "author": author.strip("‎ ").strip(), "text": text.strip("‎")})
        elif msgs:  # продолжение многострочного сообщения
            msgs[-1]["text"] += "\n" + line
    for msg in msgs:
        for rx in RE_ATT:
            a = rx.search(msg["text"])
            if a:
                name = a.group(1).strip()
                msg["attachment"] = name
                msg["attachment_sha256"] = files_by_name.get(name)
                break
    return msgs


def register(manifest: dict, path: Path, root: Path, origin: str) -> str:
    digest = sha256(path)
    rel = str(path.relative_to(root.parent))
    entry = manifest.setdefault(digest, {"paths": [], "origin": origin,
                                         "size": path.stat().st_size,
                                         "kind": "audio" if path.suffix.lower() in AUDIO_EXT else "file",
                                         "registered": datetime.now().isoformat(timespec="seconds")})
    if rel not in entry["paths"]:
        entry["paths"].append(rel)
    return digest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("--extra", action="store_true", help="не чат: только скопировать и хэшировать")
    args = ap.parse_args()
    src = args.source.expanduser()
    if not src.exists():
        print(f"FAIL: нет {src}")
        return 1

    manifest = load_json(MANIFEST, {})
    dest = RAW / src.stem
    dest.mkdir(parents=True, exist_ok=True)
    if src.is_file() and src.suffix.lower() == ".zip":
        shutil.copy2(src, RAW / src.name)
        register(manifest, RAW / src.name, RAW, "original-zip")
        with zipfile.ZipFile(src) as z:
            z.extractall(dest)
    elif src.is_dir():
        shutil.copytree(src, dest, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dest / src.name)

    files_by_name = {}
    for p in sorted(dest.rglob("*")):
        if p.is_file():
            files_by_name[p.name] = register(manifest, p, RAW, src.name)
    dump_json(MANIFEST, manifest)
    n_audio = sum(1 for e in manifest.values() if e["kind"] == "audio")
    print(f"manifest: {len(manifest)} файлов (аудио: {n_audio}) → {MANIFEST}")

    if args.extra:
        return 0
    chats = [p for p in dest.rglob("*.txt") if "whatsapp" in p.name.lower() or p.name == "_chat.txt"] \
        or list(dest.rglob("*.txt"))
    if not chats:
        print("FAIL: в экспорте не найден .txt чата")
        return 1
    msgs = []
    for chat in chats:
        for m in parse_chat(chat, files_by_name):
            m["chat"] = chat.name
            msgs.append(m)
    for i, m in enumerate(msgs, 1):
        m["n"] = i
    write_jsonl(MESSAGES, msgs)
    authors = {}
    for m in msgs:
        authors[m["author"]] = authors.get(m["author"], 0) + 1
    missing = [m["attachment"] for m in msgs if m.get("attachment") and not m.get("attachment_sha256")]
    print(f"messages: {len(msgs)} → {MESSAGES}")
    print("авторы: " + ", ".join(f"{a} ({c})" for a, c in sorted(authors.items(), key=lambda x: -x[1])))
    if missing:
        print(f"WARN: {len(missing)} вложений упомянуто в чате, но нет в архиве "
              f"(экспорт «без медиа»?): {missing[:5]}")
    return 0 if msgs else 1


if __name__ == "__main__":
    sys.exit(main())
