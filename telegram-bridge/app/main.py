"""Telegram user-session bridge: FastAPI + Telethon.

The service only READS an existing StringSession (created interactively by
login.py). It never asks for a login code. If the session is missing or
invalid, /health reports authorized:false and the API endpoints return 503.
"""
import asyncio
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from telethon import TelegramClient, errors
from telethon.sessions import StringSession

from . import audit, config

client: TelegramClient | None = None
authorized: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, authorized
    session_str = ""
    p = Path(config.SESSION_FILE)
    if p.exists():
        session_str = p.read_text().strip()
    client = TelegramClient(StringSession(session_str or None), config.API_ID, config.API_HASH)
    try:
        # Never let a hung Telegram connection block the API from starting.
        await asyncio.wait_for(client.connect(), timeout=20)
        authorized = await asyncio.wait_for(client.is_user_authorized(), timeout=20)
    except Exception as exc:  # noqa: BLE001 — must not crash on bad session/network
        authorized = False
        audit.log("startup", note=f"connect failed: {type(exc).__name__}")
    audit.log("startup", note=f"authorized={authorized}")
    yield
    if client and client.is_connected():
        await client.disconnect()


app = FastAPI(title="tg-bridge", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


# --- Auth: Bearer token, constant-time comparison -------------------------

async def require_token(request: Request) -> None:
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    if not config.BEARER_TOKEN or not secrets.compare_digest(token, config.BEARER_TOKEN):
        audit.log(request.url.path, status=401, note="bad token")
        raise HTTPException(status_code=401, detail="unauthorized")


def require_client() -> TelegramClient:
    if client is None or not authorized or not client.is_connected():
        raise HTTPException(status_code=503, detail="telegram session not authorized; run login.py")
    return client


# --- Telegram error mapping (no bare 500s for expected failures) ----------

def telegram_error_response(exc: Exception) -> JSONResponse:
    if isinstance(exc, errors.FloodWaitError):
        return JSONResponse(status_code=429, content={
            "error": "flood_wait",
            "retry_after_seconds": exc.seconds,
            "detail": f"Telegram flood wait: retry in {exc.seconds}s",
        })
    if isinstance(exc, (errors.UsernameNotOccupiedError, errors.UsernameInvalidError,
                        errors.PeerIdInvalidError, ValueError)):
        return JSONResponse(status_code=400, content={
            "error": "invalid_peer",
            "detail": str(exc),
        })
    if isinstance(exc, errors.ChatWriteForbiddenError):
        return JSONResponse(status_code=403, content={
            "error": "write_forbidden",
            "detail": "not allowed to write to this chat",
        })
    if isinstance(exc, errors.RPCError):
        return JSONResponse(status_code=502, content={
            "error": "telegram_error",
            "code": exc.code,
            "detail": exc.message or type(exc).__name__,
        })
    raise exc


async def resolve_peer(tg: TelegramClient, peer: str):
    """Accept 'me', @username, phone, or a numeric id."""
    peer = peer.strip()
    if peer in ("me", "self"):
        return "me"
    try:
        return await tg.get_entity(int(peer))
    except ValueError:
        pass
    return await tg.get_entity(peer)


# --- Rate limit for /send (sliding window, in-memory) ---------------------

_send_times: list[float] = []


def check_send_rate() -> None:
    now = time.monotonic()
    cutoff = now - config.SEND_RATE_WINDOW
    while _send_times and _send_times[0] < cutoff:
        _send_times.pop(0)
    if len(_send_times) >= config.SEND_RATE_LIMIT:
        raise HTTPException(status_code=429, detail={
            "error": "rate_limited",
            "detail": f"max {config.SEND_RATE_LIMIT} sends per {config.SEND_RATE_WINDOW}s",
        })
    _send_times.append(now)


# --- Endpoints ------------------------------------------------------------

@app.get("/health", dependencies=[Depends(require_token)])
async def health():
    audit.log("/health")
    connected = client is not None and client.is_connected()
    return {"status": "ok", "connected": connected, "authorized": bool(authorized and connected)}


def _dialog_type(d) -> str:
    if d.is_user:
        return "user"
    if d.is_channel:
        return "channel"
    if d.is_group:
        return "group"
    return "unknown"


@app.get("/dialogs", dependencies=[Depends(require_token)])
async def dialogs(limit: int = 20, offset: int = 0):
    tg = require_client()
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    audit.log("/dialogs", note=f"limit={limit} offset={offset}")
    try:
        result = []
        i = -1
        async for d in tg.iter_dialogs(limit=offset + limit):
            i += 1
            if i < offset:
                continue
            msg = d.message
            last = None
            if msg is not None:
                read = True
                if msg.out:
                    read_max = getattr(d.dialog, "read_outbox_max_id", 0) or 0
                    read = msg.id <= read_max
                else:
                    read = d.unread_count == 0
                last = {
                    "text": (msg.message or "")[:500],
                    "date": msg.date.isoformat() if msg.date else None,
                    "out": bool(msg.out),
                    "read": read,
                }
            result.append({
                "id": d.id,
                "type": _dialog_type(d),
                "name": d.name,
                "unread_count": d.unread_count,
                "last_message": last,
            })
        return {"dialogs": result, "count": len(result), "offset": offset}
    except Exception as exc:  # noqa: BLE001
        return telegram_error_response(exc)


def _message_type(m) -> str:
    if m.photo:
        return "photo"
    if m.voice:
        return "voice"
    if m.video:
        return "video"
    if m.sticker:
        return "sticker"
    if m.document:
        return "document"
    if m.action:
        return "service"
    return "text"


@app.get("/messages", dependencies=[Depends(require_token)])
async def messages(peer: str, limit: int = 20, offset_id: int = 0):
    tg = require_client()
    limit = max(1, min(limit, 100))
    audit.log("/messages", peer=peer, note=f"limit={limit} offset_id={offset_id}")
    try:
        entity = await resolve_peer(tg, peer)
        result = []
        async for m in tg.iter_messages(entity, limit=limit, offset_id=offset_id):
            sender = None
            s = await m.get_sender()
            if s is not None:
                name = " ".join(filter(None, [getattr(s, "first_name", None), getattr(s, "last_name", None)])) \
                       or getattr(s, "title", None) or getattr(s, "username", None)
                sender = {"id": s.id, "name": name}
            result.append({
                "id": m.id,
                "date": m.date.isoformat() if m.date else None,
                "out": bool(m.out),
                "sender": sender,
                "text": m.message or "",
                "type": _message_type(m),
                "reply_to": m.reply_to.reply_to_msg_id if m.reply_to else None,
            })
        return {"peer": peer, "messages": result, "count": len(result)}
    except Exception as exc:  # noqa: BLE001
        return telegram_error_response(exc)


class SendBody(BaseModel):
    peer: str
    text: str = Field(min_length=1, max_length=4096)
    reply_to: int | None = None


@app.post("/send", dependencies=[Depends(require_token)])
async def send(body: SendBody):
    tg = require_client()
    check_send_rate()
    audit.log("/send", peer=body.peer, note=f"reply_to={body.reply_to}")
    try:
        entity = await resolve_peer(tg, body.peer)
        msg = await tg.send_message(entity, body.text, reply_to=body.reply_to)
        return {"id": msg.id, "date": msg.date.isoformat() if msg.date else None}
    except Exception as exc:  # noqa: BLE001
        return telegram_error_response(exc)


class ReadBody(BaseModel):
    peer: str


@app.post("/read", dependencies=[Depends(require_token)])
async def mark_read(body: ReadBody):
    tg = require_client()
    audit.log("/read", peer=body.peer)
    try:
        entity = await resolve_peer(tg, body.peer)
        await tg.send_read_acknowledge(entity)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return telegram_error_response(exc)
