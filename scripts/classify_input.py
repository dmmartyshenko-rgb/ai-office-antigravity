#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
classify_input.py — Паттерн "Classify-and-act".

Принимает входящий документ (текст / PDF-квитанция / фото уведомления) и
определяет категорию + ветку действий (см. AGENTS.md §2).

Категории: invoice | pretension | court_order | notice_board |
           service_cutoff | unknown

Использование:
    python3 classify_input.py path/to/file.pdf
    python3 classify_input.py path/to/photo.jpg
    python3 classify_input.py path/to/notice.txt
    echo "текст квитанции..." | python3 classify_input.py -
    python3 classify_input.py file.pdf --json      # только JSON в stdout

Зависимости: только стандартная библиотека. PDF/OCR — опционально:
    pip install pdfplumber pillow pytesseract   (не обязательно)
Если извлечь текст не удалось — категория 'unknown' и эскалация человеку.
Ничего не отправляет и не изменяет — только классифицирует.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ── Ветки действий по категориям (совпадает с AGENTS.md §2) ──────────────────
NEXT_ACTION = {
    "invoice": "Запустить verify_invoice.py: сверка с data/tariffs.json, поиск переплат и навязанных услуг.",
    "pretension": "Проверить основание долга (договор управления ст.162 ЖК РФ, решение ОСС); подготовить мотивированный ответ; состязательная проверка (AGENTS.md §4).",
    "court_order": "СРОЧНО: срок на возражения — 10 дней со дня получения (ст.128-129 ГПК РФ). Готовить возражения относительно исполнения. НЕМЕДЛЕННАЯ эскалация человеку.",
    "notice_board": "Проверить легитимность ОСС: кворум (ст.45-46 ЖК РФ), повестка, сроки уведомления (ст.45), форма протокола.",
    "service_cutoff": "Проверить законность ограничения: наличие судебного решения, порядок/сроки предупреждения (разд.XI ПП РФ №354). Незаконная угроза → жалоба в ГЖИ/прокуратуру.",
    "unknown": "Эскалация человеку: не распознано. Запросить недостающий документ/уточнение. Ничего не домысливать.",
}

# ── Сигнатуры категорий: (вес, регэксп) ──────────────────────────────────────
SIGNATURES = {
    "court_order": [
        (5, r"судебн\w*\s+приказ"),
        (4, r"мирово\w*\s+суд"),
        (3, r"\bвзыскать\b"),
        (3, r"вынес\w*\s+судебный\s+приказ"),
        (2, r"№\s*дела|дело\s*№"),
        (2, r"судебн\w*\s+участ\w*"),
    ],
    "service_cutoff": [
        (5, r"приостановлени\w*\s+(?:предоставлени\w*\s+)?коммунальн\w*"),
        (5, r"ограничени\w*\s+(?:предоставлени\w*\s+)?коммунальн\w*"),
        (4, r"\bотключени\w*\b"),
        (3, r"будет\s+(?:ограничен\w*|приостановлен\w*|отключен\w*)"),
        (2, r"уведомлени\w*\s+о\s+(?:задолженност|ограничени|приостановлени)"),
    ],
    "pretension": [
        (5, r"\bпретензи\w*\b"),
        (4, r"\bтребовани\w*\s+(?:об\s+уплате|о\s+погашени|оплат)"),
        (4, r"досудебн\w*\s+(?:претензи|требовани|порядок)"),
        (3, r"в\s+течени\w*\s+\d+\s+(?:кален\w*\s+)?дн"),
        (3, r"задолженност\w*\s+в\s+размере"),
        (2, r"предлагаем\s+(?:погасить|оплатить)"),
    ],
    "notice_board": [
        (5, r"обще\w*\s+собрани\w*\s+собственник"),
        (4, r"\bОСС\b|повестк\w*\s+дня"),
        (4, r"уведомлени\w*\s+о\s+проведени\w*\s+собрани"),
        (3, r"\bголосовани\w*\b|бюллетен\w*"),
        (3, r"очно-заочн\w*|заочн\w*\s+голосовани"),
        (2, r"\bкворум\b"),
    ],
    "invoice": [
        (5, r"лицев\w*\s+сч[её]т"),
        (4, r"\bначислен\w*\b"),
        (4, r"\bк\s+оплате\b|итого\s+к\s+оплате"),
        (3, r"\bГВС\b|\bХВС\b|горяч\w*\s+вод|холодн\w*\s+вод"),
        (3, r"\bотоплени\w*\b|содержани\w*\s+жил|водоотведени"),
        (3, r"\bОДН\b|\bИПУ\b|\bКР\s+на\s+СОИ\b"),
        (2, r"период\w*\s*[:\-]|расчётн\w*\s+период|за\s+\w+\s+20\d\d"),
        (2, r"тариф\w*|норматив\w*\s+потреблени"),
    ],
}

# Порог уверенности: ниже — категория 'unknown'
MIN_SCORE = 5


def extract_text(path: Path) -> tuple[str, str]:
    """Возвращает (text, note). Поддержка txt/md, PDF (опц.), изображений (опц. OCR)."""
    suffix = path.suffix.lower()

    if suffix in {".txt", ".md", ".text", ""}:
        return path.read_text(encoding="utf-8", errors="replace"), ""

    if suffix == ".pdf":
        # Пробуем pdfplumber, затем PyPDF2. Оба опциональны.
        try:
            import pdfplumber  # type: ignore

            with pdfplumber.open(str(path)) as pdf:
                text = "\n".join((page.extract_text() or "") for page in pdf.pages)
            return text, "" if text.strip() else "PDF без текстового слоя (возможно скан) — нужен OCR."
        except ImportError:
            pass
        try:
            import PyPDF2  # type: ignore

            reader = PyPDF2.PdfReader(str(path))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            return text, "" if text.strip() else "PDF без текстового слоя (возможно скан) — нужен OCR."
        except ImportError:
            return "", "Для PDF установите: pip install pdfplumber (или PyPDF2)."

    if suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}:
        try:
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore

            text = pytesseract.image_to_string(Image.open(str(path)), lang="rus+eng")
            return text, "" if text.strip() else "OCR не извлёк текст — проверьте качество фото."
        except ImportError:
            return "", "Для фото установите OCR: pip install pillow pytesseract (+ tesseract-ocr с рус. языком)."

    return "", f"Неподдерживаемый формат: {suffix}"


def classify(text: str) -> dict:
    low = text.lower()
    scores: dict[str, int] = {}
    hits: dict[str, list[str]] = {}
    for category, sigs in SIGNATURES.items():
        total = 0
        matched: list[str] = []
        for weight, pattern in sigs:
            if re.search(pattern, low):
                total += weight
                matched.append(pattern)
        if total:
            scores[category] = total
            hits[category] = matched

    if not scores:
        best, best_score = "unknown", 0
    else:
        best = max(scores, key=scores.get)
        best_score = scores[best]
        if best_score < MIN_SCORE:
            best = "unknown"

    total_all = sum(scores.values()) or 1
    confidence = round(best_score / total_all, 2) if best != "unknown" else 0.0

    return {
        "category": best,
        "confidence": confidence,
        "score": best_score,
        "all_scores": dict(sorted(scores.items(), key=lambda kv: -kv[1])),
        "signals": hits.get(best, []),
        "next_action": NEXT_ACTION[best],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify-and-act: сортировка входящих ЖКХ-документов.")
    parser.add_argument("input", help="Путь к файлу (txt/pdf/изображение) или '-' для чтения текста из stdin.")
    parser.add_argument("--json", action="store_true", help="Вывести только JSON.")
    args = parser.parse_args(argv)

    note = ""
    if args.input == "-":
        text = sys.stdin.read()
        source = "<stdin>"
    else:
        path = Path(args.input)
        if not path.exists():
            print(json.dumps({"error": f"Файл не найден: {path}"}, ensure_ascii=False))
            return 2
        text, note = extract_text(path)
        source = str(path)

    if not text.strip():
        result = {
            "category": "unknown",
            "confidence": 0.0,
            "source": source,
            "note": note or "Пустой ввод / текст не извлечён.",
            "next_action": NEXT_ACTION["unknown"],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    result = classify(text)
    result["source"] = source
    if note:
        result["note"] = note

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
