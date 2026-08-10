#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
send_for_approval.py — Human-in-the-Loop шлюз исходящих документов.

ЖЁСТКОЕ ПРАВИЛО (CLAUDE.md §1.5): ни одно письмо/претензия/жалоба/иск не
покидает систему без ЯВНОГО одобрения человека. Этот скрипт — единственный
разрешённый путь исходящих. Сам он НИКУДА НЕ ОТПРАВЛЯЕТ по сети — он лишь ведёт
очередь согласования в data/outbox/ и фиксирует решение человека.

Жизненный цикл документа:
    submit  → статус PENDING_APPROVAL (кладётся в data/outbox/<id>/)
    review  → показать человеку сводку (адресат, суть, требования, способ отправки)
    approve → статус APPROVED (человек подтвердил; можно отправлять вручную)
    reject  → статус REJECTED (с причиной, на доработку)

Отправку выполняет человек вручную (заказное с описью / под расписку / ГИС ЖКХ /
e-mail). Скрипт печатает инструкцию, но действие совершает человек.

Использование:
    # поставить документ в очередь согласования
    python3 send_for_approval.py submit --file draft.md \
        --to "УК «Пример», ИНН 0000000000" \
        --subject "Претензия по переплате за содержание" \
        --method "Заказное письмо с описью вложения" \
        --requirements "Перерасчёт 90.45 руб.; ответ в 10 дней"

    python3 send_for_approval.py list                 # очередь
    python3 send_for_approval.py review <id>          # карточка на согласование
    python3 send_for_approval.py approve <id> --by "Иванов И.И."
    python3 send_for_approval.py reject  <id> --reason "Добавить расчёт неустойки"

Только стандартная библиотека. Проверка состязательной верификации: скрипт
предупредит, если в метаданных документа не отмечено прохождение Adversarial
verification (AGENTS.md §4).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTBOX = ROOT / "data" / "outbox"

STATUS_PENDING = "PENDING_APPROVAL"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _new_id() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def _meta_path(doc_dir: Path) -> Path:
    return doc_dir / "meta.json"


def _load_meta(doc_dir: Path) -> dict:
    return json.loads(_meta_path(doc_dir).read_text(encoding="utf-8"))


def _save_meta(doc_dir: Path, meta: dict) -> None:
    _meta_path(doc_dir).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_submit(args) -> int:
    src = Path(args.file)
    if not src.exists():
        print(json.dumps({"error": f"Файл документа не найден: {src}"}, ensure_ascii=False))
        return 2
    OUTBOX.mkdir(parents=True, exist_ok=True)
    doc_id = _new_id()
    doc_dir = OUTBOX / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    dest = doc_dir / src.name
    shutil.copy2(src, dest)

    meta = {
        "id": doc_id,
        "status": STATUS_PENDING,
        "created_at": _now(),
        "document_file": src.name,
        "to": args.to,
        "subject": args.subject,
        "method": args.method,
        "requirements": args.requirements,
        "adversarial_verified": bool(args.verified),
        "history": [{"at": _now(), "event": "submit", "status": STATUS_PENDING}],
    }
    _save_meta(doc_dir, meta)

    warn = ""
    if not meta["adversarial_verified"]:
        warn = ("ВНИМАНИЕ: документ НЕ отмечен как прошедший состязательную проверку "
                "(AGENTS.md §4). Рекомендуется прогнать Агент №1 ↔ Агент №2 до готовности.")
    print(json.dumps({
        "status": "queued",
        "id": doc_id,
        "path": str(doc_dir),
        "message": "Документ поставлен в очередь согласования. Отправка ТОЛЬКО после approve человеком.",
        "warning": warn,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_list(args) -> int:
    if not OUTBOX.exists():
        print(json.dumps({"queue": []}, ensure_ascii=False, indent=2))
        return 0
    items = []
    for d in sorted(OUTBOX.iterdir()):
        if d.is_dir() and _meta_path(d).exists():
            m = _load_meta(d)
            items.append({"id": m["id"], "status": m["status"],
                          "subject": m.get("subject"), "to": m.get("to"),
                          "verified": m.get("adversarial_verified")})
    print(json.dumps({"queue": items}, ensure_ascii=False, indent=2))
    return 0


def cmd_review(args) -> int:
    doc_dir = OUTBOX / args.id
    if not _meta_path(doc_dir).exists():
        print(json.dumps({"error": f"Документ не найден: {args.id}"}, ensure_ascii=False))
        return 2
    m = _load_meta(doc_dir)
    doc_text = (doc_dir / m["document_file"]).read_text(encoding="utf-8", errors="replace")
    print("═" * 64)
    print("КАРТОЧКА СОГЛАСОВАНИЯ (Human-in-the-Loop)")
    print("═" * 64)
    print(f"ID:            {m['id']}")
    print(f"Статус:        {m['status']}")
    print(f"Адресат:       {m.get('to')}")
    print(f"Тема:          {m.get('subject')}")
    print(f"Требования:    {m.get('requirements')}")
    print(f"Способ отправки: {m.get('method')}")
    print(f"Состязат. проверка: {'да' if m.get('adversarial_verified') else 'НЕТ (!)'}")
    print("-" * 64)
    print("ТЕКСТ ДОКУМЕНТА:")
    print("-" * 64)
    print(doc_text)
    print("═" * 64)
    print("Для одобрения: send_for_approval.py approve", m["id"], "--by \"ФИО\"")
    print("Для отклонения: send_for_approval.py reject", m["id"], "--reason \"...\"")
    return 0


def cmd_approve(args) -> int:
    doc_dir = OUTBOX / args.id
    if not _meta_path(doc_dir).exists():
        print(json.dumps({"error": f"Документ не найден: {args.id}"}, ensure_ascii=False))
        return 2
    m = _load_meta(doc_dir)
    m["status"] = STATUS_APPROVED
    m["approved_by"] = args.by
    m["approved_at"] = _now()
    m["history"].append({"at": _now(), "event": "approve", "by": args.by, "status": STATUS_APPROVED})
    _save_meta(doc_dir, m)
    print(json.dumps({
        "status": STATUS_APPROVED,
        "id": m["id"],
        "approved_by": args.by,
        "next_action": f"Отправьте документ ВРУЧНУЮ способом: {m.get('method')}. "
                       "Сохраните квитанцию об отправке/опись в этой же папке.",
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_reject(args) -> int:
    doc_dir = OUTBOX / args.id
    if not _meta_path(doc_dir).exists():
        print(json.dumps({"error": f"Документ не найден: {args.id}"}, ensure_ascii=False))
        return 2
    m = _load_meta(doc_dir)
    m["status"] = STATUS_REJECTED
    m["reject_reason"] = args.reason
    m["history"].append({"at": _now(), "event": "reject", "reason": args.reason, "status": STATUS_REJECTED})
    _save_meta(doc_dir, m)
    print(json.dumps({
        "status": STATUS_REJECTED,
        "id": m["id"],
        "reason": args.reason,
        "next_action": "Доработать документ (при необходимости — новый цикл состязательной проверки) и submit заново.",
    }, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Human-in-the-Loop шлюз исходящих документов.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("submit", help="Поставить документ в очередь согласования.")
    s.add_argument("--file", required=True, help="Путь к файлу документа (md/txt/docx-текст).")
    s.add_argument("--to", required=True, help="Адресат (УК/ГЖИ/суд), реквизиты.")
    s.add_argument("--subject", required=True, help="Тема/суть документа.")
    s.add_argument("--method", default="Заказное письмо с описью вложения",
                   help="Способ отправки (заказное/ГИС ЖКХ/под расписку/e-mail).")
    s.add_argument("--requirements", default="", help="Ключевые требования/суммы/сроки.")
    s.add_argument("--verified", action="store_true",
                   help="Отметить, что документ прошёл состязательную проверку (AGENTS.md §4).")
    s.set_defaults(func=cmd_submit)

    sub.add_parser("list", help="Показать очередь согласования.").set_defaults(func=cmd_list)

    r = sub.add_parser("review", help="Карточка документа на согласование.")
    r.add_argument("id")
    r.set_defaults(func=cmd_review)

    a = sub.add_parser("approve", help="Одобрить документ (человек).")
    a.add_argument("id")
    a.add_argument("--by", required=True, help="ФИО одобрившего.")
    a.set_defaults(func=cmd_approve)

    j = sub.add_parser("reject", help="Отклонить документ на доработку.")
    j.add_argument("id")
    j.add_argument("--reason", required=True, help="Причина отклонения.")
    j.set_defaults(func=cmd_reject)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
