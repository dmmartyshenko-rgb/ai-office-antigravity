#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
monitor_tariffs.py — Мониторинг тарифов ЖКХ и изменений законодательства.

Читает публичные источники (сайт РЭК/комитета по тарифам региона, ГИС ЖКХ,
публикации об изменениях НПА), сравнивает с текущей data/tariffs.json и при
изменении добавляет НОВУЮ версию тарифа в history (с датой вступления и
источником), а также пишет сигнал в claude-progress.md.

ВАЖНО (CLAUDE.md §1.5): скрипт только ЧИТАЕТ публичные данные и обновляет
локальный tariffs.json. Он НИЧЕГО НИКУДА НЕ ОТПРАВЛЯЕТ. Любое изменение тарифа
из внешнего источника перед применением требует подтверждения человеком
(флаг --apply); по умолчанию — режим предпросмотра (dry-run).

Источники задаются в data/sources.json (см. пример там же). Скрипт бережно
относится к сети: таймауты, вежливый User-Agent, без параллельных запросов.

Использование:
    python3 monitor_tariffs.py                     # dry-run: показать, что изменилось
    python3 monitor_tariffs.py --sources data/sources.json
    python3 monitor_tariffs.py --apply             # применить изменения (после проверки человеком)
    python3 monitor_tariffs.py --check-only        # только проверить доступность источников

Зависимости: только стандартная библиотека (urllib). Парсинг конкретных
страниц РЭК/ГИС ЖКХ индивидуален — реализуйте extract-функцию под источник в
data/sources.json (поле 'pattern' — регэксп с группой 'rate').
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARIFFS = ROOT / "data" / "tariffs.json"
DEFAULT_SOURCES = ROOT / "data" / "sources.json"
PROGRESS = ROOT / "claude-progress.md"
USER_AGENT = "ZHKH-Agent/1.0 (local tariff monitor; contact: owner)"
TIMEOUT = 20


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def parse_num(s: str) -> float | None:
    s = s.replace("\xa0", "").replace(" ", "").replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def load_sources(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("sources", [])


def extract_rate(html: str, source: dict) -> float | None:
    """Извлекает тариф из HTML по регэкспу источника (группа 'rate' или первая группа)."""
    pattern = source.get("pattern")
    if not pattern:
        return None
    m = re.search(pattern, html, re.I | re.S)
    if not m:
        return None
    try:
        raw = m.groupdict().get("rate") or m.group(1)
    except IndexError:
        raw = m.group(0)
    return parse_num(raw)


def check_sources(sources: list[dict]) -> list[dict]:
    results = []
    for src in sources:
        entry = {"service": src.get("service"), "url": src.get("url")}
        try:
            html = fetch(src["url"])
            entry["reachable"] = True
            entry["found_rate"] = extract_rate(html, src)
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, KeyError) as e:
            entry["reachable"] = False
            entry["error"] = str(e)
        results.append(entry)
    return results


def compute_changes(tariffs: dict, checks: list[dict], today: str) -> list[dict]:
    """Сравнить найденные тарифы с текущими; вернуть список изменений."""
    services = tariffs.get("services", {})
    changes = []
    for chk in checks:
        key = chk.get("service")
        new_rate = chk.get("found_rate")
        if not chk.get("reachable") or new_rate is None or key not in services:
            continue
        history = services[key].get("history", [])
        current = history[-1]["rate"] if history else None
        if current is None or abs(float(current) - new_rate) > 1e-6:
            changes.append({
                "service": key,
                "title": services[key].get("title", key),
                "old_rate": current,
                "new_rate": new_rate,
                "source": chk.get("url"),
                "effective_from": today,
            })
    return changes


def apply_changes(tariffs_path: Path, tariffs: dict, changes: list[dict]) -> None:
    for ch in changes:
        svc = tariffs["services"][ch["service"]]
        svc.setdefault("history", []).append({
            "effective_from": ch["effective_from"],
            "rate": ch["new_rate"],
            "source": ch["source"],
            "added_by": "monitor_tariffs.py",
        })
    tariffs.setdefault("_meta", {})["last_updated"] = changes[0]["effective_from"] if changes else \
        tariffs.get("_meta", {}).get("last_updated")
    tariffs_path.write_text(json.dumps(tariffs, ensure_ascii=False, indent=2), encoding="utf-8")


def log_progress(changes: list[dict], applied: bool) -> None:
    if not PROGRESS.exists() or not changes:
        return
    stamp = dt.date.today().isoformat()
    verb = "ПРИМЕНЕНО" if applied else "ОБНАРУЖЕНО (dry-run, требуется approval)"
    lines = [f"\n> [monitor {stamp}] {verb}: изменения тарифов:"]
    for ch in changes:
        lines.append(f">   - {ch['title']}: {ch['old_rate']} → {ch['new_rate']} (источник: {ch['source']})")
    with PROGRESS.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Мониторинг тарифов ЖКХ и обновление tariffs.json.")
    p.add_argument("--tariffs", default=str(DEFAULT_TARIFFS))
    p.add_argument("--sources", default=str(DEFAULT_SOURCES))
    p.add_argument("--apply", action="store_true", help="Применить изменения к tariffs.json (после проверки человеком).")
    p.add_argument("--check-only", action="store_true", help="Только проверить доступность источников.")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    tariffs_path = Path(args.tariffs)
    sources_path = Path(args.sources)
    if not tariffs_path.exists():
        print(json.dumps({"error": f"tariffs.json не найден: {tariffs_path}"}, ensure_ascii=False))
        return 2

    sources = load_sources(sources_path)
    if not sources:
        msg = (f"Источники не заданы. Создайте {sources_path} по образцу (data/sources.json). "
               "Пока мониторинг работать не будет — заполните URL сайта РЭК региона / ГИС ЖКХ.")
        print(json.dumps({"status": "no_sources", "hint": msg}, ensure_ascii=False, indent=2))
        return 0

    checks = check_sources(sources)
    if args.check_only:
        print(json.dumps({"checks": checks}, ensure_ascii=False, indent=2))
        return 0

    tariffs = json.loads(tariffs_path.read_text(encoding="utf-8"))
    today = dt.date.today().isoformat()
    changes = compute_changes(tariffs, checks, today)

    if args.apply and changes:
        apply_changes(tariffs_path, tariffs, changes)
        log_progress(changes, applied=True)
    elif changes:
        log_progress(changes, applied=False)

    result = {
        "checked": len(checks),
        "reachable": sum(1 for c in checks if c.get("reachable")),
        "changes": changes,
        "applied": bool(args.apply and changes),
        "next_action": (
            "Изменения применены к tariffs.json. Перепроверьте затронутые квитанции verify_invoice.py."
            if (args.apply and changes) else
            ("Обнаружены изменения тарифов. Проверьте их вручную и запустите с --apply для применения."
             if changes else "Изменений тарифов не обнаружено.")
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
