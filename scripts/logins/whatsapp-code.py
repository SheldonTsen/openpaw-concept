#!/usr/bin/env python3
"""
Pair WhatsApp using a numeric code instead of QR.

Usage:
    uv run python scripts/logins/whatsapp-code.py <phone_number>

Phone number format: digits only, no + or spaces (e.g. 14155552671)

Steps:
    1. Run this script with your phone number
    2. Open WhatsApp → Linked Devices → Link a Device → Link with phone number
    3. Enter the 8-digit code shown
    4. Script exits once paired

Auth is saved to neonize.db at the repo root.

Due to the janky nature of this script, you will need to kill the terminal window to 
close it. ctrl+c won't work.
"""

import os
import signal
import sys
import threading
from pathlib import Path

from neonize.client import NewClient
from neonize.events import PairStatusEv

DB_PATH = str(Path(__file__).resolve().parent.parent.parent / "neonize.db")


def force_exit(*_):
    os._exit(0)


signal.signal(signal.SIGINT, force_exit)
signal.signal(signal.SIGTERM, force_exit)

if len(sys.argv) < 2:
    print("Usage: uv run python scripts/logins/whatsapp-code.py <phone_number>")
    print("Example: uv run python scripts/logins/whatsapp-code.py 14155552671")
    sys.exit(1)

phone = sys.argv[1].strip().lstrip("+")
client = NewClient(DB_PATH)
_code_requested = threading.Event()


def on_qr(_client: NewClient, _data: bytes):
    """Override the default QR display — request a pair code instead."""
    if _code_requested.is_set():
        return
    _code_requested.set()

    def request_code():
        try:
            code = _client.PairPhone(
                phone=phone,
                show_push_notification=True,
            )
            print(f"\nYour pairing code: {code}")
            print("Open WhatsApp → Linked Devices → Link a Device → Link with phone number")
            print("Enter the code above. Waiting for confirmation...\n")
        except Exception as e:
            print(f"Failed to get pairing code: {e}")
            os._exit(1)

    threading.Thread(target=request_code, daemon=True).start()


# Override QR handler so it doesn't print the QR
client.event.qr(on_qr)


@client.event(PairStatusEv)
def on_paired(_: NewClient, event: PairStatusEv):
    print(f"Paired as {event.ID.User}@{event.ID.Server}")
    print("Done. You can now start the worker/listener.")
    os._exit(0)


if __name__ == "__main__":
    print(f"Connecting to WhatsApp (phone: {phone})...")
    print("Press Ctrl+C to cancel.\n")
    client.connect()
