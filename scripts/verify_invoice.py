#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_invoice.py — Паттерн "Loop-until-done".

Построчно сверяет начисления квитанции ЖКУ с официальными тарифами региона из
data/tariffs.json В ЦИКЛЕ до полной сходимости: каждая строка получает финальный
статус (нет 'pending'), считается суммарная переплата и перечень нарушений со
ссылками на НПА (см. AGENTS.md §3, CLAUDE.md §2-3).

Вход — квитанция в JSON (рекомендуется) или текст (эвристический парсер):

  Формат JSON (data/invoices/*.json):
  {
    "meta": {"account": "0000", "period": "2025-07", "area_m2": 54.3, "persons": 2},
    "lines": [
      {"service": "cold_water", "volume": 4.2, "rate": 42.15, "charged": 177.03},
      {"service": "maintenance", "volume": 54.3, "rate": 30.00, "charged": 1629.0}
    ]
  }
  'service' — ключ из tariffs.json ИЛИ произвольное название (сопоставится по словарю синонимов).

Использование:
    python3 verify_invoice.py data/invoices/2025-07.json
    python3 verify_invoice.py data/invoices/2025-07.json --tariffs data/tariffs.json
    python3 verify_invoice.py bill.txt --text        # эвристический парсер текста
    python3 verify_invoice.py bill.json --json        # машиночитаемый вывод

Статусы строки:
    ok             — начисление соответствует официальному тарифу
    overcharge     — тариф превышен (переплата), ссылка ПП №354 / ст.156 ЖК РФ
    no_oss         — услуга требует решения ОСС, но оно не подтверждено (навязанная)
    missing_tariff — нет эталонного тарифа в базе (нужно заполнить tariffs.json)
    unknown_service— услуга не сопоставлена (эскалация человеку)

Только стандартная библиотека. Ничего не отправляет, файлы не изменяет.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TOLERANCE = 0.02  # допуск округления при сравнении сумм (2 коп. на копейку/руб.)

# Синонимы названий услуг → ключ в tariffs.json
SYNONYMS = {
    "cold_water": [r"холодн\w*\s+вод", r"\bхвс\b", r"водоснабжени\w*\s+холодн"],
    "hot_water": [r"горяч\w*\s+вод", r"\bгвс\b"],
    "water_disposal": [r"водоотведени", r"канализаци"],
    "heating": [r"отоплени", r"теплов\w*\s+энерги", r"теплоснабжени"],
    "electricity": [r"электроснабжени", r"электроэнерги", r"\bэлектр"],
    "gas": [r"газоснабжени", r"\bгаз\b"],
    "tko": [r"\bтко\b", r"обращени\w*\s+с\s+тко", r"вывоз\w*\s+мусор", r"твёрд\w*\s+коммунальн"],
    "maintenance": [r"содержани\w*\s+жил", r"содержани\w*\s+общ", r"содержани\w*\s+и\s+ремонт"],
    "current_repair": [r"текущ\w*\s+ремонт"],
    "management": [r"управлени\w*\s+(?:мкд|дом)"],
    "capital_repair": [r"капитальн\w*\s+ремонт", r"\bкапремонт\b", r"взнос\w*\s+на\s+кап"],
    "intercom": [r"домофон"],
    "security": [r"охран", r"консьерж"],
    "video": [r"видеонаблюдени", r"видеокамер"],
}

NPA_HINT = {
    "communal_resource": "ПП РФ №354; тариф утверждает РЭК региона.",
    "maintenance": "ст.156, 162 ЖК РФ; ПП РФ №491 — размер по решению ОСС.",
    "management": "ст.162 ЖК РФ; ПП РФ №416 — по решению ОСС/договору.",
    "capital_repair": "ст.169-170 ЖК РФ — мин. размер устанавливает субъект РФ.",
}


def load_tariffs(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    services = dict(data.get("services", {}))
    # доп. услуги, требующие ОСС
    for key, item in data.get("additional_services_require_oss", {}).get("items", {}).items():
        services.setdefault(key, {
            "title": item.get("title", key),
            "category": "additional",
            "requires_oss": True,
            "history": ([{"effective_from": "0001-01-01", "rate": item["rate"]}]
                        if item.get("rate") is not None else []),
        })
    return services


def official_rate(service: dict, period: str | None) -> float | None:
    """Актуальный тариф на дату периода (последний effective_from <= период)."""
    history = service.get("history", [])
    if not history:
        return None
    key = (period or "9999-12") + "-01"  # период вида YYYY-MM → сравниваем как дату
    applicable = [h for h in history if h.get("effective_from", "0001-01-01") <= key]
    chosen = max(applicable, key=lambda h: h["effective_from"]) if applicable else \
        min(history, key=lambda h: h["effective_from"])
    return chosen.get("rate")


def match_service(name: str, tariffs: dict) -> str | None:
    """Сопоставить произвольное название услуги с ключом tariffs.json."""
    if name in tariffs:
        return name
    low = name.lower()
    for key, patterns in SYNONYMS.items():
        if key in tariffs and any(re.search(p, low) for p in patterns):
            return key
    # по совпадению title
    for key, svc in tariffs.items():
        if svc.get("title", "").lower() in low or low in svc.get("title", "").lower():
            return key
    return None


def resolve_line(line: dict, tariffs: dict, period: str | None) -> dict:
    """Один проход разрешения строки. Возвращает строку с полем 'status'."""
    raw_name = str(line.get("service", "")).strip()
    charged = _to_float(line.get("charged"))
    volume = _to_float(line.get("volume"))
    rate = _to_float(line.get("rate"))

    key = match_service(raw_name, tariffs)
    out = {
        "service_raw": raw_name,
        "service_key": key,
        "volume": volume,
        "rate_charged": rate,
        "charged": charged,
    }

    if key is None:
        out["status"] = "unknown_service"
        out["note"] = "Услуга не сопоставлена с базой. Эскалация человеку (не домысливать)."
        return out

    svc = tariffs[key]
    out["title"] = svc.get("title", key)
    out["category"] = svc.get("category")
    ref_rate = official_rate(svc, period)
    out["rate_official"] = ref_rate

    # Услуги, требующие подтверждения ОСС
    if svc.get("requires_oss") and not _oss_confirmed(svc):
        out["status"] = "no_oss"
        out["npa"] = NPA_HINT.get(svc.get("category"), "ст.44-48, 156 ЖК РФ")
        out["note"] = ("Требуется подтверждённое решение ОСС (реквизиты протокола). "
                       "В tariffs.json источник не подтверждён/ставка пуста — начисление под вопросом.")
        # если ставка всё же задана — посчитаем потенциальную сумму для справки
        if ref_rate and volume is not None:
            out["expected"] = round(volume * ref_rate, 2)
        return out

    if ref_rate is None:
        out["status"] = "missing_tariff"
        out["note"] = "Нет эталонного тарифа в базе — заполнить tariffs.json из официального источника."
        return out

    if volume is None or charged is None:
        out["status"] = "missing_tariff"
        out["note"] = "Недостаточно данных строки (объём/начислено). Не домысливать — уточнить у пользователя."
        return out

    expected = round(volume * ref_rate, 2)
    out["expected"] = expected
    diff = round(charged - expected, 2)
    out["overpayment"] = diff

    if diff > TOLERANCE:
        out["status"] = "overcharge"
        out["npa"] = NPA_HINT.get(svc.get("category"), "ПП РФ №354 / ст.156 ЖК РФ")
        out["note"] = (f"Переплата {diff:.2f} руб.: начислено {charged:.2f} при ожидаемом "
                       f"{expected:.2f} ({volume} × {ref_rate}).")
    elif diff < -TOLERANCE:
        out["status"] = "ok"
        out["note"] = f"Начислено меньше эталона на {abs(diff):.2f} руб. (не в ущерб собственнику)."
    else:
        out["status"] = "ok"
        out["note"] = "Соответствует официальному тарифу."
    return out


def _oss_confirmed(svc: dict) -> bool:
    """ОСС подтверждён, если в истории есть непустой source и заданная ставка."""
    for h in svc.get("history", []):
        src = str(h.get("source", "")).strip()
        if src and not src.upper().startswith("ЗАПОЛНИТЬ") and h.get("rate") is not None:
            return True
    return False


def _to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("\xa0", "").replace(" ", "").replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def parse_text_invoice(text: str) -> dict:
    """Эвристический парсер текстовой квитанции. Best-effort — предпочитайте JSON."""
    period = None
    m = re.search(r"(?:период|за)\s*[:\-]?\s*([А-Яа-я]+\s*20\d\d|20\d\d[-/.]\d{2})", text, re.I)
    if m:
        period = m.group(1)
    area = None
    m = re.search(r"площад\w*[^0-9]{0,15}(\d+[.,]?\d*)\s*(?:м2|кв)", text, re.I)
    if m:
        area = _to_float(m.group(1))

    lines = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        # ищем строки с услугой и хотя бы двумя числами (объём/тариф/сумма)
        nums = re.findall(r"\d+[.,]?\d*", raw.replace("\xa0", ""))
        if len(nums) >= 2 and match_service(raw, {k: {} for k in SYNONYMS}):
            vals = [_to_float(n) for n in nums]
            line = {"service": raw.strip()}
            # эвристика: последнее число — начислено; если 3+ чисел, [-3]=объём,[-2]=тариф
            line["charged"] = vals[-1]
            if len(vals) >= 3:
                line["volume"], line["rate"] = vals[-3], vals[-2]
            lines.append(line)
    return {"meta": {"period": period, "area_m2": area, "parsed_from": "text"}, "lines": lines}


def verify(invoice: dict, tariffs: dict, max_iter: int = 20) -> dict:
    """Loop-until-done: гоняем проходы, пока все строки не получат финальный статус."""
    period = (invoice.get("meta") or {}).get("period")
    period_norm = _normalize_period(period)
    lines = invoice.get("lines", [])

    resolved: list[dict] = [{"_pending": True, **ln} for ln in lines]
    iterations = 0
    while any(r.get("_pending") for r in resolved) and iterations < max_iter:
        iterations += 1
        for i, r in enumerate(resolved):
            if not r.get("_pending"):
                continue
            res = resolve_line(r, tariffs, period_norm)
            if res.get("status") and res["status"] != "pending":
                resolved[i] = res  # финализировано, снят _pending
    # то, что не сошлось (теоретически) — помечаем
    for i, r in enumerate(resolved):
        if r.get("_pending"):
            r.pop("_pending", None)
            r["status"] = "unknown_service"
            r["note"] = "Не удалось разрешить за отведённые итерации — эскалация человеку."
            resolved[i] = r

    total_overpayment = round(sum(
        r.get("overpayment", 0) for r in resolved if r.get("status") == "overcharge"), 2)
    violations = [r for r in resolved if r.get("status") in {"overcharge", "no_oss"}]

    return {
        "converged": iterations < max_iter,
        "iterations": iterations,
        "period": period,
        "lines": resolved,
        "summary": {
            "total_lines": len(resolved),
            "ok": sum(1 for r in resolved if r["status"] == "ok"),
            "overcharge": sum(1 for r in resolved if r["status"] == "overcharge"),
            "no_oss": sum(1 for r in resolved if r["status"] == "no_oss"),
            "missing_tariff": sum(1 for r in resolved if r["status"] == "missing_tariff"),
            "unknown_service": sum(1 for r in resolved if r["status"] == "unknown_service"),
            "total_overpayment_rub": total_overpayment,
            "violations_count": len(violations),
        },
        "next_action": (
            "Есть нарушения — подготовить претензию (AGENTS.md §4, состязательная проверка), "
            "затем send_for_approval.py."
            if violations else
            "Нарушений тарифа не выявлено. Проверить недостающие тарифы (missing_tariff) в tariffs.json."
        ),
    }


def _normalize_period(period: str | None) -> str | None:
    if not period:
        return None
    p = period.strip().lower()
    months = {
        "январ": "01", "феврал": "02", "март": "03", "апрел": "04", "ма": "05",
        "июн": "06", "июл": "07", "август": "08", "сентябр": "09", "октябр": "10",
        "ноябр": "11", "декабр": "12",
    }
    m = re.search(r"(20\d\d)[-/.]?(\d{2})", p)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    ym = re.search(r"([а-я]+)\w*\s*(20\d\d)", p)
    if ym:
        for stem, mm in months.items():
            if ym.group(1).startswith(stem):
                return f"{ym.group(2)}-{mm}"
    return None


def render_report(result: dict) -> str:
    s = result["summary"]
    out = []
    out.append("═" * 64)
    out.append("АУДИТ КВИТАНЦИИ ЖКУ  (verify_invoice.py — Loop-until-done)")
    out.append("═" * 64)
    out.append(f"Период: {result.get('period') or '—'} · "
               f"Сходимость: {'да' if result['converged'] else 'НЕТ'} за {result['iterations']} итер.")
    out.append("-" * 64)
    icon = {"ok": "✓", "overcharge": "✗", "no_oss": "⚠", "missing_tariff": "?", "unknown_service": "…"}
    for r in result["lines"]:
        out.append(f"[{icon.get(r['status'], '·')}] {r['status'].upper():15} | "
                   f"{r.get('title') or r.get('service_raw', '')[:40]}")
        if r.get("note"):
            out.append(f"      {r['note']}")
        if r.get("npa"):
            out.append(f"      НПА: {r['npa']}")
    out.append("-" * 64)
    out.append(f"Всего строк: {s['total_lines']} | OK: {s['ok']} | "
               f"Переплата: {s['overcharge']} | Без ОСС: {s['no_oss']} | "
               f"Нет тарифа: {s['missing_tariff']} | Неизвестно: {s['unknown_service']}")
    out.append(f"ИТОГО ПЕРЕПЛАТА: {s['total_overpayment_rub']:.2f} руб. | "
               f"Нарушений: {s['violations_count']}")
    out.append("-" * 64)
    out.append("Действие: " + result["next_action"])
    out.append("═" * 64)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Loop-until-done: сверка квитанции ЖКУ с тарифами.")
    parser.add_argument("invoice", help="Путь к квитанции (JSON или текст с --text).")
    parser.add_argument("--tariffs", default=None, help="Путь к tariffs.json (по умолчанию data/tariffs.json).")
    parser.add_argument("--text", action="store_true", help="Считать вход текстовой квитанцией (эвристика).")
    parser.add_argument("--json", action="store_true", help="Вывести результат в JSON.")
    args = parser.parse_args(argv)

    inv_path = Path(args.invoice)
    if not inv_path.exists():
        print(json.dumps({"error": f"Файл не найден: {inv_path}"}, ensure_ascii=False))
        return 2

    tariffs_path = Path(args.tariffs) if args.tariffs else \
        inv_path.resolve().parents[1] / "data" / "tariffs.json"
    if not tariffs_path.exists():
        # fallback: относительно этого скрипта
        tariffs_path = Path(__file__).resolve().parent.parent / "data" / "tariffs.json"
    if not tariffs_path.exists():
        print(json.dumps({"error": f"tariffs.json не найден (искали {tariffs_path})"}, ensure_ascii=False))
        return 2

    tariffs = load_tariffs(tariffs_path)

    if args.text or inv_path.suffix.lower() in {".txt", ".md"}:
        invoice = parse_text_invoice(inv_path.read_text(encoding="utf-8", errors="replace"))
    else:
        invoice = json.loads(inv_path.read_text(encoding="utf-8"))

    if not invoice.get("lines"):
        print(json.dumps({"error": "В квитанции не найдено строк начислений. "
                                   "Проверьте формат или используйте JSON."}, ensure_ascii=False))
        return 1

    result = verify(invoice, tariffs)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
