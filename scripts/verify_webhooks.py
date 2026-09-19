"""
LoopGuard - Webhook Verification Utility
Queries Webhook.site endpoints to inspect received alert payloads and HMAC links.
Usage:
    python scripts/verify_webhooks.py <primary_uuid> [secondary_uuid]
    or set environment variables: PRIMARY_WEBHOOK_UUID, SECONDARY_WEBHOOK_UUID
"""

import os
import sys
import json
import urllib.request

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Extract UUIDs from command line arguments or environment variables
primary_uuid = (
    sys.argv[1] if len(sys.argv) > 1
    else os.environ.get("PRIMARY_WEBHOOK_UUID", "c85d175d-de64-4de3-84d9-d857b94b43d3")
)
secondary_uuid = (
    sys.argv[2] if len(sys.argv) > 2
    else os.environ.get("SECONDARY_WEBHOOK_UUID", "8b8be468-f9e6-48ae-9cb7-70b950ebbd3d")
)

endpoints = [
    ("PRIMARY (Payments-Core)", primary_uuid),
    ("SECONDARY (Infra-Core)", secondary_uuid)
]

for name, uuid in endpoints:
    if not uuid:
        continue
    print("=" * 60)
    print(f"CHANNEL: {name}")
    print(f"UUID: {uuid}")
    url = f"https://webhook.site/token/{uuid}/requests"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            res = json.loads(response.read().decode("utf-8"))
            print(f"Total requests recorded by webhook.site: {res.get('total', len(res.get('data', [])))}")
            for idx, item in enumerate(res.get("data", [])):
                print(f"\n  --- Request #{idx+1} ---")
                print(f"  Received At : {item.get('created_at')}")
                print(f"  Method      : {item.get('method')}")
                print(f"  Origin IP   : {item.get('ip')}")
                headers = item.get("headers", {})
                print(f"  User-Agent  : {headers.get('user-agent', [''])[0]}")
                raw_content = item.get("content", "{}")
                try:
                    content = json.loads(raw_content)
                    print(f"  Header Text : {content.get('content')}")
                    embeds = content.get("embeds", [])
                    if embeds:
                        embed = embeds[0]
                        print(f"  Embed Title : {embed.get('title')}")
                        for field in embed.get("fields", []):
                            fname = field.get("name")
                            fval = field.get("value")
                            print(f"    * {fname}: {fval}")
                        footer = embed.get("footer", {}).get("text")
                        print(f"  Footer      : {footer}")
                except Exception as e:
                    print(f"  Raw Content : {raw_content[:200]} (Parse err: {e})")
    except Exception as err:
        print(f"  [ERROR] Failed to query webhook.site for {uuid}: {err}")
