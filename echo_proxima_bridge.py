#!/usr/bin/env python3
"""
echo_proxima_bridge.py — Smart AI Router
Routes queries to the best AI via Proxima, falls back to OpenRouter or local Ollama.

Routing logic:
  code / debug / plan  → Claude (precision)
  search / news / web  → Perplexity (live data)
  architecture / why   → ChatGPT (reasoning)
  quick / simple       → local qwen3-fast (instant, free)
  auto                 → Proxima Smart Router decides

Fallback chain:
  Proxima (localhost:3210) → OpenRouter → local Ollama

Usage:
  from echo_proxima_bridge import ask, route_intent
  response = ask("fix this Python error", code="...")
  response = ask("what is the best embedding model 2026", intent="search")

  python3 echo_proxima_bridge.py "your question"
  python3 echo_proxima_bridge.py --status
"""

import os, sys, re, json, logging, urllib.request, urllib.error
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────

PROXIMA_URL   = "http://localhost:3210"

# ── Provider priority (Claude is LAST) ──
PROVIDER_CHAIN = [
    {"base_url": "http://localhost:3210/v1",  "model": "chatgpt",              "name": "ChatGPT",       "emoji": "💬"},
    {"base_url": "http://localhost:3210/v1",  "model": "gemini",               "name": "Gemini",        "emoji": "✦"},
    {"base_url": "http://localhost:3210/v1",  "model": "perplexity",           "name": "Perplexity",    "emoji": "🔍"},
    {"base_url": "http://localhost:20128/v1", "model": "oc/auto",              "name": "OpenCode-Free", "emoji": "⚡"},
    {"base_url": "http://localhost:20128/v1", "model": "kr/claude-sonnet-4.5","name": "Claude-Last",   "emoji": "◆"},
]
ACTIVE_PROVIDER = PROVIDER_CHAIN[0]
OLLAMA_URL    = "http://127.0.0.1:11434/api/generate"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
LOCAL_MODEL   = "qwen3:4b"

# Load OpenRouter key from Hermes config if available
def _load_openrouter_key():
    import os
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if key:
        return key
    env_file = Path.home() / ".hermes/.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""

OPENROUTER_KEY    = _load_openrouter_key()
OPENROUTER_MODEL  = "anthropic/claude-sonnet-4"

log = logging.getLogger("echo_proxima")

# ── INTENT DETECTION ─────────────────────────────────────────────────

INTENT_PATTERNS = {
    "code": [
        r"\b(fix|debug|error|traceback|exception|bug|patch|code|script|function|class|import)\b",
        r"\b(python|javascript|bash|zsh|rust|java|kotlin|sql)\b",
        r"```", r"def |class |import |return "
    ],
    "search": [
        r"\b(latest|current|today|2026|news|what is|who is|when did|search)\b",
        r"\b(release|update|version|recently|now)\b"
    ],
    "plan": [
        r"\b(plan|architect|design|structure|how to build|how should|strategy)\b",
        r"\b(integrate|pipeline|system|workflow|approach)\b"
    ],
    "analyze": [
        r"\b(analyze|review|audit|check|evaluate|assess|compare)\b",
        r"\b(why|explain|what does|what is the difference)\b"
    ],
    "quick": [
        r"^.{0,60}$",  # short questions
        r"\b(yes|no|what|when|where|who|list)\b"
    ]
}

MODEL_ROUTING = {
    "code":    "chatgpt",
    "plan":    "chatgpt",
    "search":  "perplexity",
    "analyze": "gemini",
    "quick":   "local",
    "auto":    "chatgpt"
}

def route_intent(message: str) -> str:
    """Detect intent and return the best model string."""
    msg_lower = message.lower()
    scores = {intent: 0 for intent in INTENT_PATTERNS}
    for intent, patterns in INTENT_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, msg_lower, re.I):
                scores[intent] += 1
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "auto"
    return MODEL_ROUTING.get(best, "auto")

# ── PROXIMA ───────────────────────────────────────────────────────────

def _proxima_available():
    try:
        urllib.request.urlopen(f"{PROXIMA_URL}/v1/models", timeout=2)
        return True
    except:
        return False

def _ask_proxima(message: str, model: str = "auto", function: str = None, **kwargs) -> str | None:
    """Call Proxima SDK."""
    try:
        sys.path.insert(0, str(Path.home() / "Proxima/sdk"))
        from proxima import Proxima
        client = Proxima(base_url=PROXIMA_URL)
        kwargs_clean = {k: v for k, v in kwargs.items() if v is not None}
        resp = client.chat(message, model=model, function=function, **kwargs_clean)
        log.info(f"Proxima: {resp.provider} ({resp.response_time_ms}ms)")
        return resp.text
    except Exception as e:
        log.warning(f"Proxima failed: {e}")
        return None

# ── OPENROUTER ────────────────────────────────────────────────────────

def _ask_openrouter(message: str) -> str | None:
    if not OPENROUTER_KEY:
        log.warning("No OpenRouter key found")
        return None
    payload = json.dumps({
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": message}],
        "max_tokens": 1500
    }).encode()
    req = urllib.request.Request(
        OPENROUTER_URL, data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "HTTP-Referer": "https://echo-os.local",
            "X-Title": "Echo OS"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        log.warning(f"OpenRouter failed: {e}")
        return None

# ── LOCAL OLLAMA ──────────────────────────────────────────────────────

def _ask_local(message: str, model: str = LOCAL_MODEL) -> str | None:
    payload = json.dumps({
        "model": model,
        "prompt": f"/no_think\n{message}",
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 400, "think": False}
    }).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read()).get("response", "").strip()
    except Exception as e:
        log.warning(f"Local Ollama failed: {e}")
        return None

# ── MAIN ROUTER ───────────────────────────────────────────────────────

def ask(
    message: str,
    intent: str = None,
    model: str = None,
    function: str = None,
    fallback_local: bool = True,
    **kwargs
) -> dict:
    """
    Route a query to the best available AI.

    Returns:
        {
            "text": response text,
            "provider": which AI answered,
            "intent": detected intent,
            "via": "proxima|openrouter|local"
        }
    """
    detected_intent = intent or route_intent(message)
    target_model = model or MODEL_ROUTING.get(detected_intent, "auto")

    log.info(f"Routing: intent={detected_intent} → model={target_model}")

    # Local shortcut — don't hit Proxima for quick queries
    if target_model == "local" or detected_intent == "quick":
        text = _ask_local(message)
        if text:
            return {"text": text, "provider": LOCAL_MODEL, "intent": detected_intent, "via": "local"}

    # Try Proxima first
    if _proxima_available():
        proxima_model = target_model if target_model != "local" else "auto"
        text = _ask_proxima(message, model=proxima_model, function=function, **kwargs)
        if text:
            return {"text": text, "provider": proxima_model, "intent": detected_intent, "via": "proxima"}

    # Fallback: OpenRouter
    text = _ask_openrouter(message)
    if text:
        return {"text": text, "provider": OPENROUTER_MODEL, "intent": detected_intent, "via": "openrouter"}

    # Last resort: local Ollama
    if fallback_local:
        text = _ask_local(message)
        if text:
            return {"text": text, "provider": LOCAL_MODEL, "intent": detected_intent, "via": "local_fallback"}

    return {"text": "", "provider": "none", "intent": detected_intent, "via": "failed"}

def ask_text(message: str, **kwargs) -> str:
    """Convenience wrapper — returns just the text."""
    return ask(message, **kwargs).get("text", "")

# ── HERMES PATCH INSTRUCTIONS ─────────────────────────────────────────

HERMES_PATCH = """
To upgrade Hermes to use the smart router:

1. Copy this file to ~/.hermes/echo_proxima_bridge.py

2. In your Hermes bot file, replace the AI call section with:
   from echo_proxima_bridge import ask
   result = ask(user_message)
   reply = result["text"]
   # Log which AI answered:
   # result["via"] = "proxima|openrouter|local"
   # result["provider"] = specific model used

3. The bridge auto-detects:
   - Is Proxima running? → use it (Claude/GPT/Gemini/Perplexity)
   - OpenRouter key available? → fallback
   - Neither? → local qwen3-fast

4. Add to Hermes response embed (optional):
   f"[{result['provider']} via {result['via']}]"
"""

# ── STATUS ────────────────────────────────────────────────────────────

def status():
    proxima_up = _proxima_available()
    or_key = bool(OPENROUTER_KEY)

    print(f"\nEcho Proxima Bridge — Status")
    print(f"{'─'*40}")
    print(f"Proxima (localhost:3210) : {'running ✓' if proxima_up else 'not running ✗'}")
    print(f"OpenRouter key          : {'found ✓' if or_key else 'not found ✗'}")
    print(f"Local Ollama            : ", end="")
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
        print("running ✓")
    except:
        print("not running ✗")

    if proxima_up:
        print(f"\nAvailable via Proxima:")
        try:
            sys.path.insert(0, str(Path.home() / "Proxima/sdk"))
            from proxima import Proxima
            models = Proxima().get_models()
            for m in models:
                name = m.get("id") or m.get("name", "?")
                ready = "✓" if m.get("ready") or m.get("status") == "ready" else "○"
                print(f"  {ready} {name}")
        except Exception as e:
            print(f"  (could not list models: {e})")
    else:
        print(f"\nStart Proxima: cd ~/Proxima && npm start")

    print(f"\nIntent routing:")
    for intent, model in MODEL_ROUTING.items():
        print(f"  {intent:<12} → {model}")
    print()

# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = sys.argv[1:]

    if not args or "--help" in args:
        print(__doc__); sys.exit(0)

    if "--status" in args:
        status(); sys.exit(0)

    if "--patch" in args:
        print(HERMES_PATCH); sys.exit(0)

    # Test query
    message = " ".join(a for a in args if not a.startswith("--"))
    verbose = "--verbose" in args

    intent = route_intent(message)
    print(f"Intent detected: {intent} → {MODEL_ROUTING.get(intent,'auto')}")

    result = ask(message)
    print(f"\nProvider : {result['provider']}")
    print(f"Via      : {result['via']}")
    print(f"\nResponse:\n{result['text']}")
