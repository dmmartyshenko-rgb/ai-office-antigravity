#!/usr/bin/env python3
"""Фиксация веб-страницы как доказательства: снимок + HTML + текст + sha256.

    python3 capture_web.py URL [URL ...] [--label метка] [--profile ~/путь/профиль_Chrome]
                           [--wait 3] [--full-page]

Для каждого URL создаёт private/raw/web/<UTC-время>_<метка>/:
  page.png   — снимок (по умолчанию вся страница),
  page.html  — DOM после загрузки,
  page.txt   — видимый текст,
  meta.json  — URL, итоговый URL после редиректов, UTC-время, заголовок,
               User-Agent, sha256 каждого файла.
Все файлы вносятся в private/work/manifest.json (kind: web) до любой обработки.

--profile — постоянный профиль браузера для страниц за логином (VK и т. п.).
Скрипт только читает страницы: ничего не нажимает, не пишет, не отправляет.
Требуется: pip install playwright (браузер — установленный Chromium/Chrome;
путь можно задать через PLAYWRIGHT_BROWSERS_PATH или --executable).
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import MANIFEST, RAW, dump_json, load_json, sha256  # noqa: E402


def slug(text: str) -> str:
    s = re.sub(r"[^\w.-]+", "_", text, flags=re.UNICODE).strip("_")
    return s[:60] or "page"


def capture(page, url: str, out: Path, wait: float, full_page: bool) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(int(wait * 1000))
    (out / "page.html").write_text(page.content(), encoding="utf-8")
    (out / "page.txt").write_text(page.inner_text("body"), encoding="utf-8")
    page.screenshot(path=str(out / "page.png"), full_page=full_page)
    meta = {
        "url": url,
        "final_url": page.url,
        "status": resp.status if resp else None,
        "title": page.title(),
        "captured_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "user_agent": page.evaluate("navigator.userAgent"),
        "files": {},
    }
    for name in ("page.png", "page.html", "page.txt"):
        meta["files"][name] = sha256(out / name)
    dump_json(out / "meta.json", meta)
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--label", default="", help="метка для имени папки (иначе — из URL)")
    ap.add_argument("--profile", help="папка постоянного профиля браузера (страницы за логином)")
    ap.add_argument("--executable", help="путь к Chrome/Chromium, если не найден автоматически")
    ap.add_argument("--wait", type=float, default=3.0, help="секунд подождать после загрузки")
    ap.add_argument("--viewport-only", action="store_true", help="снимок только видимой области")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("нужен playwright: pip install playwright")

    manifest = load_json(MANIFEST, {})
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with sync_playwright() as p:
        kw = {"headless": True}
        if args.executable:
            kw["executable_path"] = args.executable
        if args.profile:
            ctx = p.chromium.launch_persistent_context(str(Path(args.profile).expanduser()), **kw)
            browser = None
        else:
            browser = p.chromium.launch(**kw)
            ctx = browser.new_context()
        page = ctx.new_page()
        for i, url in enumerate(args.urls, 1):
            name = f"{stamp}_{slug(args.label or url)}" + (f"_{i}" if len(args.urls) > 1 else "")
            out = RAW / "web" / name
            try:
                meta = capture(page, url, out, args.wait, not args.viewport_only)
            except Exception as e:  # одна битая страница не останавливает пакет
                print(f"ОШИБКА {url}: {e}")
                continue
            for fname, h in meta["files"].items():
                f = out / fname
                entry = manifest.setdefault(h, {"paths": [], "origin": f"web:{url}", "size": f.stat().st_size,
                                                "kind": "web", "registered": meta["captured_utc"]})
                rel = str(f.relative_to(RAW.parent))
                if rel not in entry["paths"]:
                    entry["paths"].append(rel)
            print(f"OK {url} → {out} (HTTP {meta['status']})")
        ctx.close()
        if browser:
            browser.close()
    dump_json(MANIFEST, manifest)


if __name__ == "__main__":
    main()
