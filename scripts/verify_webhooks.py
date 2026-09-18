import urllib.request
import json
import sys

# Ensure UTF-8 output on Windows console
sys.stdout.reconfigure(encoding='utf-8')

endpoints = [
    ("PRIMARY (Payments-Core)", "c85d175d-de64-4de3-84d9-d857b94b43d3"),
    ("SECONDARY (Infra-Core)", "8b8be468-f9e6-48ae-9cb7-70b950ebbd3d")
]

for name, uuid in endpoints:
    print("=" * 60)
    print(f"CHANNEL: {name}")
    print(f"UUID: {uuid}")
    url = f"https://webhook.site/token/{uuid}/requests"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    res = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))
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
