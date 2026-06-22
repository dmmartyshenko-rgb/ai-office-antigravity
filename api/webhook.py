"""
MiMo Code Telegram Bot — AI coding assistant powered by Xiaomi MiMo V2-Flash (free).
Uses OpenRouter free tier: xiaomi/mimo-v2-flash:free
Deployed as a Vercel serverless function (webhook mode).
"""
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler

TELEGRAM_API_URL = "https://api.telegram.org"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MIMO_MODEL = "xiaomi/mimo-v2-flash:free"

SYSTEM_PROMPT = (
    "You are an expert coding assistant powered by Xiaomi MiMo V2-Flash. "
    "Help users with programming questions, debug code, explain concepts, "
    "review code, and write clean implementations. "
    "Always use proper code blocks with language tags. "
    "Match the language of the user — respond in Russian if they write in Russian, "
    "in English if they write in English. "
    "Be concise and practical."
)


def _call_mimo(user_text: str) -> str:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    payload = {
        "model": MIMO_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


def _send_telegram(chat_id: int, text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    url = f"{TELEGRAM_API_URL}/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    urllib.request.urlopen(req, timeout=20)


def _send_long(chat_id: int, text: str) -> None:
    """Split and send messages longer than Telegram's 4096-char limit."""
    MAX = 4000
    for i in range(0, len(text), MAX):
        _send_telegram(chat_id, text[i : i + MAX])


def _handle_update(update: dict) -> None:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()
    if not text:
        return

    cmd = text.lower().split()[0] if text.startswith("/") else ""

    if cmd == "/start":
        _send_telegram(
            chat_id,
            "Привет! Я AI-кодер на базе Xiaomi MiMo V2-Flash.\n\n"
            "Отправь любой вопрос по коду — отвечу с примерами.\n\n"
            "Примеры:\n"
            "• Напиши сортировку пузырьком на Python\n"
            "• Почему мой SQL запрос работает медленно?\n"
            "• Объясни разницу между async/await и threading\n\n"
            "/help — все команды",
        )
        return

    if cmd == "/help":
        _send_telegram(
            chat_id,
            "Команды:\n"
            "/start — приветствие\n"
            "/help — это сообщение\n\n"
            "Просто пиши вопрос или код — отвечу с примерами.",
        )
        return

    try:
        reply = _call_mimo(text)
        _send_long(chat_id, reply)
    except Exception as exc:
        _send_telegram(chat_id, f"Ошибка: {exc}")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "bot": "MiMo Code Bot"}).encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            update = json.loads(body)
            _handle_update(update)
        except Exception:
            pass
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass
