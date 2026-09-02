#!/usr/bin/env python3
"""Hermes Megamap — жёсткая валидация инвариантов (CI/CLI).

Правила:
- INDEX.md существует и содержит <= 60 строк;
- каждый домен из INDEX имеет существующие файлы карты (domains/) и журнала (logs/);
- в domains/ нет сирот — каждая карта упомянута в INDEX;
- в каждой карте присутствуют все обязательные разделы своего типа;
- у активных проектов «## Следующий шаг» и у тёплых контактов
  «## Следующий социальный шаг» непусты.

Выход 0 — зелёный, 1 — нарушения (все печатаются).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metabolism import find_root, parse_index  # noqa: E402

INDEX_MAX_LINES = 60
REQUIRED = {
    "project": ["## Статус", "## Где лежит", "## Цель", "## Артефакты",
                "## Следующий шаг", "## Риски и блокеры"],
    "relationship": ["## Круг / Роль", "## Статус отношений",
                     "## Friend Health Score", "## Ключевой контекст и ресурсы",
                     "## Следующий социальный шаг", "## Блокеры"],
}


def section_body(text: str, header: str) -> str:
    m = re.search(rf"^{re.escape(header)}\s*\n(.*?)(?=^## |\Z)", text,
                  re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def main() -> int:
    root = find_root()
    errors = []

    index = root / "INDEX.md"
    if not index.is_file():
        print(f"FAIL: нет {index}")
        return 1
    n_lines = len(index.read_text(encoding="utf-8").splitlines())
    if n_lines > INDEX_MAX_LINES:
        errors.append(f"INDEX.md: {n_lines} строк (лимит {INDEX_MAX_LINES}) — "
                      f"пора укрупнять или архивировать домены")

    domains = parse_index(root)
    if not domains:
        errors.append("INDEX.md: не найдено ни одной строки домена в таблице")

    # INDEX ↔ файлы
    for slug, info in sorted(domains.items()):
        for key, layer in (("map", "карта"), ("log", "журнал")):
            rel = info[key]
            if not rel:
                errors.append(f"INDEX: у «{slug}» не указан файл ({layer})")
            elif not (root / rel).is_file():
                errors.append(f"«{slug}»: {layer} {rel} не существует")

    # Сироты в domains/
    referenced = {info["map"] for info in domains.values() if info["map"]}
    for p in sorted((root / "domains").rglob("*.md")):
        rel = str(p.relative_to(root))
        if rel not in referenced:
            errors.append(f"{rel}: карта-сирота — нет строки в INDEX.md")

    # Обязательные разделы + непустой следующий шаг
    for slug, info in sorted(domains.items()):
        rel = info["map"]
        if not rel or not (root / rel).is_file():
            continue
        kind = "project" if "/projects/" in rel else "relationship"
        text = (root / rel).read_text(encoding="utf-8")
        for sec in REQUIRED[kind]:
            if not re.search(rf"^{re.escape(sec)}\s*$", text, re.MULTILINE):
                errors.append(f"{rel}: нет обязательного раздела «{sec}»")

        active = info["status"].lower().startswith("актив")
        warm = "тепл" in section_body(text, "## Статус отношений").lower() \
               or "тёпл" in section_body(text, "## Статус отношений").lower()
        step_hdr = "## Следующий шаг" if kind == "project" \
                   else "## Следующий социальный шаг"
        step = section_body(text, step_hdr)
        needs_step = active if kind == "project" else (warm or active)
        if needs_step and step in ("", "—", "-"):
            errors.append(f"{rel}: «{step_hdr}» пуст, а домен "
                          f"{'активен' if kind == 'project' else 'тёплый/активный'} — "
                          f"заполните перед завершением задачи")

    if errors:
        print(f"FAIL: {len(errors)} нарушений инвариантов Hermes Megamap:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"OK: мегакарта целостна — {len(domains)} доменов, "
          f"INDEX {n_lines}/{INDEX_MAX_LINES} строк")
    return 0


if __name__ == "__main__":
    sys.exit(main())
