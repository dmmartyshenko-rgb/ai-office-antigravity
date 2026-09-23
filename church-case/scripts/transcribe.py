#!/usr/bin/env python3
"""Расшифровка всех аудио из manifest → private/work/transcripts/<sha256>.json.

    pip install faster-whisper          # один раз (нужен и ffmpeg для .opus)
    python3 transcribe.py [--model large-v3] [--device cpu|cuda] [--limit N]

Каждый файл: {sha256, path, model, language, duration, segments:[{start,end,text}], text}.
Уже расшифрованные пропускаются. Имя файла = sha256 оригинала, поэтому
расшифровка навсегда привязана к конкретному неизменённому аудио.
Расшифровка — черновик машины: цитаты для эпизодов переслушиваются человеком.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import MANIFEST, PRIVATE, TRANSCRIPTS, dump_json, load_json  # noqa: E402

# Подсказка модели: лексика дела, чтобы не искажались термины и имена.
PROMPT = ("Разговор о церкви, епископ, пастор, община, Евангелие, Господь, "
          "власть, благословение, покаяние, ЕЛЦАИ, лютеране.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("FAIL: нет faster-whisper. Установи: pip install faster-whisper (и ffmpeg)")
        return 1
    manifest = load_json(MANIFEST, {})
    todo = [(h, e) for h, e in manifest.items()
            if e["kind"] == "audio" and not (TRANSCRIPTS / f"{h}.json").is_file()]
    if args.limit:
        todo = todo[:args.limit]
    print(f"к расшифровке: {len(todo)}")
    if not todo:
        return 0
    model = WhisperModel(args.model, device=args.device,
                         compute_type="int8" if args.device != "cuda" else "float16")
    for i, (h, e) in enumerate(todo, 1):
        path = PRIVATE / e["paths"][0]  # пути в manifest — относительно private/
        t0 = time.time()
        segments, info = model.transcribe(str(path), language="ru", initial_prompt=PROMPT,
                                          vad_filter=True, word_timestamps=False)
        segs = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
                for s in segments]
        dump_json(TRANSCRIPTS / f"{h}.json", {
            "sha256": h, "path": e["paths"][0], "model": args.model,
            "language": info.language, "duration": round(info.duration, 1),
            "segments": segs, "text": " ".join(s["text"] for s in segs)})
        print(f"[{i}/{len(todo)}] {e['paths'][0]} {info.duration:.0f}s за {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
