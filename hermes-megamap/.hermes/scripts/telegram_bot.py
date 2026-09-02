#!/usr/bin/env python3
"""Hermes Megamap — Telegram-бот приёмной (голос и текст → Triage-буфер).

Только стандартная библиотека (long polling через urllib). Бот — часть этапа
TRIAGE: он пишет ТОЛЬКО в buffer/ и cold/sources/voice/, никогда не трогает
domains/ и INDEX.md.

Настройка:
  1. Создайте бота у @BotFather, получите токен.
  2. export TELEGRAM_BOT_TOKEN="123456:ABC..."  (токен в git не хранить!)
  3. Запустите: python3 .hermes/scripts/telegram_bot.py  (или hermes_cli.py bot)
  4. Напишите боту /start — он ответит вашим chat_id; впишите его в
     .hermes/config.json → telegram.allowed_chat_ids. До этого бот ничего
     не принимает (белый список пуст = приём закрыт).

Голосовые: скачиваются в cold/sources/voice/ (оригинал сохраняется всегда),
расшифровка — локальным faster-whisper или openai-whisper, если установлены
(pip install faster-whisper). Без них заметка-заглушка со ссылкой на файл
остаётся в буфере до ручной расшифровки.
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import metabolism as mb  # noqa: E402

ROOT = mb.find_root()
API = "https://api.telegram.org"

HELP = (
    "Hermes Megamap — приёмная внешней памяти.\n\n"
    "Пришлите текст или голосовое — заметка попадёт в Triage-буфер.\n"
    "Директивы в первой строке:\n"
    "@домен — привязать к домену\n"
    "@new-project slug | Имя | Суть\n"
    "@new-contact slug | ФИО | Круг\n"
    "Внутри: «! Заголовок», «Почему: …», «Следующий шаг: …»\n\n"
    "Разбор буфера по слоям — команда consolidate в дашборде или CLI."
)


def _token() -> str:
    import os
    tok = os.environ.get("TELEGRAM_BOT_TOKEN") \
        or mb.load_config(ROOT).get("telegram", {}).get("token", "")
    if not tok:
        sys.exit("Нет токена: export TELEGRAM_BOT_TOKEN=... (бот от @BotFather)")
    return tok


def tg(token: str, method: str, timeout: int = 65, **params):
    data = urllib.parse.urlencode(
        {k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
         for k, v in params.items()}).encode()
    req = urllib.request.Request(f"{API}/bot{token}/{method}", data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read().decode())
    if not resp.get("ok"):
        raise RuntimeError(f"{method}: {resp}")
    return resp["result"]


def download_voice(token: str, file_id: str) -> Path:
    """Оригинал голосовой — в холодный архив (cold/sources/voice/)."""
    info = tg(token, "getFile", file_id=file_id)
    url = f"{API}/file/bot{token}/{info['file_path']}"
    dest_dir = ROOT / "cold" / "sources" / "voice"
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(info["file_path"]).suffix or ".ogg"
    dest = dest_dir / f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}_{file_id[:10]}{ext}"
    with urllib.request.urlopen(url, timeout=120) as r:
        dest.write_bytes(r.read())
    return dest


def transcribe(path: Path) -> str | None:
    """faster-whisper → openai-whisper → None (расшифровка недоступна)."""
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("small", compute_type="int8")
        segments, _ = model.transcribe(str(path), language="ru")
        text = " ".join(s.text.strip() for s in segments).strip()
        return text or None
    except ImportError:
        pass
    except Exception as e:  # модель есть, но упала — честно сообщаем
        print(f"faster-whisper: {e}")
    try:
        import whisper
        model = whisper.load_model("small")
        text = model.transcribe(str(path), language="ru")["text"].strip()
        return text or None
    except ImportError:
        return None
    except Exception as e:
        print(f"whisper: {e}")
        return None


def register_owner(chat_id: int) -> None:
    """Вписывает chat_id владельца в .hermes/config.json (режим --setup)."""
    cfg_path = ROOT / ".hermes" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.is_file() else {}
    cfg.setdefault("telegram", {})["allowed_chat_ids"] = [chat_id]
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")


def handle_update(update: dict, token: str, allowed: list,
                  transcriber=transcribe, downloader=download_voice,
                  setup: bool = False) -> str | None:
    """Обрабатывает один update; возвращает текст ответа пользователю.
    transcriber/downloader параметризованы для тестов.
    setup=True: пока белый список пуст, первый написавший становится владельцем
    (chat_id сохраняется в config.json автоматически)."""
    msg = update.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    if chat_id is None:
        return None
    if chat_id not in allowed:
        if setup and not allowed:
            register_owner(chat_id)
            allowed.append(chat_id)
            print(f"setup: владелец зарегистрирован, chat_id {chat_id} → config.json")
            return ("Готово: вы владелец этой памяти, chat_id сохранён.\n\n" + HELP)
        return (f"Ваш chat_id: {chat_id}\n"
                f"Приём закрыт: добавьте его в .hermes/config.json → "
                f"telegram.allowed_chat_ids и перезапустите бота.")
    text = (msg.get("text") or "").strip()
    if text in ("/start", "/help"):
        return HELP
    if text:
        p = mb.triage(text, ROOT, source="telegram")
        return f"Принято в буфер: {p.name}" if p else "Дубликат — уже в буфере."
    voice = msg.get("voice") or msg.get("audio")
    if voice:
        audio = downloader(token, voice["file_id"])
        rel = audio.relative_to(ROOT)
        transcript = transcriber(audio)
        if transcript:
            note = f"{transcript}\n\n[оригинал: {rel}]"
            p = mb.triage(note, ROOT, source="telegram-voice")
            return (f"Расшифровано и принято в буфер: {p.name}\n\n«{transcript[:200]}»"
                    if p else "Дубликат — уже в буфере.")
        note = (f"! Голосовая заметка без расшифровки\n"
                f"Аудио сохранено: {rel} — расшифровать вручную "
                f"(pip install faster-whisper для автоматики).")
        mb.triage(note, ROOT, source="telegram-voice")
        return (f"Голос сохранён ({rel.name}), но расшифровка недоступна — "
                f"установите faster-whisper. Заметка-заглушка в буфере.")
    return "Не понял: пришлите текст или голосовое. /help — подсказка."


def main() -> int:
    setup = "--setup" in sys.argv
    token = _token()
    allowed = mb.load_config(ROOT).get("telegram", {}).get("allowed_chat_ids", [])
    me = tg(token, "getMe", timeout=20)
    print(f"Бот @{me['username']} запущен. Хранилище: {ROOT}")
    if not allowed:
        print("Белый список пуст — первый написавший станет владельцем (--setup)."
              if setup else
              "Белый список пуст — бот только сообщает chat_id (приём закрыт).")
    offset_file = ROOT / ".hermes" / "tg_offset"
    offset = int(offset_file.read_text()) if offset_file.is_file() else 0
    while True:
        try:
            updates = tg(token, "getUpdates", offset=offset + 1, timeout=55,
                         allowed_updates=["message"])
        except KeyboardInterrupt:
            print("\nостановлен")
            return 0
        except Exception as e:
            print(f"getUpdates: {e} — повтор через 5с")
            time.sleep(5)
            continue
        for u in updates:
            offset = max(offset, u["update_id"])
            offset_file.write_text(str(offset))
            try:
                reply = handle_update(u, token, allowed, setup=setup)
            except Exception as e:
                reply = f"Ошибка обработки: {e}"
                print(reply)
            chat = (u.get("message") or {}).get("chat", {}).get("id")
            if reply and chat:
                try:
                    tg(token, "sendMessage", timeout=20, chat_id=chat, text=reply)
                except Exception as e:
                    print(f"sendMessage: {e}")


if __name__ == "__main__":
    sys.exit(main())
