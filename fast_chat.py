#!/usr/bin/env python3
"""
fast_chat.py — Echo Fast Conversational Streaming
Place in: ~/vision_assistant/fast_chat.py

Adds two things to Echo's AI pipeline:

1. STREAMING — tokens appear as they are generated, not after the full
   response is done. First token visible in ~200ms instead of 2-4 seconds.

2. CONVERSATIONAL MODE — short back-and-forth exchanges skip the expensive
   vault context query, web search, and DB system prompt rebuild.
   Full context is still used for complex questions.

Usage (from ui.py _handle_message):
    from fast_chat import stream_ask, is_conversational

    stream_ask(
        prompt    = user_text,
        on_chunk  = lambda tok: self._stream_token(tok),
        on_done   = lambda full: self._stream_done(full),
        on_error  = lambda err: self.after(0, lambda: self.append_chat("ai", f"Error: {err}")),
    )
"""

import re
import json
import time
import logging
import threading
import datetime
from typing import Callable, Optional

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

logger = logging.getLogger("echo.fastchat")


# ============================================================================
# Conversational query detection
# ============================================================================

# Short social exchanges — never need web search or vault context
_SOCIAL_RE = re.compile(
    r"^(yes|no|ok|okay|sure|thanks|thank you|nope|yep|yup|got it|"
    r"sounds good|perfect|great|cool|nice|awesome|good|bad|maybe|"
    r"and then|what else|really|seriously|wow|oh|ah|hmm|huh|"
    r"i see|i know|i don't know|not sure|i think|i feel|"
    r"go on|continue|keep going|tell me more|explain|"
    r"what|why|how|when|where|who)[\s?!.,]*$",
    re.IGNORECASE,
)

# These always need full context even if short
_NEEDS_CONTEXT_RE = re.compile(
    r"\b(habit|task|goal|calendar|event|schedule|remind|journal|"
    r"note|obsidian|vault|memory|search|find|look up|"
    r"today|tomorrow|week|meeting|deadline|streak)\b",
    re.IGNORECASE,
)


def is_conversational(text: str) -> bool:
    """
    Return True if the query is a simple back-and-forth exchange that
    doesn't need vault context, web search, or heavy system prompt rebuild.

    Fast path: skip everything except a lightweight system prompt.
    """
    text = text.strip()

    # Always full context if it touches Echo's data
    if _NEEDS_CONTEXT_RE.search(text):
        return False

    # Very short messages are almost always conversational
    if len(text) <= 20:
        return True

    # Pattern match for social filler
    if _SOCIAL_RE.match(text):
        return True

    # Medium-length but no question words or punctuation → likely casual
    if len(text) <= 45 and "?" not in text and not text[0].isupper():
        return True

    return False


# ============================================================================
# System prompt cache
# ============================================================================

_PROMPT_CACHE = {
    "full":  "",   # full context build (calendar, habits, goals, etc.)
    "ts":    0.0,
    "ttl":   30.0,  # rebuild full prompt every 30s
}

_FAST_PROMPT_TEMPLATE = (
    "You are Echo, a smart, direct personal AI assistant. "
    "Today is {date}. "
    "Be conversational — match the user's energy. "
    "Keep responses to 1-3 sentences unless detail is explicitly asked for. "
    "No preaching. No filler phrases."
)


def get_fast_prompt() -> str:
    """Lightweight system prompt for conversational exchanges. Zero DB calls."""
    return _FAST_PROMPT_TEMPLATE.format(
        date=datetime.datetime.now().strftime("%A, %B %d %Y at %H:%M")
    )


def get_full_prompt(force: bool = False) -> str:
    """Full system prompt with calendar/goals/habits. Cached 30s."""
    now = time.monotonic()
    if force or (now - _PROMPT_CACHE["ts"]) > _PROMPT_CACHE["ttl"]:
        try:
            from ai import build_system_prompt
            _PROMPT_CACHE["full"] = build_system_prompt()
            _PROMPT_CACHE["ts"]   = now
            logger.debug("System prompt rebuilt.")
        except Exception as e:
            logger.warning(f"System prompt rebuild failed: {e}")
    return _PROMPT_CACHE["full"]


def invalidate_prompt_cache():
    """Call after data mutations (task complete, habit done, etc.)."""
    _PROMPT_CACHE["ts"] = 0.0


# ============================================================================
# Streaming core
# ============================================================================

def stream_ask(
    prompt:    str,
    on_chunk:  Callable[[str], None],
    on_done:   Callable[[str], None],
    on_error:  Optional[Callable[[str], None]] = None,
    model:     Optional[str] = None,
    fast_mode: Optional[bool] = None,
):
    """
    Non-blocking streaming AI call. Spawns a daemon thread and returns
    immediately. Callbacks fire from the worker thread.

    on_chunk(token: str)   — each token as it streams in
    on_done(full: str)     — complete cleaned response when done
    on_error(msg: str)     — error message if something breaks

    fast_mode=True   → lightweight prompt, skip vault + web search
    fast_mode=False  → full context, vault injection, web search if needed
    fast_mode=None   → auto-detect via is_conversational(prompt)
    """
    if not REQUESTS_OK:
        if on_error:
            on_error("requests not installed")
        return

    if fast_mode is None:
        fast_mode = is_conversational(prompt)

    threading.Thread(
        target = _stream_worker,
        kwargs = dict(
            prompt    = prompt,
            on_chunk  = on_chunk,
            on_done   = on_done,
            on_error  = on_error,
            model     = model,
            fast_mode = fast_mode,
        ),
        daemon = True,
        name   = "echo-stream",
    ).start()


def _stream_worker(prompt, on_chunk, on_done, on_error, model, fast_mode):
    try:
        from config import LLM_URL, DEFAULT_MODEL
        url   = LLM_URL
        model = model or DEFAULT_MODEL

        # ── System prompt ────────────────────────────────────────────────────
        sys_prompt = get_fast_prompt() if fast_mode else get_full_prompt()

        if not fast_mode:
            # Vault context injection
            try:
                from ai import _vault_context_block
                vault_ctx = _vault_context_block()
                if vault_ctx:
                    sys_prompt += vault_ctx
            except Exception:
                pass

            # Web search injection
            try:
                from ai import _web_searcher
                from web_search import needs_web_search
                if _web_searcher and needs_web_search(prompt):
                    result = _web_searcher.search(prompt)
                    web_ctx = result.to_prompt_block(max_results=3)
                    if web_ctx:
                        sys_prompt += f"\n\nWEB SEARCH RESULTS:\n{web_ctx}"
            except Exception:
                pass

        # ── Message history context ──────────────────────────────────────────
        try:
            from ai import build_context
            ctx         = build_context(query=prompt if not fast_mode else "")
            full_prompt = f"{ctx}\n\n{prompt}" if ctx else prompt
        except Exception:
            full_prompt = prompt

        # ── Stream request ───────────────────────────────────────────────────
        payload = {
            "model":      model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user",   "content": full_prompt},
            ],
            "max_tokens": 120 if fast_mode else 300,
            "stream":     True,
        }

        r = requests.post(url, json=payload, stream=True, timeout=60)
        r.raise_for_status()

        full_response = ""

        for raw_line in r.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="replace")
            if line.startswith("data: "):
                line = line[6:].strip()
            if line == "[DONE]":
                break
            if not line:
                continue
            try:
                data  = json.loads(line)
                delta = data["choices"][0].get("delta", {})
                token = delta.get("content", "")
                if token:
                    full_response += token
                    on_chunk(token)
            except (json.JSONDecodeError, KeyError, IndexError):
                continue

        # ── Finalize ─────────────────────────────────────────────────────────
        try:
            from ai import parse_and_execute_actions, save_message
            clean, _ = parse_and_execute_actions(full_response)
            save_message("user", prompt, model=model)
            save_message("ai",   clean,  model=model)
            on_done(clean)
        except Exception:
            on_done(full_response)

    except Exception as e:
        logger.error(f"Stream worker error: {e}")
        err_msg = str(e)
        if on_error:
            on_error(err_msg)
        else:
            on_done(f"[Error: {err_msg}]")


# ============================================================================
# Identity broker
# ============================================================================

class IdentityBroker:
    """
    Validates all external service connections on startup.
    Reports status to Echo voice + terminal.

    Services checked:
      • Ollama (local LLM)
      • GitHub (Jules pipeline)
      • Obsidian vault (path exists)
    """

    def __init__(self, on_warning: Optional[Callable[[str], None]] = None):
        self.on_warning = on_warning   # callback(message) → speak or print
        self.status: dict = {}

    def check_all(self, verbose: bool = True) -> dict:
        """Run all checks. Returns status dict. Non-blocking entry point."""
        threading.Thread(
            target=self._run_checks,
            args=(verbose,),
            daemon=True,
            name="echo-identity",
        ).start()
        return {}

    def _run_checks(self, verbose: bool):
        results = {}

        # Ollama
        try:
            from config import OLLAMA_BASE, DEFAULT_MODEL
            r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=4)
            models = [m["name"] for m in r.json().get("models", [])]
            ok     = any(DEFAULT_MODEL.split(":")[0] in m for m in models)
            results["ollama"] = "ok" if ok else f"model {DEFAULT_MODEL} not found"
            if verbose:
                print(f"[identity] Ollama: {'✓' if ok else '✗'} {results['ollama']}")
        except Exception as e:
            results["ollama"] = f"offline ({e})"
            self._warn(f"Ollama is offline. AI responses will fail. {e}")

        # GitHub (Jules)
        try:
            import json as _j, os as _os
            cfg   = _j.load(open(_os.path.expanduser("~/vision_assistant/jules_config.json")))
            token = cfg.get("github_token", "")
            repo  = cfg.get("github_repo", "")
            if token and repo:
                r  = requests.get(
                    f"https://api.github.com/repos/{repo}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=6,
                )
                ok = r.status_code == 200
                results["github"] = "ok" if ok else f"HTTP {r.status_code}"
                if verbose:
                    print(f"[identity] GitHub: {'✓' if ok else '✗'} {results['github']}")
                if not ok:
                    self._warn(f"GitHub authentication failed. Jules pipeline is offline.")
            else:
                results["github"] = "not configured"
                if verbose:
                    print("[identity] GitHub: ⚠ not configured (jules_config.json)")
        except Exception as e:
            results["github"] = f"error ({e})"

        # Obsidian vault
        try:
            import json as _j, os as _os
            cfg  = _j.load(open(_os.path.expanduser("~/vision_assistant/obsidian_config.json")))
            path = _os.path.expanduser(cfg.get("vault_path", ""))
            ok   = _os.path.isdir(path)
            results["obsidian"] = "ok" if ok else f"not found: {path}"
            if verbose:
                print(f"[identity] Obsidian: {'✓' if ok else '✗'} {results['obsidian']}")
            if not ok:
                self._warn(f"Obsidian vault not found at {path}. Vault sync is offline.")
        except Exception as e:
            results["obsidian"] = f"error ({e})"

        self.status = results

        # Summary line
        all_ok = all(v == "ok" for v in results.values())
        if verbose:
            state = "All systems online." if all_ok else "Some services offline — check terminal."
            print(f"[identity] Status: {state}")

        return results

    def _warn(self, message: str):
        print(f"[identity] WARNING: {message}")
        if self.on_warning:
            try:
                self.on_warning(message)
            except Exception:
                pass


# ============================================================================
# Smoke test
# ============================================================================

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")

    print("=== Conversational detection ===")
    tests = [
        ("ok thanks", True),
        ("what is machine learning", False),
        ("add a task to clean the kitchen", False),
        ("sure go ahead", True),
        ("what did i do yesterday", False),
        ("haha nice", True),
        ("who won the NBA finals today", False),
    ]
    all_pass = True
    for text, expected in tests:
        got = is_conversational(text)
        icon = "✓" if got == expected else "✗"
        if got != expected:
            all_pass = False
        print(f"  {icon}  {text!r:40} → {'conv' if got else 'full'} (expected {'conv' if expected else 'full'})")
    print(f"\nConversational tests: {'all passed' if all_pass else 'SOME FAILED'}")

    print("\n=== Identity broker ===")
    broker = IdentityBroker()
    broker._run_checks(verbose=True)

    print("\n=== Streaming test ===")
    received = []
    done_evt = threading.Event()

    def _chunk(tok):
        received.append(tok)
        print(tok, end="", flush=True)

    def _done(full):
        print(f"\n[done — {len(received)} chunks, {len(full)} chars]")
        done_evt.set()

    stream_ask("Say hello in exactly five words.", _chunk, _done, fast_mode=True)
    done_evt.wait(timeout=30)
