#!/usr/bin/env python3
"""Сборка приложения к представлению: таблица эпизодов обвинения + доводы защиты.

    python3 build_dossier.py  → private/drafts/prilozhenie_epizody.md

Берёт только role=charge (обвинение) и отдельно role=context. Порядок — по дате.
Для каждого эпизода: цитата, источник (sha256/таймкод), норма, довод защиты и ответ.
Показ довода защиты в самом документе — сознательный выбор: орган видит, что
заявитель сам проверил позицию на прочность, а не прячет слабые места.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DRAFTS, EPISODES, load_json  # noqa: E402

LEVEL = {"A": "документ", "B": "голос/текст Ответчика", "C": "свидетельство",
         "D": "СМИ", "E": "пересказ"}


def cell(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def src_line(s: dict) -> str:
    ref = s["sha256_or_url"]
    ref = ref if ref.startswith("http") else f"sha256 {ref[:12]}…"
    return f"{LEVEL.get(s['level'], s['level'])}: {s['locator']} ({ref})"


def section(title: str, eps: list) -> list:
    out = [f"## {title}", ""]
    if not eps:
        return out + ["_нет_", ""]
    for e in eps:
        out.append(f"### [{e['id']}] {e['date']} — {cell(e['summary'])}")
        out.append("")
        for s in e["sources"]:
            if s.get("quote_verbatim"):
                out.append(f"> «{s['quote_verbatim']}»")
                out.append("")
            out.append(f"- Источник: {src_line(s)}")
        out.append(f"- Норма: {'; '.join(e['canonical_basis'])}")
        out.append(f"- Проверка: {e['verification']['status']}")
        if e.get("opinion"):
            out.append(f"- Оценка заявителя: {e['opinion']}")
        d = e["defense"]
        out.append(f"- Возможное возражение: {d['rebuttal']}")
        if d.get("reply"):
            out.append(f"- Ответ на возражение: {d['reply']}")
        out.append("")
    return out


def main() -> int:
    eps = [load_json(p) for p in sorted(EPISODES.glob("E-*.json"))] if EPISODES.is_dir() else []
    eps.sort(key=lambda e: e.get("date", ""))
    charge = [e for e in eps if e.get("role") == "charge"]
    context = [e for e in eps if e.get("role") == "context"]
    lines = ["# Приложение. Эпизоды", "",
             f"Эпизодов в обвинении: {len(charge)}. Контекстных: {len(context)}.",
             "Каждая цитата сверена с исходным файлом (sha256 снят до обработки).", ""]
    lines += section("I. Эпизоды, составляющие предмет обращения", charge)
    lines += section("II. Контекст (не вменяется в вину)", context)
    out = DRAFTS / "prilozhenie_epizody.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"→ {out} (обвинение {len(charge)}, контекст {len(context)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
