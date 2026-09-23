#!/usr/bin/env python3
"""Лексический сканер: кандидаты в эпизоды из сообщений и расшифровок.

    python3 scan_candidates.py [--author "Имя в чате"] [--lexicon свой.json]

Ищет в словах Ответчика маркеры категорий (см. LEXICON) → private/work/candidates.jsonl.
Это НЕ эпизоды: сканер не понимает контекста, иронии, цитирования. Каждого
кандидата Аналитик читает в контексте и принимает или отклоняет с причиной.
Словарь дополняется под дело: private/work/lexicon.json того же формата.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (CANDIDATES, MESSAGES, TRANSCRIPTS, WORK, load_json,  # noqa: E402
                    read_jsonl, write_jsonl)

LEXICON = {
    # Оскорбления и уничижительные ярлыки в адрес людей
    "insult": [r"\bвор\w*", r"\bукрал\w*", r"\bмошенни\w*", r"\bпредател\w*", r"\bиуд\w*",
               r"\bдурак\w*", r"\bидиот\w*", r"\bтвар\w*", r"\bсволоч\w*", r"\bкрыс\w*",
               r"\bнедоросл\w*", r"\bнедоросн\w*", r"\bгнид\w*", r"\bпес\b|\bпсы\b|\bпсин\w*",
               r"\bлжец\w*", r"\bлжив\w*", r"\bбес\w*ся\b|\bбесноват\w*"],
    # Лагерный/блатной жаргон и брань
    "jargon": [r"\bбеспредел\w*", r"\bкозл\w*", r"\bстукач\w*", r"\bпонят\w*\s+по\s+понятиям|\bпо\s+понятиям",
               r"\bшестер\w*", r"\bфраер\w*", r"\bбаклан\w*", r"\bчушк\w*|\bчушок", r"\bпахан\w*",
               r"\bзону\b|\bна\s+зоне", r"\bмаст[ьи]\b", r"\bбазар\w*", r"\bразвел\w*"],
    # Говорение от имени Бога / присвоение Божьего суда
    "divine_authority": [r"бог\w*(?:\s+\w+){0,2}\s+(?:сказал|говорит|накажет|покарает|осудит|не\s+простит)",
                         r"господ\w*(?:\s+\w+){0,2}\s+(?:сказал|говорит|накажет|покарает|открыл)",
                         r"(?:проклят|прокл[яи]н\w*|анафем\w*)", r"воля\s+божья", r"от\s+имени\s+бога",
                         r"бог\s+(?:мне\s+)?(?:открыл|показал)", r"суд\s+божий"],
    # Власть от Бога / политика — для проверки последовательности
    "power": [r"власт\w*\s+от\s+бога", r"всякая\s+власть", r"не\s+от\s+бога",
              r"президент\w*", r"путин\w*", r"трамп\w*|байден\w*", r"\bсша\b|америк\w*",
              r"украин\w*", r"запад\w*"],
    "war": [r"\bсво\b", r"войн\w*", r"фронт\w*", r"блиндаж\w*", r"окоп\w*", r"арми\w*",
            r"гуманитар\w*", r"мобилиз\w*"],
    # Присвоение власти, угрозы, требования подчинения
    "authority_claim": [r"я\s+(?:епископ|здесь\s+решаю|решаю)", r"подчин\w*", r"отлуч\w*",
                        r"запрещ\w*\s+в\s+служени\w*", r"лишу|лишить\s+сана", r"выгон\w*",
                        r"(?:подам|подаю)\s+в\s+суд", r"пожалеешь|пожалеете"],
    # Обвинения в преступлениях без суда
    "accusation": [r"украл\w*\s+(?:организац|церк|общин|деньг)", r"преступ\w*", r"посад\w*",
                   r"уголовн\w*"],
    "alcohol": [r"пьян\w*", r"выпи\w*", r"водк\w*", r"\bпил\b|\bпили\b", r"трезв\w*"],
}


def compile_lexicon(extra: dict) -> dict:
    lex = {k: list(v) for k, v in LEXICON.items()}
    for k, v in (extra or {}).items():
        lex.setdefault(k, []).extend(v)
    return {k: re.compile("|".join(f"(?:{p})" for p in v), re.I) for k, v in lex.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--author", action="append", default=[],
                    help="имя Ответчика в чате (можно несколько); по умолчанию — все авторы")
    ap.add_argument("--lexicon", type=Path, default=WORK / "lexicon.json")
    args = ap.parse_args()
    lex = compile_lexicon(load_json(args.lexicon, {}))
    out = []
    for m in read_jsonl(MESSAGES):
        if args.author and m["author"] not in args.author:
            continue
        cats = sorted(k for k, rx in lex.items() if rx.search(m["text"]))
        if cats:
            out.append({"kind": "message", "ref": f"msg:{m['n']}", "ts": m["ts"],
                        "author": m["author"], "categories": cats, "text": m["text"][:1000]})
    for tp in sorted(TRANSCRIPTS.glob("*.json")) if TRANSCRIPTS.is_dir() else []:
        t = load_json(tp)
        for s in t["segments"]:
            cats = sorted(k for k, rx in lex.items() if rx.search(s["text"]))
            if cats:
                out.append({"kind": "audio", "ref": f"audio:{t['sha256']}@{s['start']:.1f}",
                            "path": t["path"], "start": s["start"], "end": s["end"],
                            "categories": cats, "text": s["text"]})
    write_jsonl(CANDIDATES, out)
    by = {}
    for c in out:
        for k in c["categories"]:
            by[k] = by.get(k, 0) + 1
    print(f"кандидатов: {len(out)} → {CANDIDATES}")
    print("по категориям: " + ", ".join(f"{k}={v}" for k, v in sorted(by.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
