#!/usr/bin/env python3
"""Сбор данных по бумаге с официального ISS API Московской биржи (iss.moex.com).

Тянет: паспорт бумаги (ISIN, уровень листинга, лот), рыночные данные (цена,
объём) и дивиденды. Только стандартная библиотека — запускается где угодно с
Python 3. Уважает HTTPS_PROXY и CA-бандл, если заданы (нужно в проксируемых
средах). Ничего не покупает и не требует ключей — только чтение публичных данных.

ВАЖНО про среду: под egress-политикой некоторых окружений (в т.ч. облачных
сессий Claude Code) `iss.moex.com` может отвечать 403 — это запрет прокси, не
ошибка сети. Тогда запускай скрипт на своей машине, где MOEX доступен.

Использование:
    python3 moex_fetch.py SBER
    python3 moex_fetch.py SBER --json      # весь ответ как JSON в stdout
    python3 moex_fetch.py LKOH GAZP        # несколько тикеров

Выход: человекочитаемая сводка (по умолчанию) или JSON (--json).
Код возврата: 0 — успех, 2 — сеть/доступ, 3 — бумага не найдена.
"""
import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

ISS = "https://iss.moex.com/iss"
UA = {"User-Agent": "birzha-analitik/1.0 (+harness; read-only)"}


def _opener():
    """HTTPS-opener с учётом HTTPS_PROXY и CA-бандла окружения."""
    ctx = ssl.create_default_context()
    ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if not ca and os.path.exists("/root/.ccr/ca-bundle.crt"):
        ca = "/root/.ccr/ca-bundle.crt"
    if ca and os.path.exists(ca):
        try:
            ctx.load_verify_locations(ca)
        except Exception:
            pass
    handlers = [urllib.request.HTTPSHandler(context=ctx)]
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"https": proxy, "http": proxy}))
    return urllib.request.build_opener(*handlers)


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with _opener().open(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _rows(block):
    """ISS отдаёт {columns:[...], data:[[...]]} — собираем в список словарей."""
    cols = block.get("columns", [])
    return [dict(zip(cols, row)) for row in block.get("data", [])]


def fetch(ticker):
    t = ticker.upper()
    out = {"ticker": t}

    sec_url = (
        f"{ISS}/engines/stock/markets/shares/securities/{t}.json"
        "?iss.meta=off&iss.only=securities,marketdata"
    )
    data = _get(sec_url)
    secs = _rows(data.get("securities", {}))
    mkt = _rows(data.get("marketdata", {}))
    if not secs:
        raise LookupError(f"бумага {t} не найдена в режиме shares MOEX")

    s = secs[0]
    out["profile"] = {
        "SECID": s.get("SECID"),
        "SECNAME": s.get("SECNAME"),
        "ISIN": s.get("ISIN"),
        "LISTLEVEL": s.get("LISTLEVEL"),
        "LOTSIZE": s.get("LOTSIZE"),
        "FACEVALUE": s.get("FACEVALUE"),
        "PREVPRICE": s.get("PREVPRICE"),
    }
    m = mkt[0] if mkt else {}
    out["market"] = {
        "LAST": m.get("LAST"),
        "LASTCHANGEPRCNT": m.get("LASTCHANGEPRCNT"),
        "VALTODAY": m.get("VALTODAY"),
        "WAPRICE": m.get("WAPRICE"),
        "UPDATETIME": m.get("UPDATETIME"),
    }

    try:
        div = _get(f"{ISS}/securities/{t}/dividends.json?iss.meta=off")
        out["dividends"] = _rows(div.get("dividends", {}))[-8:]  # последние выплаты
    except Exception as e:
        out["dividends_error"] = str(e)

    out["source"] = sec_url
    return out


def summarize(o):
    p, m = o.get("profile", {}), o.get("market", {})
    lines = [
        f"=== {o['ticker']}  {p.get('SECNAME') or ''} ===",
        f"ISIN: {p.get('ISIN')}  уровень листинга: {p.get('LISTLEVEL')}  лот: {p.get('LOTSIZE')}",
        f"Цена LAST: {m.get('LAST')}  изм.%: {m.get('LASTCHANGEPRCNT')}  "
        f"объём(руб): {m.get('VALTODAY')}  обновлено: {m.get('UPDATETIME')}",
        f"PREVPRICE: {p.get('PREVPRICE')}  WAPRICE: {m.get('WAPRICE')}",
    ]
    divs = o.get("dividends")
    if divs:
        lines.append("Дивиденды (последние):")
        for d in divs:
            lines.append(
                f"  {d.get('registryclosedate')}: {d.get('value')} {d.get('currencyid','')}"
            )
    elif o.get("dividends_error"):
        lines.append(f"Дивиденды: недоступно ({o['dividends_error']})")
    lines.append(f"Источник: {o['source']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="MOEX ISS: данные по бумаге (read-only)")
    ap.add_argument("tickers", nargs="+", help="тикеры MOEX, напр. SBER LKOH")
    ap.add_argument("--json", action="store_true", help="вывести сырой JSON")
    args = ap.parse_args()

    results, rc = [], 0
    for t in args.tickers:
        try:
            results.append(fetch(t))
        except LookupError as e:
            print(f"[{t}] не найдено: {e}", file=sys.stderr)
            rc = max(rc, 3)
        except urllib.error.HTTPError as e:
            hint = (
                " — вероятно egress-политика окружения (403). Запусти на своей машине."
                if e.code == 403
                else ""
            )
            print(f"[{t}] HTTP {e.code}: {e.reason}{hint}", file=sys.stderr)
            rc = max(rc, 2)
        except (urllib.error.URLError, ssl.SSLError, OSError) as e:
            print(f"[{t}] сеть/доступ: {e} — возможно, MOEX закрыт egress-политикой.",
                  file=sys.stderr)
            rc = max(rc, 2)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print("\n\n".join(summarize(o) for o in results) if results
              else "нет данных (см. ошибки выше)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
