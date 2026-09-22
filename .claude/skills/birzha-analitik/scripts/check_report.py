#!/usr/bin/env python3
"""Проверка готовности инвест-отчёта харнеса birzha-analitik.

Отчёт «готов», только если:
- присутствуют все обязательные разделы;
- не осталось шаблонных заглушек ({{...}}, ЗАПОЛНИТЬ, <источник>);
- достаточно источников-ссылок (http/https) и дат (ГГГГ-ММ-ДД);
- есть строка Human-in-the-Loop про решение человека.

Пропуск данных, честно помеченный `⛔ нет доступа`, заглушкой НЕ считается —
это допустимое состояние (первоисточник недостижим), а не забытое поле.

Использование: python3 check_report.py <путь-к-отчёту.md>
Код возврата: 0 — OK, 1 — есть нарушения (печатаются), 2 — файла нет.
"""
import re
import sys
from pathlib import Path

REQUIRED_SECTIONS = [
    "## Краткое резюме",
    "## Часть 1. Фундаментальный анализ",
    "### 1.2 Финансовые показатели",
    "## Часть 2. Отраслевой анализ и риски",
    "### 2.2 Карта рисков",
    "### 2.3 Оценка против безрисковой ставки",
    "## Заключение",
    "## Human-in-the-Loop",
    "## Источники",
]
STUB_PATTERNS = [
    (r"\{\{.*?\}\}", "шаблонная вставка {{...}}"),
    (r"ЗАПОЛНИТЬ", "маркер ЗАПОЛНИТЬ"),
    (r"<источник>", "плейсхолдер <источник>"),
    (r"<url>", "плейсхолдер <url>"),
]
MIN_SOURCES = 3   # минимум разных ссылок-источников
MIN_DATES = 2     # минимум дат получения данных


def check(path: Path):
    errors = []
    text = path.read_text(encoding="utf-8")

    for sec in REQUIRED_SECTIONS:
        if sec not in text:
            errors.append(f"нет обязательного раздела: «{sec}»")

    for pat, name in STUB_PATTERNS:
        hits = re.findall(pat, text, flags=re.IGNORECASE)
        if hits:
            errors.append(f"осталась заглушка ({name}): {len(hits)} шт. — "
                          f"напр. {hits[0][:40]!r}")

    urls = set(re.findall(r"https?://[^\s)>\]]+", text))
    if len(urls) < MIN_SOURCES:
        errors.append(f"мало источников-ссылок: {len(urls)} (нужно ≥ {MIN_SOURCES}). "
                      f"Каждая цифра — с URL. Недостижимое помечай ⛔ нет доступа.")

    dates = re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", text)
    if len(dates) < MIN_DATES:
        errors.append(f"мало дат получения данных: {len(dates)} (нужно ≥ {MIN_DATES})")

    if "Решение" not in text or ("человек" not in text and "человеком" not in text):
        errors.append("нет строки Human-in-the-Loop про решение человека")

    return errors


def main():
    if len(sys.argv) != 2:
        print("использование: python3 check_report.py <путь-к-отчёту.md>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"FAIL: нет файла {path}", file=sys.stderr)
        return 2

    errors = check(path)
    if errors:
        print(f"FAIL: {len(errors)} нарушений в {path.name}:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"OK: отчёт {path.name} заполнен — разделы на месте, источники и даты есть, "
          f"заглушек нет, гейт Human-in-the-Loop присутствует.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
