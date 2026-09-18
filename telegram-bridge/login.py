#!/usr/bin/env python3
"""Interactive first-time login: asks for the Telegram code and the 2FA
password, then writes a StringSession to TG_SESSION_FILE (chmod 600).

Run once as the service user, on the server:

    sudo -u tgbridge TG_BRIDGE_ENV=/opt/tg-bridge/.env /opt/tg-bridge/venv/bin/python /opt/tg-bridge/login.py

The bridge service itself never asks for a code — it only reads this file.
"""
import asyncio
import os
import sys
from getpass import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import config  # noqa: E402

from telethon import TelegramClient  # noqa: E402
from telethon.sessions import StringSession  # noqa: E402


async def main() -> None:
    if not config.API_ID or not config.API_HASH:
        sys.exit("TG_API_ID / TG_API_HASH are not set — fill in the .env file first.")

    client = TelegramClient(StringSession(), config.API_ID, config.API_HASH)
    await client.start(
        phone=lambda: input("Phone number (international format, e.g. +49...): "),
        code_callback=lambda: input("Code from Telegram: "),
        password=lambda: getpass("2FA password (empty if none): "),
    )
    me = await client.get_me()
    session_str = client.session.save()
    await client.disconnect()

    path = Path(config.SESSION_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(session_str + "\n")
    os.chmod(path, 0o600)
    print(f"Logged in as: {me.first_name or ''} {me.last_name or ''} (@{me.username or '-'}, id={me.id})")
    print(f"Session saved to {path} (chmod 600).")
    print("Now restart the service: sudo systemctl restart tg-bridge")


if __name__ == "__main__":
    asyncio.run(main())
