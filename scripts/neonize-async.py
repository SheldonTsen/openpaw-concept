#!/usr/bin/env python3

# DOES NOT WORK

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from neonize.aioze.client import NewAClient
from neonize.aioze.events import ConnectedEv, MessageEv, PairStatusEv, event
from neonize.utils import log, build_jid


# --- Configuration ---
DB_PATH = str(Path(__file__).resolve().parent.parent / "neonize.db")
message_to_send = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Hello from neonize!"


# --- Logging / Signals ---
log.setLevel(logging.INFO)


def interrupted(*_):
    print("\nShutting down...")
    event.set()


signal.signal(signal.SIGINT, interrupted)
signal.signal(signal.SIGTERM, interrupted)


# --- Client (MODULE LEVEL — matches official example) ---
client = NewAClient(DB_PATH)

# Track if we've already sent the initial message
message_sent = False


@client.event(ConnectedEv)
async def on_connected(client: NewAClient, _: ConnectedEv):
    global message_sent

    log.info("Connected to WhatsApp")

    if message_sent:
        return

    me = client.get_me()
    phone = me.JID.User

    log.info(f"Sending to self ({phone}): {message_to_send}")

    await client.send_message(
        build_jid(phone),
        message_to_send,
    )

    message_sent = True
    log.info("Sent! Reply in WhatsApp to continue...")


@client.event(PairStatusEv)
async def on_pair_status(_: NewAClient, msg: PairStatusEv):
    log.info(f"Logged in as {msg.ID.User}")


@client.event(MessageEv)
async def on_message(client: NewAClient, message: MessageEv):
    text = message.Message.conversation or message.Message.extendedTextMessage.text

    if not text:
        return

    is_from_me = message.Info.MessageSource.IsFromMe
    sender = message.Info.MessageSource.Sender

    log.info(f"{'[me]' if is_from_me else '[them]'} {sender.User}: {text}")

    # Ignore our own initial message
    if text == message_to_send:
        return

    print(f"\nReply from {sender.User}:")
    print(text)

    # Stop cleanly
    await client.stop()
    event.set()


async def connect():
    await client.connect()
    await client.idle()  # REQUIRED


if __name__ == "__main__":
    print("Starting Neonize WhatsApp client...")
    print(f"Auth database: {DB_PATH}")
    print(f"Message: {message_to_send}")
    print()
    print("Press Ctrl+C to stop.\n")

    asyncio.run(connect())
