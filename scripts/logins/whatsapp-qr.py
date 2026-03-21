#!/usr/bin/env python3
"""
Scan the QR code to link your WhatsApp account. Exits once paired.

Usage:
    uv run python scripts/logins/whatsapp.py

Auth is stored in neonize.db at the repo root.
Subsequent runs (worker, listener) will reuse it automatically.

Due to the janky nature of this script, you will need to kill the terminal window to 
close it. ctrl+c won't work.
"""

import os
import signal
from pathlib import Path

from neonize.client import NewClient
from neonize.events import PairStatusEv

DB_PATH = str(Path(__file__).resolve().parent.parent.parent / "neonize.db")


def force_exit(*_):
    os._exit(0)


signal.signal(signal.SIGINT, force_exit)
signal.signal(signal.SIGTERM, force_exit)

client = NewClient(DB_PATH)


@client.event(PairStatusEv)
def on_paired(_: NewClient, event: PairStatusEv):
    print(f"\nPaired as {event.ID.User}@{event.ID.Server}")
    print("You can now start the worker/listener.")
    os._exit(0)


if __name__ == "__main__":
    print("Scan the QR code below with WhatsApp (Linked Devices → Link a Device).")
    print("Press Ctrl+C to cancel.\n")
    client.connect()
