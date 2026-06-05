#!/usr/bin/env python3
"""
echo_save_cookies.py — Easy cookie saver
Run this after copying cookie JSON from Cookie-Editor.

Usage:
  python3 echo_save_cookies.py claude    # then paste JSON, press Ctrl+D
  python3 echo_save_cookies.py chatgpt
  python3 echo_save_cookies.py gemini
  python3 echo_save_cookies.py perplexity
  python3 echo_save_cookies.py grok
"""
import sys, json, urllib.request
from pathlib import Path

provider = sys.argv[1] if len(sys.argv) > 1 else None
if not provider:
    print("Usage: python3 echo_save_cookies.py <provider>")
    print("Providers: claude chatgpt gemini perplexity grok")
    sys.exit(1)

cookie_dir = Path.home() / ".echo" / "cookies"
cookie_dir.mkdir(parents=True, exist_ok=True)
out = cookie_dir / f"{provider}.json"

print(f"Paste your Cookie-Editor JSON for {provider}")
print("Press Ctrl+D when done:")
print("-" * 40)

try:
    data = sys.stdin.read().strip()
    # Clean up common paste artifacts
    data = data.replace("[~", "").replace("~", "").strip()
    if not data.startswith("["):
        data = "[" + data
    if not data.endswith("]"):
        data = data + "]"
    parsed = json.loads(data)
    out.write_text(json.dumps(parsed, indent=2))
    print(f"\n✓ Saved {len(parsed)} cookies to {out}")
    
    # Hot-reload if server running
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                f"http://localhost:3210/reload_cookies/{provider}",
                method="POST"
            ), timeout=2
        )
        print(f"✓ Hot-reloaded into running server")
    except:
        print(f"→ Server not running — cookies will load on next start")
except json.JSONDecodeError as e:
    print(f"✗ Invalid JSON: {e}")
    print("  Make sure you copied the full JSON from Cookie-Editor")
    sys.exit(1)
