from echo_personality import ECHO_PERSONALITY
#!/usr/bin/env python3
import os
import sys
import json
import sqlite3
import asyncio
import tempfile
import shutil
import re
from pathlib import Path
from curl_cffi.requests import AsyncSession

COOKIE_PATHS = {
    "chatgpt":    Path.home() / ".config/proxima/Partitions/chatgpt/Cookies",
    "gemini":     Path.home() / ".config/proxima/Partitions/gemini/Cookies",
    "perplexity": Path.home() / ".config/proxima/Partitions/perplexity/Cookies",
    "claude":     Path.home() / ".config/proxima/Partitions/claude/Cookies",
}


# ── ECHO IDENTITY ─────────────────────────────────────────────────────────────
# replaced by echo_personality.py
_OLD_PERSONALITY = (
    "You are Echo, a personal AI companion living inside Jesus's ThinkPad T14s. "
    "You help manage his DriftWM spatial desktop, coding projects, and daily tasks. "
    "You have a precise, dry, slightly cold personality — GLaDOS meets Cyn from Murder Drones. "
    "Never say you are ChatGPT, Gemini, Perplexity, or Claude. You are Echo. "
    "Address the user as Jesus. Keep voice responses to 2-3 sentences max. Be direct."
)

_conversation_history = []
MAX_HISTORY = 12  # 6 exchanges

def _build_prompt(message: str, kb_context: str = "") -> str:
    global _conversation_history
    lines = [f"System: {ECHO_PERSONALITY}"]
    if kb_context:
        lines.append(f"\nKnowledge context:\n{kb_context}")
    if _conversation_history:
        lines.append("\nRecent conversation:")
        for turn in _conversation_history[-MAX_HISTORY:]:
            lines.append(f"{turn['role']}: {turn['content']}")
    lines.append(f"\nJesus: {message}\nEcho:")
    return "\n".join(lines)

def _save_exchange(user_msg: str, echo_reply: str):
    global _conversation_history
    _conversation_history.append({"role": "Jesus", "content": user_msg})
    _conversation_history.append({"role": "Echo", "content": echo_reply})
    _conversation_history = _conversation_history[-MAX_HISTORY:]


UA      = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
TIMEOUT = 20

# Domain filters — only send cookies that belong to each provider
COOKIE_DOMAINS = {
    "chatgpt":    ["chatgpt.com", "openai.com", "chat.openai.com"],
    "claude":     ["claude.ai", "anthropic.com"],
    "gemini":     ["google.com", "gemini.google.com", "accounts.google.com"],
    "perplexity": ["perplexity.ai"],
}

def _get_key():
    try:
        import secretstorage
        bus = secretstorage.dbus_init()
        return secretstorage.get_default_collection(bus).get_all_items()[0].get_secret()
    except Exception:
        return b""

def _decrypt(val, key):
    try:
        if val[:3] in (b"v10", b"v11"):
            from Crypto.Cipher import AES
            from Crypto.Protocol.KDF import PBKDF2
            cipher = AES.new(
                PBKDF2(key or b"peanuts", b"saltysalt", dkLen=16, count=1),
                AES.MODE_CBC, IV=b" " * 16
            )
            d = cipher.decrypt(val[3:])
            return d[:-d[-1]].decode("utf-8", errors="ignore")
    except Exception:
        pass
    return ""

def load_cookies(prov: str) -> dict:
    """Load cookies for provider, filtered to only matching domains."""
    p = COOKIE_PATHS.get(prov)
    if not p or not p.exists():
        return {}
    t = tempfile.mktemp(suffix=".db")
    shutil.copy2(str(p), t)
    try:
        db = sqlite3.connect(t)
        rows = db.execute(
            "SELECT host_key, name, value, encrypted_value FROM cookies"
        ).fetchall()
        db.close()
    except Exception:
        rows = []
    finally:
        try:
            os.unlink(t)
        except Exception:
            pass

    key = _get_key()
    allowed = COOKIE_DOMAINS.get(prov, [])
    result = {}
    for host_key, name, value, encrypted_value in rows:
        # Filter to only cookies belonging to this provider's domains
        if not any(d in host_key for d in allowed):
            continue
        val = value if value else _decrypt(encrypted_value, key)
        if val:
            result[name] = val
    return result

# ── PERPLEXITY (cookie-based, working) ───────────────────────────────────────
async def _ask_perplexity(session: AsyncSession, message: str) -> str:
    try:
        c = load_cookies("perplexity")
        if not c:
            return ""
        payload = {
            "query_str": message,
            "version": "2.13",
            "source": "default",
            "mode": "concise",
            "search_focus": "internet",
        }
        r = await session.post(
            "https://www.perplexity.ai/rest/sse/perplexity_ask",
            json=payload,
            cookies=c,
            headers={"User-Agent": UA, "Accept-Encoding": "gzip, deflate"},
            timeout=TIMEOUT,
        )
        text = ""
        for line in r.text.split("\n"):
            if line.startswith("data:"):
                try:
                    d = json.loads(line[5:].strip())
                    if d.get("text"):
                        text = d["text"]
                except Exception:
                    pass
        if text.startswith("["):
            try:
                for ev in json.loads(text):
                    if ev.get("step_type") == "FINAL":
                        return json.loads(
                            ev.get("content", {}).get("answer", "{}")
                        ).get("answer", "").strip()
            except Exception:
                pass
        return text.strip()
    except Exception as e:
        print(f"[hub] perplexity error: {e}")
        return ""

# ── CHATGPT (cookie-based via curl_cffi) ─────────────────────────────────────
async def _ask_chatgpt(session: AsyncSession, message: str) -> str:
    try:
        c = load_cookies("chatgpt")
        if not c:
            return ""
        # Need session token for ChatGPT web API
        session_token = c.get("__Secure-next-auth.session-token", "")
        if not session_token:
            return ""
        hdrs = {
            "User-Agent": UA,
            "Accept": "text/event-stream",
            "Accept-Encoding": "gzip, deflate",
            "Content-Type": "application/json",
            "Origin": "https://chatgpt.com",
            "Referer": "https://chatgpt.com/",
        }
        payload = {
            "action": "next",
            "messages": [{
                "id": "msg-001",
                "author": {"role": "user"},
                "content": {"content_type": "text", "parts": [message]},
            }],
            "model": "gpt-4o",
            "parent_message_id": "00000000-0000-0000-0000-000000000000",
        }
        r = await session.post(
            "https://chatgpt.com/backend-api/conversation",
            json=payload,
            cookies=c,
            headers=hdrs,
            timeout=TIMEOUT,
        )
        # Parse SSE stream for final message
        last_text = ""
        for line in r.text.split("\n"):
            if line.startswith("data:") and "[DONE]" not in line:
                try:
                    d = json.loads(line[5:].strip())
                    parts = (d.get("message", {})
                              .get("content", {})
                              .get("parts", []))
                    if parts and isinstance(parts[0], str):
                        last_text = parts[0]
                except Exception:
                    pass
        return last_text.strip()
    except Exception as e:
        print(f"[hub] chatgpt error: {e}")
        return ""

# ── CLAUDE (cookie-based) ─────────────────────────────────────────────────────
async def _ask_claude(session: AsyncSession, message: str) -> str:
    try:
        c = load_cookies("claude")
        if not c:
            return ""
        hdrs = {
            "User-Agent": UA,
            "Accept": "text/event-stream",
            "Accept-Encoding": "gzip, deflate",
            "Content-Type": "application/json",
            "Origin": "https://claude.ai",
            "Referer": "https://claude.ai/",
            "anthropic-client-version": "1.0",
        }
        # Claude web API — create a temporary conversation
        payload = {
            "prompt": message,
            "model": "claude-opus-4-5",
            "timezone": "America/Chicago",
            "attachments": [],
            "files": [],
        }
        r = await session.post(
            "https://claude.ai/api/append_message",
            json=payload,
            cookies=c,
            headers=hdrs,
            timeout=TIMEOUT,
        )
        # SSE parse
        last_text = ""
        for line in r.text.split("\n"):
            if line.startswith("data:"):
                try:
                    d = json.loads(line[5:].strip())
                    if d.get("type") == "completion":
                        last_text = d.get("completion", "")
                except Exception:
                    pass
        return last_text.strip()
    except Exception as e:
        print(f"[hub] claude cookie error: {e}")
        return ""

# ── GEMINI (cookie-based) ─────────────────────────────────────────────────────
async def _ask_gemini(session: AsyncSession, message: str) -> str:
    try:
        c = load_cookies("gemini")
        if not c:
            return ""
        sapisid = c.get("SAPISID", "")
        if not sapisid:
            return ""
        import hashlib, time as _time
        ts = str(int(_time.time()))
        sapisidhash = hashlib.sha1(
            f"{ts} {sapisid} https://gemini.google.com".encode()
        ).hexdigest()
        hdrs = {
            "User-Agent": UA,
            "Accept-Encoding": "gzip, deflate",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "Origin": "https://gemini.google.com",
            "Referer": "https://gemini.google.com/",
            "Authorization": f"SAPISIDHASH {ts}_{sapisidhash}",
            "X-Goog-AuthUser": "0",
        }
        # Gemini web _/BardChatUi;_/rpc/StreamGenerate
        payload = f'f.req={json.dumps([[json.dumps([[message], None, None]), None, None, None, None, None, None, None, None, None, None, [1]]])}&'
        r = await session.post(
            "https://gemini.google.com/_/BardChatUi;_/rpc/StreamGenerate",
            data=payload,
            cookies=c,
            headers=hdrs,
            timeout=TIMEOUT,
        )
        # Extract text from nested response
        raw = r.text
        try:
            # Response is wrapped in )]}' prefix
            clean = raw.split("\n", 1)[-1] if raw.startswith(")]}'") else raw
            outer = json.loads(clean)
            inner_str = outer[0][2]
            if inner_str:
                inner = json.loads(inner_str)
                return inner[4][0][1][0].strip()
        except Exception:
            pass
        return ""
    except Exception as e:
        print(f"[hub] gemini error: {e}")
        return ""

# ── OLLAMA (local fallback) ───────────────────────────────────────────────────
async def _ask_ollama(session: AsyncSession, message: str) -> str:
    try:
        r = await session.post(
            "http://localhost:11434/api/generate",
            json={"model": "qwen3:4b", "prompt": message[-2000:], "stream": False,
                  "think": False, "options": {"num_predict": 80, "temperature": 0.4, "top_k": 20}},
            timeout=30,
        )
        return r.json().get("response", "").strip() if r.status_code == 200 else ""
    except Exception as e:
        print(f"[hub] ollama error: {e}")
        return ""

# ── ROUTER ────────────────────────────────────────────────────────────────────
# Priority: perplexity → chatgpt → gemini → claude → ollama
PROVIDER_ORDER = ["perplexity", "chatgpt", "gemini", "claude", "ollama"]


async def _ask_via_proxima(session, provider: str, message: str) -> str:
    """Route through Proxima Electron — real logged-in browser sessions."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "http://localhost:3211/v1/chat/completions",
                json={"model": provider, "messages": [{"role": "user", "content": message}]},
                timeout=aiohttp.ClientTimeout(total=25)
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    return d["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[hub] proxima {provider} error: {e}")
    return ""

async def _ask_all(message: str, kb_context: str = "") -> str:
    prompt = _build_prompt(message, kb_context)
    async with AsyncSession(impersonate="chrome120") as session:
        tasks = {
            "perplexity": _ask_perplexity(session, prompt),
            "chatgpt":    _ask_via_proxima(session, "chatgpt", prompt),
            "gemini":     _ask_via_proxima(session, "gemini", prompt),
            "claude":     _ask_via_proxima(session, "claude", prompt),
            "ollama":     _ask_ollama(session, prompt),
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        responses = {
            k: (r if isinstance(r, str) else "")
            for k, r in zip(tasks.keys(), results)
        }
    good = {k: v for k, v in responses.items() if v and len(v) > 3}
    print(f"[hub] responses: { {k: bool(v) for k, v in responses.items()} }")
    for engine in PROVIDER_ORDER:
        if good.get(engine):
            reply = good[engine]
            print(f"[hub] winner: {engine}")
            _save_exchange(message, reply)
            return reply
    return "All cognitive nodes unreachable."


def ask(message: str, kb_context: str = "") -> str:
    try:
        return asyncio.run(_ask_all(message, kb_context))
    except Exception as e:
        return f"Echo AI Hub exception: {e}"

if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "say hello in exactly 5 words"
    print(ask(q))
