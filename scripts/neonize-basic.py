#!/usr/bin/env python3
"""
Basic Neonize script: send a message to yourself, wait for a reply, print it, exit.

First run: displays a QR code in terminal — scan it with WhatsApp to link.
Subsequent runs: reconnects automatically (auth stored in neonize.db).

Usage:
    python scripts/neonize-basic.py "Hello from neonize!"

No environment variables needed. Auth state is stored locally in neonize.db.
"""

import logging
import os
import signal
import sys
import threading
from pathlib import Path

from neonize.client import NewClient
from neonize.events import ConnectedEv, MessageEv, PairStatusEv, event
from neonize.utils import log, build_jid

# --- Configuration ---
DB_PATH = str(Path(__file__).resolve().parent.parent / "neonize.db")

# Get message from args
message_to_send = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Hello from neonize!"


def force_exit(*_):
    """Force exit — neonize's Go runtime can swallow signals."""
    print("\nShutting down...")
    event.set()
    os._exit(0)


signal.signal(signal.SIGINT, force_exit)
signal.signal(signal.SIGTERM, force_exit)
log.setLevel(logging.INFO)

client = NewClient(DB_PATH)

# Track whether we've sent our message yet (avoid re-sending on reconnect)
message_sent = threading.Event()


@client.event(ConnectedEv)
def on_connected(client: NewClient, _: ConnectedEv):
    log.info("Connected to WhatsApp")

    if message_sent.is_set():
        return

    # Send message to self (own JID)
    me = client.get_me()
    phone = me.JID.User
    log.info(f"Sending to self ({phone}): {message_to_send}")
    client.send_message(
        build_jid(phone),
        message_to_send,
    )
    message_sent.set()
    log.info("Sent! Reply in WhatsApp to continue...")


@client.event(PairStatusEv)
def on_pair_status(_: NewClient, msg: PairStatusEv):
    log.info(f"Logged in as {msg.ID.User}")


@client.event(MessageEv)
def on_message(_: NewClient, message: MessageEv):
    text = message.Message.conversation or message.Message.extendedTextMessage.text

    if not text:
        return

    is_from_me = message.Info.MessageSource.IsFromMe
    sender = message.Info.MessageSource.Sender

    log.info(f"{'[me]' if is_from_me else '[them]'} {sender.User}: {text}")

    # Skip our own outgoing message (the one we just sent)
    if text == message_to_send:
        return

    # Got a reply
    print(f"\nReply from {sender.User}:")
    print(text)

    # Exit
    event.set()
    os._exit(0)


if __name__ == "__main__":
    print("Starting Neonize WhatsApp client...")
    print(f"Auth database: {DB_PATH}")
    print(f"Message: {message_to_send}")
    print()
    print("Press Ctrl+C to stop.")
    print()
    client.connect()
