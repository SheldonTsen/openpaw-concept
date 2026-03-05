#!/usr/bin/env python3
"""
Basic Green API script: send a message, poll for a reply, print it, and exit.

Usage:
    python scripts/green-api-basic.py <phone_number> <message>

Example:
    python scripts/green-api-basic.py 1234567890 "Hello, are you there?"

Requires GREEN_API_INSTANCE_ID and GREEN_API_TOKEN in .env file.
"""

import sys
import time
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")


def build_url(instance_id: str, token: str, method: str) -> str:
    prefix = instance_id[:4]
    return f"https://{prefix}.api.greenapi.com/waInstance{instance_id}/{method}/{token}"


def get_settings(*, instance_id: str, token: str) -> dict:
    """Get current instance settings."""
    url = build_url(instance_id=instance_id, token=token, method="getSettings")
    resp = httpx.get(url, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def set_settings(*, instance_id: str, token: str, settings: dict) -> dict:
    """Update instance settings. Note: this reboots the instance."""
    url = build_url(instance_id=instance_id, token=token, method="setSettings")
    resp = httpx.post(url, json=settings, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def ensure_receive_settings(*, instance_id: str, token: str) -> None:
    """Ensure instance is configured for HTTP API polling (receiveNotification).

    Two things must be true:
    1. incomingWebhook must be "yes"
    2. webhookUrl must be empty — otherwise notifications get pushed to
       that URL instead of queuing for receiveNotification
    """
    current = get_settings(instance_id=instance_id, token=token)

    # Print relevant settings for debugging
    print(f"  incomingWebhook:          {current.get('incomingWebhook')}")
    print(f"  outgoingWebhook:          {current.get('outgoingWebhook')}")
    print(f"  outgoingAPIMessageWebhook:{current.get('outgoingAPIMessageWebhook')}")
    print(f"  webhookUrl:               '{current.get('webhookUrl', '')}'")

    needs_update: dict = {}

    if current.get("incomingWebhook") != "yes":
        needs_update["incomingWebhook"] = "yes"

    # Enable outgoing API message webhook so we can see our own sends
    # (useful for self-testing when sending to yourself)
    if current.get("outgoingAPIMessageWebhook") != "yes":
        needs_update["outgoingAPIMessageWebhook"] = "yes"

    # If webhookUrl is set, notifications are pushed there instead of
    # being queued for receiveNotification.  Clear it.
    if current.get("webhookUrl"):
        needs_update["webhookUrl"] = ""

    if not needs_update:
        print("Settings OK for receiveNotification polling")
        return

    print(f"Updating settings: {needs_update}")
    set_settings(
        instance_id=instance_id,
        token=token,
        settings=needs_update,
    )
    # Instance reboots after setSettings; give it a moment
    print("Instance rebooting after settings change, waiting 5s...")
    time.sleep(5)
    print("Settings updated")


def send_message(*, instance_id: str, token: str, chat_id: str, message: str) -> dict:
    """Send a text message via Green API."""
    url = build_url(instance_id=instance_id, token=token, method="sendMessage")
    payload = {"chatId": chat_id, "message": message}

    resp = httpx.post(url, json=payload, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def receive_notification(*, instance_id: str, token: str, receive_timeout: int = 5) -> dict | None:
    """Receive one notification from the queue.

    Uses server-side long-polling (receiveTimeout) so the request blocks
    on Green API's side for up to `receive_timeout` seconds before
    returning empty.  Returns None if queue is empty after the wait.
    """
    url = build_url(instance_id=instance_id, token=token, method="receiveNotification")

    resp = httpx.get(
        url,
        params={"receiveTimeout": receive_timeout},
        timeout=receive_timeout + 15.0,  # HTTP timeout > server wait
    )
    resp.raise_for_status()

    data = resp.json()
    if data is None:
        return None
    return data


def delete_notification(*, instance_id: str, token: str, receipt_id: int) -> bool:
    """Delete a notification from the queue (acknowledge it)."""
    url = build_url(
        instance_id=instance_id,
        token=token,
        method=f"deleteNotification/{receipt_id}",
    )

    resp = httpx.delete(url, timeout=30.0)
    resp.raise_for_status()
    return resp.json().get("result", False)


def extract_text_from_notification(notification: dict) -> tuple[str | None, str]:
    """Extract text content from a notification.

    Returns (text, webhook_type).  text is None for non-message notifications.
    Handles both incoming messages and outgoing API messages (for self-test).
    """
    body = notification.get("body", {})
    webhook_type = body.get("typeWebhook", "")

    if webhook_type == "incomingMessageReceived":
        message_data = body.get("messageData", {})

        text_data = message_data.get("textMessageData")
        if text_data:
            return text_data.get("textMessage"), webhook_type

        ext_data = message_data.get("extendedTextMessageData")
        if ext_data:
            return ext_data.get("text"), webhook_type

    if webhook_type == "outgoingAPIMessageReceived":
        message_data = body.get("messageData", {})

        text_data = message_data.get("textMessageData")
        if text_data:
            return text_data.get("textMessage"), webhook_type

        ext_data = message_data.get("extendedTextMessageData")
        if ext_data:
            return ext_data.get("text"), webhook_type

    return None, webhook_type


def last_incoming_messages(*, instance_id: str, token: str, minutes: int = 10) -> list:
    """Fetch recent incoming messages from the journal (independent of notification queue)."""
    url = build_url(instance_id=instance_id, token=token, method="lastIncomingMessages")
    resp = httpx.get(url, params={"minutes": minutes}, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def format_chat_id(phone: str) -> str:
    """Format a phone number into Green API chat ID."""
    digits = "".join(c for c in phone if c.isdigit())
    return f"{digits}@c.us"


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__.strip())
        sys.exit(1)

    phone = sys.argv[1]
    message = " ".join(sys.argv[2:])

    instance_id = os.getenv("GREEN_API_INSTANCE_ID")
    token = os.getenv("GREEN_API_TOKEN")

    if not instance_id or not token:
        print(
            "Error: GREEN_API_INSTANCE_ID and GREEN_API_TOKEN must be set in .env or environment."
        )
        sys.exit(1)

    chat_id = format_chat_id(phone=phone)
    poll_interval = 5  # server-side long-poll seconds per request
    timeout = 120  # max seconds to wait for a reply

    # --- Step 0: Ensure instance settings allow receiveNotification ---
    ensure_receive_settings(instance_id=instance_id, token=token)

    # --- Step 1: Drain any stale notifications first ---
    drained = 0
    while True:
        notif = receive_notification(instance_id=instance_id, token=token)
        if notif is None:
            break
        receipt_id = notif.get("receiptId")
        if receipt_id is not None:
            delete_notification(instance_id=instance_id, token=token, receipt_id=receipt_id)
        drained += 1
    if drained:
        print(f"(drained {drained} stale notification(s) from queue)")

    # --- Step 2: Send the message ---
    print(f"Sending to {chat_id}: {message}")
    result = send_message(
        instance_id=instance_id,
        token=token,
        chat_id=chat_id,
        message=message,
    )
    print(f"Sent! Message ID: {result.get('idMessage')}")

    # --- Step 3: Poll for a reply ---
    print(f"Waiting for reply (timeout {timeout}s, polling every {poll_interval}s)...")
    start = time.time()

    poll_count = 0
    while time.time() - start < timeout:
        poll_count += 1
        elapsed = int(time.time() - start)
        print(f"  poll #{poll_count} ({elapsed}s elapsed)...", end="", flush=True)

        notif = receive_notification(
            instance_id=instance_id,
            token=token,
            receive_timeout=poll_interval,
        )

        if notif is None:
            print(" empty")
            continue

        # Debug: show raw notification type
        webhook_type = notif.get("body", {}).get("typeWebhook", "???")
        receipt_id = notif.get("receiptId")
        print(f" got {webhook_type} (receipt={receipt_id})")

        text, wh_type = extract_text_from_notification(notification=notif)

        # Always acknowledge the notification
        if receipt_id is not None:
            delete_notification(instance_id=instance_id, token=token, receipt_id=receipt_id)

        if text is not None:
            sender = notif.get("body", {}).get("senderData", {}).get("senderName", "unknown")
            label = "Reply" if "incoming" in wh_type else "Echo (self)"
            print(f"\n{label} from {sender}:")
            print(text)
            return

        # Non-text notification — keep polling

    # --- Diagnostic: check if instance received anything at all ---
    print("\nTimed out. Running diagnostic — checking lastIncomingMessages...")
    recent = last_incoming_messages(instance_id=instance_id, token=token, minutes=10)
    if recent:
        print(f"Instance DID receive {len(recent)} message(s) in last 10 min:")
        for msg in recent[:5]:
            print(
                f"  [{msg.get('typeMessage')}] from {msg.get('senderId', '?')}: "
                f"{msg.get('textMessage', '(non-text)')}"
            )
        print("-> Messages exist but notification queue is empty.")
        print("   Try clearing webhookUrl in the Green API console directly.")
    else:
        print("Instance received 0 messages in the last 10 minutes.")
        print("The reply may not be reaching this Green API instance.")
        print("Verify the person is replying to the correct WhatsApp number.")
    sys.exit(1)


if __name__ == "__main__":
    main()
