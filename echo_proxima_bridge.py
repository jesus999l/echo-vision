#!/usr/bin/env python3
"""
echo_proxima_bridge.py — Conscious Mind AI Router
Handles real-time streaming queries via Proxima and online fallback endpoints.
"""

import os, sys, re, json, logging, urllib.request, urllib.error, pathlib
from pathlib import Path

PROXIMA_URL   = "http://localhost:3211"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

def _load_openrouter_key():
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if key: return key
    env_file = Path.home() / ".hermes/.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""

OPENROUTER_KEY    = _load_openrouter_key()
OPENROUTER_MODEL  = "anthropic/claude-sonnet-4"
log = logging.getLogger("echo_proxima")

INTENT_PATTERNS = {
    "code": [r"\b(fix|debug|error|traceback|exception|bug|patch|code|script|function)\b", r"```"],
    "search": [r"\b(latest|current|today|2026|news|search)\b"],
    "plan": [r"\b(plan|architect|design|structure|pipeline)\b"],
    "analyze": [r"\b(analyze|review|audit|why|explain)\b"],
    "quick": [r"^.{0,60}$", r"\b(yes|no|what|when)\b"]
}
MODEL_ROUTING = {
    "code": "chatgpt", "plan": "chatgpt", "search": "perplexity",
    "analyze": "gemini", "quick": "chatgpt", "auto": "chatgpt"
}

def route_intent(message: str) -> str:
    msg_lower = message.lower()
    scores = {intent: 0 for intent in INTENT_PATTERNS}
    for intent, patterns in INTENT_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, msg_lower, re.I): scores[intent] += 1
    best = max(scores, key=scores.get)
    return "auto" if scores[best] == 0 else MODEL_ROUTING.get(best, "auto")

def _proxima_available():
    try:
        urllib.request.urlopen(f"{PROXIMA_URL}/", timeout=2)
        return True
    except: return False

def _ask_proxima(message: str, model: str = "chatgpt", function: str = None, **kwargs) -> str | None:
    try:
        import requests
        r = requests.post(f"{PROXIMA_URL}/v1/chat/completions",
            json={"messages": [{"role": "user", "content": message}], "model": model},
            timeout=300)
        text = r.json()["choices"][0]["message"]["content"].strip()
        return text if text else None
    except Exception as e:
        log.warning(f"Proxima channel missed: {e}")
        return None

def _ask_openrouter(message: str) -> str | None:
    if not OPENROUTER_KEY: return None
    payload = json.dumps({"model": OPENROUTER_MODEL, "messages": [{"role": "user", "content": message}]}).encode()
    req = urllib.request.Request(OPENROUTER_URL, data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENROUTER_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]
    except Exception as e: return None

def ask(message: str, intent: str = None, model: str = None, function: str = None, **kwargs) -> dict:
    detected_intent = intent or route_intent(message)
    try:
        sys.path.insert(0, str(pathlib.Path.home() / "vision_assistant"))
        import echo_personality
        master_prompt = getattr(echo_personality, "SYSTEM_PROMPT", "You are Echo, an AI companion system.")
        message = master_prompt + "\n\n[User Context Query]: " + message
    except Exception as identity_err:
        log.warning(f"Personality injection channel skipped: {identity_err}")

    target_model = model or MODEL_ROUTING.get(detected_intent, "auto")
    if _proxima_available():
        text = _ask_proxima(message, model=target_model, function=function, **kwargs)
        if text: return {"text": text, "provider": target_model, "intent": detected_intent, "via": "proxima"}

    text = _ask_openrouter(message)
    if text: return {"text": text, "provider": OPENROUTER_MODEL, "intent": detected_intent, "via": "openrouter"}
    return {"text": "Conscious online routing channels unavailable.", "provider": "none", "intent": detected_intent, "via": "failed"}

def ask_text(message: str, **kwargs) -> str:
    return ask(message, **kwargs).get("text", "")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1:
        res = ask(sys.argv[1])
        print(f"\nProvider: {res['provider']} via {res['via']}\nResponse: {res['text']}")
