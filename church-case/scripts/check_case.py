#!/usr/bin/env python3
"""Судья-валидатор: проверка эпизодов и черновиков дела.

    python3 check_case.py            # всё: эпизоды + черновики
    python3 check_case.py --strict   # WARN тоже валит (перед подписью)

Эпизоды (private/episodes/E-*.json):
  E1 обязательные поля и допустимые значения (schema/episode.schema.json);
  E2 sha256 источника есть в manifest.json (цепочка хранения);
  E3 дословная цитата реально присутствует в сообщении / расшифровке (антигаллюцинация);
  E4 цитата из аудио переслушана человеком (quote_checked_by_ear);
  E5 criminal_record → только verified_primary;
  E6 обвинение (charge) не может быть unverified и должно иметь ≥2 источника A–C или 1 A/B (1 Тим 5:19);
  E7 обвинение с defense.assessment=breaks или pending не допускается;
  E8 power/war_involvement → legal_risk_reviewed=true;
  E9 третьи лица без согласия → только role=context;
  E10 double_standard → есть linked_episodes, и они существуют;
  E11 в summary нет оценочных ярлыков (им место в opinion).
Черновики (private/drafts/*.md):
  D1 каждая ссылка [E-NNN] ведёт на существующий эпизод с role=charge или context;
  D2 рискованные ярлыки вне кавычек → WARN (ст. 152 ГК РФ / 128.1 УК РФ);
  D3 категоричность без доказательств («очевидно», «всем известно») → WARN.

Выход 0 — чисто, 1 — есть FAIL (или WARN при --strict).
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (CASE, DRAFTS, EPISODES, MANIFEST, MESSAGES, TRANSCRIPTS,  # noqa: E402
                    load_json, norm, read_jsonl)

SCHEMA = load_json(CASE / "schema" / "episode.schema.json")
PROPS = SCHEMA["properties"]
ENUM = {k: set(v["enum"]) for k, v in PROPS.items() if "enum" in v}
LEVELS = set(PROPS["sources"]["items"]["properties"]["level"]["enum"])
VSTATUS = set(PROPS["verification"]["properties"]["status"]["enum"])
DASSESS = set(PROPS["defense"]["properties"]["assessment"]["enum"])

LABELS = re.compile(r"\b(вор\w*|мошенни\w*|пьяниц\w*|алкогол\w*|преступни\w*|уголовни\w*|"
                    r"лжец\w*|лицемер\w*|сектант\w*|бандит\w*|зек\w*|негодя\w*|"
                    r"двойн\w+\s+стандарт\w*|сквернослов\w*|гнил\w+\s+слов\w*)", re.I)
CATEGORICAL = re.compile(r"\b(очевидно|всем\s+известно|несомненно|доказано|общеизвестно|"
                         r"без\s+сомнения)\b", re.I)
QUOTED = re.compile(r"«[^»]*»|\"[^\"]*\"|“[^”]*”|^>.*$", re.M)

fails, warns = [], []


def fail(where, msg):
    fails.append(f"FAIL {where}: {msg}")


def warn(where, msg):
    warns.append(f"WARN {where}: {msg}")


def source_texts():
    """locator → текст, в котором должна найтись цитата."""
    texts = {f"msg:{m['n']}": m["text"] for m in read_jsonl(MESSAGES)}
    audio = {}
    if TRANSCRIPTS.is_dir():
        for tp in TRANSCRIPTS.glob("*.json"):
            t = load_json(tp)
            audio[t["sha256"]] = t
    return texts, audio


def quote_found(src, texts, audio) -> bool | None:
    """True/False — проверено; None — источник вне переписки (URL, документ)."""
    q = norm(src.get("quote_verbatim", ""))
    loc = src["locator"]
    if loc.startswith("msg:"):
        return q in norm(texts.get(loc, ""))
    m = re.match(r"audio:([0-9a-f]{64})@([\d.]+)", loc)
    if m:
        t = audio.get(m.group(1))
        if not t:
            return False
        at = float(m.group(2))
        window = " ".join(s["text"] for s in t["segments"] if s["end"] >= at - 30 and s["start"] <= at + 90)
        return q in norm(window)
    return None


def check_episode(path: Path, ep: dict, ids: dict, manifest: dict, texts, audio):
    w = path.name
    for key in SCHEMA["required"]:
        if key not in ep or ep[key] in ("", [], None):
            fail(w, f"нет поля {key}")
    if fails and fails[-1].startswith(f"FAIL {w}: нет поля"):
        return
    if not re.fullmatch(r"E-\d{3}", ep["id"]) or path.stem != ep["id"]:
        fail(w, "id должен быть E-NNN и совпадать с именем файла")
    for k in ("category", "role", "statement_type"):
        if ep[k] not in ENUM[k]:
            fail(w, f"{k}={ep[k]!r} не из {sorted(ENUM[k])}")
    ver = ep["verification"].get("status")
    if ver not in VSTATUS:
        fail(w, f"verification.status={ver!r}")
    assess = ep["defense"].get("assessment")
    if assess not in DASSESS:
        fail(w, f"defense.assessment={assess!r}")
    if not ep["defense"].get("rebuttal", "").strip():
        fail(w, "нет довода защиты (defense.rebuttal) — эпизод не прошёл red team")

    strong = 0
    for i, s in enumerate(ep["sources"]):
        sw = f"{w} src[{i}]"
        if s.get("level") not in LEVELS:
            fail(sw, f"level={s.get('level')!r}")
            continue
        ref = s.get("sha256_or_url", "")
        is_url = ref.startswith("http")
        if not is_url and ref not in manifest:  # E2
            fail(sw, "sha256 нет в manifest.json — источник вне цепочки хранения")
        if ep["statement_type"] == "quote":
            if not s.get("quote_verbatim", "").strip():
                fail(sw, "эпизод-цитата без quote_verbatim")
            else:
                found = quote_found(s, texts, audio)  # E3
                if found is False:
                    fail(sw, f"цитата не найдена в источнике {s['locator']}: «{s['quote_verbatim'][:60]}…»")
                if s["locator"].startswith("audio:") and not s.get("quote_checked_by_ear"):  # E4
                    (fail if ep["role"] == "charge" else warn)(sw, "цитата из аудио не переслушана человеком")
        if s["level"] in ("A", "B"):
            strong += 2
        elif s["level"] == "C":
            strong += 1

    if ep["category"] == "criminal_record" and ver != "verified_primary":  # E5
        fail(w, "уголовное прошлое/приговор — только verified_primary (судебный акт)")
    if ep["role"] == "charge":
        if ver == "unverified":  # E6
            fail(w, "обвинение на непроверенном")
        if strong < 2:
            fail(w, "обвинению нужны ≥2 независимых источника A–C или один A/B (1 Тим 5:19)")
        if assess in ("breaks", "pending"):  # E7
            fail(w, f"обвинение с defense.assessment={assess} — доработать или вывести в context")
    political = (ep["category"] == "war_involvement" or ep.get("political") is True
                 or re.search(r"власт|президент|сша|росси|войн|арми|фронт", ep["summary"], re.I))
    if political:
        if not ep.get("legal_risk_reviewed"):  # E8
            fail(w, "политический эпизод без legal_risk_reviewed=true (ст. 207.3/280.3 УК РФ)")
    for tp in ep.get("third_parties", []):  # E9
        if not tp.get("consent") and ep["role"] == "charge":
            fail(w, f"третье лицо «{tp.get('who')}» без согласия в обвинении — только context")
    if ep["category"] == "double_standard":  # E10
        linked = ep.get("linked_episodes", [])
        if not linked:
            fail(w, "двойной стандарт без linked_episodes: с чем сопоставляем?")
        for l in linked:
            if l not in ids:
                fail(w, f"linked_episodes: {l} не существует")
    m = LABELS.search(ep["summary"])  # E11
    if m:
        warn(w, f"ярлык «{m.group(0)}» в summary — перенеси в opinion")


def check_draft(path: Path, ids: dict):
    text = path.read_text(encoding="utf-8")
    for ref in sorted(set(re.findall(r"\[(E-\d{3})\]", text))):  # D1
        if ref not in ids:
            fail(path.name, f"ссылка [{ref}] на несуществующий эпизод")
        elif ids[ref]["role"] == "rejected":
            fail(path.name, f"ссылка [{ref}] на отклонённый эпизод")
    bare = QUOTED.sub(" ", text)
    for m in LABELS.finditer(bare):  # D2
        line = bare[:m.start()].count("\n") + 1
        warn(path.name, f"стр.{line}: ярлык «{m.group(0)}» вне цитаты — утверждение о факте? "
                        f"(ст. 152 ГК РФ) Переформулируй: цитата Ответчика или «расцениваю как»")
    for m in CATEGORICAL.finditer(bare):  # D3
        line = bare[:m.start()].count("\n") + 1
        warn(path.name, f"стр.{line}: «{m.group(0)}» — категоричность без ссылки на эпизод")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    manifest = load_json(MANIFEST, {})
    texts, audio = source_texts()
    eps = {}
    for p in sorted(EPISODES.glob("E-*.json")) if EPISODES.is_dir() else []:
        try:
            eps[p] = load_json(p)
        except ValueError as e:
            fail(p.name, f"битый JSON: {e}")
    ids = {ep.get("id"): ep for ep in eps.values() if isinstance(ep, dict)}
    for p, ep in eps.items():
        check_episode(p, ep, ids, manifest, texts, audio)
    for p in sorted(DRAFTS.glob("*.md")) if DRAFTS.is_dir() else []:
        check_draft(p, ids)

    charges = [e for e in ids.values() if e.get("role") == "charge"]
    print(f"эпизодов: {len(ids)} (обвинение: {len(charges)}, "
          f"контекст: {sum(e.get('role') == 'context' for e in ids.values())}, "
          f"отклонено: {sum(e.get('role') == 'rejected' for e in ids.values())}); "
          f"файлов в manifest: {len(manifest)}")
    for line in fails + warns:
        print(line)
    bad = bool(fails) or (args.strict and bool(warns))
    print("ИТОГ: " + ("НЕ ГОТОВО" if bad else "чисто") + f" — FAIL {len(fails)}, WARN {len(warns)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
