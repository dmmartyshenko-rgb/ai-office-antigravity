"""Audit log: JSON lines — timestamp, endpoint, peer, outcome. Never message bodies."""
import json
import logging
from datetime import datetime, timezone

from . import config

_logger = logging.getLogger("tg_bridge.audit")
_logger.setLevel(logging.INFO)
_logger.propagate = False
_handler = logging.FileHandler(config.AUDIT_LOG)
_handler.setFormatter(logging.Formatter("%(message)s"))
_logger.addHandler(_handler)


def log(endpoint: str, peer: str | None = None, status: int | None = None, note: str | None = None) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "endpoint": endpoint,
    }
    if peer is not None:
        entry["peer"] = str(peer)
    if status is not None:
        entry["status"] = status
    if note:
        entry["note"] = note
    _logger.info(json.dumps(entry, ensure_ascii=False))
