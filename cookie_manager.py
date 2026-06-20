#!/usr/bin/env python3
import json
import pathlib
import sys

CONFIG_PATH = pathlib.Path("~/vision_assistant/config/session_cookies.json").expanduser()

def load_cookies():
    if not CONFIG_PATH.exists():
        return {}
    return json.loads(CONFIG_PATH.read_text())

def update_cookie(provider, cookie_name, cookie_value):
    data = load_cookies()
    if provider not in data:
        data[provider] = {}
    data[provider][cookie_name] = cookie_value
    CONFIG_PATH.write_text(json.dumps(data, indent=2))
    print(f"[cookies] Updated {cookie_name} for {provider} successfully.")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 cookie_manager.py <provider> <cookie_name> <value>")
        print("Example: python3 cookie_manager.py chatgpt __Secure-next-auth.session-token ey...")
        sys.exit(1)
    update_cookie(sys.argv[1], sys.argv[2], sys.argv[3])
