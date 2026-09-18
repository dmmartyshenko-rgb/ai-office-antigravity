"""Configuration: everything comes from the environment (.env, chmod 600)."""
import os
from pathlib import Path


def _load_dotenv(path: str) -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(os.environ.get("TG_BRIDGE_ENV", "/opt/tg-bridge/.env"))

API_ID = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
BEARER_TOKEN = os.environ.get("TG_BRIDGE_TOKEN", "")
SESSION_FILE = os.environ.get("TG_SESSION_FILE", "/opt/tg-bridge/session.txt")
AUDIT_LOG = os.environ.get("TG_AUDIT_LOG", "/opt/tg-bridge/audit.log")
LISTEN_HOST = os.environ.get("TG_LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("TG_LISTEN_PORT", "8080"))

# Rate limit for POST /send: max requests per window (seconds)
SEND_RATE_LIMIT = int(os.environ.get("TG_SEND_RATE_LIMIT", "20"))
SEND_RATE_WINDOW = int(os.environ.get("TG_SEND_RATE_WINDOW", "60"))
