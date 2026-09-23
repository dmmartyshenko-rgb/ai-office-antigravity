#!/usr/bin/env python3
"""Расшифровка всех аудио из manifest → private/work/transcripts/<sha256>.json.

    Mac (Apple Silicon, быстро):  pip install mlx-whisper; brew install ffmpeg
    Прочие:                       pip install faster-whisper (+ ffmpeg)
    python3 transcribe.py [--backend auto|mlx|faster] [--model …] [--limit N]

--backend auto: mlx-whisper, если установлен (Mac M1–M4), иначе faster-whisper.

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


def make_backend(args):
    """Возвращает run(path) -> (segments, language, model) или None."""
    seg = lambda st, en, tx: {"start": round(st, 2), "end": round(en, 2), "text": tx.strip()}
    if args.backend in ("auto", "mlx"):
        try:
            import mlx_whisper
            repo = args.model or "mlx-community/whisper-large-v3-turbo"

            def run_mlx(path):
                r = mlx_whisper.transcribe(path, path_or_hf_repo=repo, language="ru",
                                           initial_prompt=PROMPT)
                return [seg(s["start"], s["end"], s["text"]) for s in r["segments"]], r.get("language", "ru"), repo
            return run_mlx
        except ImportError:
            if args.backend == "mlx":
                return None
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    name = args.model or "large-v3"
    model = WhisperModel(name, device=args.device,
                         compute_type="float16" if args.device == "cuda" else "int8")

    def run_fw(path):
        segments, info = model.transcribe(path, language="ru", initial_prompt=PROMPT, vad_filter=True)
        return [seg(s.start, s.end, s.text) for s in segments], info.language, name
    return run_fw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["auto", "mlx", "faster"], default="auto")
    ap.add_argument("--model", default="", help="по умолчанию: whisper-large-v3-turbo (mlx) / large-v3 (faster)")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    manifest = load_json(MANIFEST, {})
    todo = [(h, e) for h, e in manifest.items()
            if e["kind"] == "audio" and not (TRANSCRIPTS / f"{h}.json").is_file()]
    if args.limit:
        todo = todo[:args.limit]
    print(f"к расшифровке: {len(todo)}")
    if not todo:
        return 0
    run = make_backend(args)
    if run is None:
        print("FAIL: нет движка. Mac: pip install mlx-whisper; иначе pip install faster-whisper. И ffmpeg.")
        return 1
    errors = 0
    for i, (h, e) in enumerate(todo, 1):
        path = PRIVATE / e["paths"][0]  # пути в manifest — относительно private/
        t0 = time.time()
        try:
            segs, lang, model_name = run(str(path))
        except Exception as ex:  # битый файл не должен останавливать сотни остальных
            errors += 1
            print(f"[{i}/{len(todo)}] ОШИБКА {e['paths'][0]}: {ex}")
            continue
        duration = segs[-1]["end"] if segs else 0.0
        dump_json(TRANSCRIPTS / f"{h}.json", {
            "sha256": h, "path": e["paths"][0], "model": model_name,
            "language": lang, "duration": round(duration, 1),
            "segments": segs, "text": " ".join(s["text"] for s in segs)})
        print(f"[{i}/{len(todo)}] {e['paths'][0]} {duration:.0f}s за {time.time()-t0:.0f}s")
    if errors:
        print(f"WARN: {errors} файлов не расшифровано — запусти снова или проверь ffmpeg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
