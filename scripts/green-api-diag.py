#!/usr/bin/env python3
"""Diagnose Green API instance — checks connection state and all settings."""

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")


def build_url(instance_id: str, token: str, method: str) -> str:
    prefix = instance_id[:4]
    return f"https://{prefix}.api.greenapi.com/waInstance{instance_id}/{method}/{token}"


def main() -> None:
    instance_id = os.getenv("GREEN_API_INSTANCE_ID")
    token = os.getenv("GREEN_API_TOKEN")

    if not instance_id or not token:
        print("Error: GREEN_API_INSTANCE_ID and GREEN_API_TOKEN must be set")
        return

    print(f"Instance ID: {instance_id}")
    print(f"URL prefix:  {instance_id[:4]}")
    print()

    # 1. Check instance state (is WhatsApp linked?)
    print("=== Instance State ===")
    url = build_url(instance_id=instance_id, token=token, method="getStateInstance")
    resp = httpx.get(url, timeout=30.0)
    print(f"  HTTP {resp.status_code}: {resp.json()}")
    print()

    # 2. Check WID (which phone number is this instance?)
    print("=== Instance WID (linked phone) ===")
    url = build_url(instance_id=instance_id, token=token, method="getWaSettings")
    resp = httpx.get(url, timeout=30.0)
    wa_settings = resp.json()
    print(f"  Phone (wid): {wa_settings.get('wid', '???')}")
    print(f"  Avatar:      {wa_settings.get('avatar', 'N/A')}")
    print(f"  Phone:       {wa_settings.get('phone', '???')}")
    print()

    # 3. All settings
    print("=== All Settings ===")
    url = build_url(instance_id=instance_id, token=token, method="getSettings")
    resp = httpx.get(url, timeout=30.0)
    settings = resp.json()
    for key, val in sorted(settings.items()):
        print(f"  {key}: {val}")
    print()

    # 4. Last incoming messages (last 60 min)
    print("=== Last Incoming Messages (60 min) ===")
    url = build_url(instance_id=instance_id, token=token, method="lastIncomingMessages")
    resp = httpx.get(url, params={"minutes": 60}, timeout=30.0)
    msgs = resp.json()
    if msgs:
        for msg in msgs[:10]:
            print(f"  [{msg.get('typeMessage')}] {msg.get('chatId')}: "
                  f"{msg.get('textMessage', '(non-text)')}")
    else:
        print("  (none)")
    print()

    # 5. Last outgoing messages (to confirm sends work)
    print("=== Last Outgoing Messages (60 min) ===")
    url = build_url(instance_id=instance_id, token=token, method="lastOutgoingMessages")
    resp = httpx.get(url, params={"minutes": 60}, timeout=30.0)
    msgs = resp.json()
    if msgs:
        for msg in msgs[:10]:
            print(f"  [{msg.get('typeMessage')}] to {msg.get('chatId')}: "
                  f"{msg.get('textMessage', '(non-text)')}")
    else:
        print("  (none)")


if __name__ == "__main__":
    main()
