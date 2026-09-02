#!/usr/bin/env python3
"""hermes — CLI внешней памяти Hermes Megamap.

Команды:
  hermes init                 — создать структуру хранилища в текущем каталоге
  hermes add-raw "<text>"     — быстрый сброс сырой заметки в Triage-буфер
  hermes consolidate          — пакетная обработка буфера по слоям 1/2/3
  hermes decay                — Decay & Audit: health-score, живучесть, TTL буфера
  hermes status               — дашборд Слоя 1 (INDEX + буфер)
  hermes lint                 — проверка инвариантов (код 0 = зелёный)
  hermes ui [порт]            — веб-дашборд на http://127.0.0.1:8137
  hermes bot                  — Telegram-бот приёмной (голос/текст → буфер)

Синтаксис заметки для add-raw (первая строка):
  @<домен>                          — привязать к существующему домену
  @new-project slug | Имя | Суть    — создать домен-проект
  @new-contact slug | ФИО | Круг    — создать карточку связи
Внутри текста: `! Заголовок`, `Почему: …`, `Следующий шаг: …`.
Без директивы @ заметка привязывается по упоминанию домена в тексте (gravity).
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import metabolism as mb  # noqa: E402


def cmd_init(_args) -> int:
    root = Path.cwd()
    for d in ["buffer", "domains/projects", "domains/relationships",
              "logs/projects", "logs/relationships", "cold/sources",
              ".hermes/scripts", ".hermes/templates"]:
        (root / d).mkdir(parents=True, exist_ok=True)
    index = root / "INDEX.md"
    if not index.is_file():
        index.write_text(mb.INDEX_HEADER, encoding="utf-8")
    cfg = root / ".hermes" / "config.json"
    if not cfg.is_file():
        import json
        cfg.write_text(json.dumps(mb.DEFAULT_CONFIG, ensure_ascii=False, indent=2)
                       + "\n", encoding="utf-8")
    mb.db_connect(root).close()
    print(f"init: хранилище Hermes Megamap готово в {root}")
    return 0


def cmd_add_raw(args) -> int:
    text = args.text if args.text else sys.stdin.read()
    root = mb.find_root()
    return 0 if mb.triage(text, root) else 1


def cmd_consolidate(_args) -> int:
    return mb.consolidate(mb.find_root())


def cmd_decay(_args) -> int:
    return mb.decay_and_audit(mb.find_root())


def cmd_status(_args) -> int:
    root = mb.find_root()
    index = root / "INDEX.md"
    if index.is_file():
        print(index.read_text(encoding="utf-8").rstrip())
    else:
        print("INDEX.md отсутствует — запустите `hermes init`")
    pending = sorted((root / "buffer").glob("*.md"))
    print(f"\nБуфер (L0): {len(pending)} необработанных заметок"
          + ("" if not pending else ":"))
    for p in pending:
        print(f"  - {p.name}")
    conn = mb.db_connect(root)
    unmatched = conn.execute(
        "SELECT COUNT(*) FROM entries WHERE status='unmatched'").fetchone()[0]
    if unmatched:
        print(f"Внимание: {unmatched} заметок не привязаны к доменам "
              f"(добавьте @<домен> и повторите consolidate)")
    conn.close()
    return 0


def cmd_lint(_args) -> int:
    lint = Path(__file__).resolve().parent / "lint_megamap.py"
    return subprocess.call([sys.executable, str(lint)])


def cmd_ui(args) -> int:
    import hermes_ui
    if args.port:
        sys.argv = [sys.argv[0], str(args.port)]
    else:
        sys.argv = [sys.argv[0]]
    return hermes_ui.main()


def cmd_bot(args) -> int:
    import telegram_bot
    sys.argv = [sys.argv[0]] + (["--setup"] if args.setup else [])
    return telegram_bot.main()


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="hermes", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="создать структуру хранилища").set_defaults(fn=cmd_init)
    p_add = sub.add_parser("add-raw", help="заметка → Triage-буфер")
    p_add.add_argument("text", nargs="?", help="текст заметки (или через stdin)")
    p_add.set_defaults(fn=cmd_add_raw)
    sub.add_parser("consolidate",
                   help="обработать буфер по слоям").set_defaults(fn=cmd_consolidate)
    sub.add_parser("decay", help="Decay & Audit").set_defaults(fn=cmd_decay)
    sub.add_parser("status", help="дашборд Слоя 1").set_defaults(fn=cmd_status)
    sub.add_parser("lint", help="проверка инвариантов").set_defaults(fn=cmd_lint)
    p_ui = sub.add_parser("ui", help="веб-дашборд (127.0.0.1)")
    p_ui.add_argument("port", nargs="?", type=int, help="порт (по умолчанию 8137)")
    p_ui.set_defaults(fn=cmd_ui)
    p_bot = sub.add_parser("bot", help="Telegram-бот приёмной")
    p_bot.add_argument("--setup", action="store_true",
                       help="первый написавший становится владельцем (chat_id → config)")
    p_bot.set_defaults(fn=cmd_bot)
    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
