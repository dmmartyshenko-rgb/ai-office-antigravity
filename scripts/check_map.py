#!/usr/bin/env python3
"""Проверка целостности трёхслойной мегакарты (map/).

Правила (см. .claude/skills/megamap/SKILL.md):
- каждый домен из таблицы INDEX имеет карту в map/domains/ и журнал в map/journal/;
- каждая карта домена упомянута в INDEX (сирот нет);
- карта домена содержит обязательные разделы;
- INDEX не длиннее одного экрана (60 строк);
- журнал не пуст и начинается с заголовка.

Выход 0 — карта целостна, 1 — есть нарушения (все печатаются).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP = ROOT / "map"
INDEX = MAP / "INDEX.md"
DOMAINS = MAP / "domains"
JOURNAL = MAP / "journal"

REQUIRED_SECTIONS = ["## Статус", "## Ветка", "## Цель", "## Артефакты",
                     "## Следующий шаг", "## Риски / открытые вопросы"]
INDEX_MAX_LINES = 60

errors = []

if not INDEX.is_file():
    print(f"FAIL: нет {INDEX.relative_to(ROOT)}")
    sys.exit(1)

index_text = INDEX.read_text(encoding="utf-8")
index_lines = index_text.splitlines()
if len(index_lines) > INDEX_MAX_LINES:
    errors.append(f"INDEX.md длиннее одного экрана: {len(index_lines)} строк "
                  f"(лимит {INDEX_MAX_LINES}) — пора укрупнять домены")

# Домены — из ссылок вида domains/<имя>.md в таблице INDEX
index_domains = set(re.findall(r"domains/([a-z0-9-]+)\.md", index_text))
if not index_domains:
    errors.append("в INDEX.md не найдено ни одной ссылки domains/<домен>.md")

disk_domains = {p.stem for p in DOMAINS.glob("*.md")} if DOMAINS.is_dir() else set()
journal_domains = {p.stem for p in JOURNAL.glob("*.md")} if JOURNAL.is_dir() else set()

for d in sorted(index_domains - disk_domains):
    errors.append(f"домен «{d}» есть в INDEX, но нет map/domains/{d}.md")
for d in sorted(disk_domains - index_domains):
    errors.append(f"map/domains/{d}.md не упомянут в INDEX (сирота)")
for d in sorted(index_domains - journal_domains):
    errors.append(f"домен «{d}» без журнала map/journal/{d}.md")

for d in sorted(index_domains & disk_domains):
    text = (DOMAINS / f"{d}.md").read_text(encoding="utf-8")
    for sec in REQUIRED_SECTIONS:
        if sec not in text:
            errors.append(f"map/domains/{d}.md: нет раздела «{sec.lstrip('# ')}»")

for d in sorted(journal_domains):
    text = (JOURNAL / f"{d}.md").read_text(encoding="utf-8").strip()
    if not text.startswith("# "):
        errors.append(f"map/journal/{d}.md: пуст или не начинается с заголовка")

if errors:
    print(f"FAIL: {len(errors)} нарушений целостности карты:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)

print(f"OK: карта целостна — {len(index_domains)} доменов, "
      f"INDEX {len(index_lines)}/{INDEX_MAX_LINES} строк")
