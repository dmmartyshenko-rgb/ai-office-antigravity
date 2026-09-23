"""Общие пути и утилиты харнеса church-case."""
import hashlib
import json
import os
import re
from pathlib import Path

CASE = Path(__file__).resolve().parent.parent
# Материалы дела живут вне git. Путь можно переопределить (например, на
# зашифрованный диск): CHURCH_CASE_PRIVATE=/path/to/private
PRIVATE = Path(os.environ.get("CHURCH_CASE_PRIVATE", CASE / "private"))
RAW = PRIVATE / "raw"
WORK = PRIVATE / "work"
EPISODES = PRIVATE / "episodes"
DRAFTS = PRIVATE / "drafts"
MANIFEST = WORK / "manifest.json"
MESSAGES = WORK / "messages.jsonl"
TRANSCRIPTS = WORK / "transcripts"
CANDIDATES = WORK / "candidates.jsonl"

AUDIO_EXT = {".opus", ".ogg", ".m4a", ".mp3", ".wav", ".aac", ".amr", ".mp4", ".webm"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path, default=None):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_jsonl(path: Path):
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def norm(text: str) -> str:
    """Нормализация для сверки цитат: регистр, ё/е, пунктуация, пробелы."""
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()
