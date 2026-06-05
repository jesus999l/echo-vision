#!/usr/bin/env python3
"""
echo_proxima_native.py v4
=========================
Hybrid approach based on Proxima's actual source code:

  claude      → api.claude.ai  (org-based SSE, credentials:include equivalent)
  gemini      → BardChatUi SSE (SNlM0e + cfb2h tokens from page)
  perplexity  → /rest/sse/perplexity_ask (read_write_token from __NEXT_DATA__)
  grok        → grok.com/rest/app-chat (SSO token)
  chatgpt     → PROXIED through Proxima:3210 (POW requires real browser)
  ollama      → localhost:11434 (local fallback)

ChatGPT requires SHA3-512 proof-of-work solvable only in browser context.
We forward those requests to the running Proxima instance.

Run:
  python3 echo_proxima_native.py --port 3211  # use 3211 if Proxima uses 3210
  # or kill Proxima and use 3210
"""

import asyncio, json, logging, os, re, sys, time, uuid, hashlib
from pathlib import Path
from typing import Optional, AsyncGenerator

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse, StreamingResponse
    from pydantic import BaseModel
    import uvicorn, aiohttp
except ImportError:
    print("Run: pip install fastapi uvicorn aiohttp"); sys.exit(1)

PORT         = int(os.environ.get("PROXIMA_PORT", 3211))  # 3211 = alongside Proxima
HOST         = os.environ.get("PROXIMA_HOST", "127.0.0.1")
COOKIE_DIR   = Path.home() / ".echo" / "cookies"
LOG_LEVEL    = os.environ.get("PROXIMA_LOG", "INFO")
OLLAMA_BASE  = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:0.5b"
PROXIMA_UPSTREAM = "http://localhost:3210"  # Real Proxima for ChatGPT POW

COOKIE_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=getattr(logging, LOG_LEVEL),
                    format="%(asctime)s [echo-proxima] %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("echo-proxima")

# ── Cookie helpers ────────────────────────────────────────────────────────────

def load_cookies(provider: str) -> dict:
    path = COOKIE_DIR / f"{provider}.json"
    if not path.exists(): return {}
    try:
        return {c["name"]: c["value"]
                for c in json.loads(path.read_text())
                if c.get("name") and c.get("value")}
    except Exception as e:
        log.warning(f"[{provider}] cookie load: {e}")
        return {}

def cookie_str(provider: str) -> str:
    return "; ".join(f"{k}={v}" for k, v in load_cookies(provider).items())

def has_cookies(provider: str) -> bool:
    p = COOKIE_DIR / f"{provider}.json"
    if not p.exists(): return False
    try:
        d = json.loads(p.read_text())
        return isinstance(d, list) and len(d) > 0
    except: return False

# ── Claude — matches Proxima claude-engine.js exactly ────────────────────────

class ClaudeSession:
    def __init__(self):
        self._org_id = None
        self._conv_id = None

    async def ask(self, prompt: str) -> str:
        cookies = load_cookies("claude")
        if not cookies.get("sessionKey"):
            return "[Claude] No sessionKey — export cookies from claude.ai"

        hdrs = {
            "Cookie": cookie_str("claude"),
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Referer": "https://claude.ai/",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        }

        async with aiohttp.ClientSession() as s:
            # Get org ID (cached)
            if not self._org_id:
                async with s.get("https://api.claude.ai/api/organizations",
                                  headers={**hdrs, "Accept": "application/json"},
                                  timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status in (401, 403):
                        return "[Claude] Not logged in — refresh cookies"
                    if not r.ok:
                        return f"[Claude] org fetch failed: {r.status}"
                    orgs = await r.json()
                    if not orgs:
                        return "[Claude] No organization found"
                    self._org_id = orgs[0]["uuid"]
                    log.info(f"[claude] org: {self._org_id[:8]}...")

            # Create conversation if needed
            if not self._conv_id:
                async with s.post(
                    f"https://api.claude.ai/api/organizations/{self._org_id}/chat_conversations",
                    json={"name": prompt[:50].replace("\n", " ").strip(),
                          "project_uuid": None, "is_starred": False},
                    headers={**hdrs, "Accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    if not r.ok:
                        if r.status in (401, 403):
                            self._org_id = None
                            return f"[Claude] Auth error {r.status}"
                        return f"[Claude] Conv create failed: {r.status}"
                    conv = await r.json()
                    self._conv_id = conv.get("uuid", "")
                    log.info(f"[claude] conv: {self._conv_id[:8]}...")

            # Send message — SSE stream exactly like Proxima
            try:
                full = ""
                async with s.post(
                    f"https://api.claude.ai/api/organizations/{self._org_id}/chat_conversations/{self._conv_id}/completion",
                    json={"prompt": prompt,
                          "timezone": "America/Chicago",
                          "attachments": [], "files": []},
                    headers=hdrs,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as r:
                    if r.status in (404, 410):
                        # Conv expired — reset and retry
                        self._conv_id = None
                        return await self.ask(prompt)
                    if r.status == 429:
                        return "[Claude] Rate limited"
                    if not r.ok:
                        body = await r.text()
                        return f"[Claude] {r.status}: {body[:200]}"

                    async for line in r.content:
                        line = line.decode("utf-8", errors="ignore").strip()
                        if not line.startswith("data:"): continue
                        data = line[5:].strip()
                        if not data: continue
                        try:
                            parsed = json.loads(data)
                            if parsed.get("type") == "content_block_delta":
                                delta = parsed.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    full += delta.get("text", "")
                            if parsed.get("completion"):
                                full += parsed["completion"]
                        except: pass

                return full.strip() or "[Claude] Empty response"

            except asyncio.TimeoutError:
                return "[Claude] Timeout"
            except Exception as e:
                if "404" in str(e) or "410" in str(e):
                    self._conv_id = None
                return f"[Claude error: {e}]"

    def reset(self):
        self._conv_id = None

_claude = ClaudeSession()

# ── Gemini — matches Proxima gemini-engine.js exactly ────────────────────────

class GeminiSession:
    def __init__(self):
        self._tokens = None
        self._tokens_at = 0
        self._conv_id = ""
        self._response_id = ""
        self._choice_id = ""
        TOKEN_TTL = 300  # 5 min

    async def _get_tokens(self, force=False) -> dict:
        if self._tokens and not force and (time.time() - self._tokens_at) < 300:
            return self._tokens
        hdrs = {"Cookie": cookie_str("gemini"),
                "User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as s:
            async with s.get("https://gemini.google.com/faq",
                              headers=hdrs,
                              timeout=aiohttp.ClientTimeout(total=30)) as r:
                if not r.ok:
                    raise Exception(f"Gemini page fetch failed: {r.status}")
                html = await r.text()
                if "$authuser" not in html:
                    raise Exception("Not logged into Google")
                try:
                    at = html.split("SNlM0e")[1].split('":"')[1].split('"')[0]
                except:
                    raise Exception("Failed to extract SNlM0e token")
                try:
                    bl = html.split("cfb2h")[1].split('":"')[1].split('"')[0]
                except:
                    raise Exception("Failed to extract cfb2h token")
                self._tokens = {"at": at, "bl": bl}
                self._tokens_at = time.time()
                return self._tokens

    def _parse_response(self, raw: str) -> str:
        """Mirrors Proxima's _parseResponse exactly."""
        clean = re.sub(r"^\)\]}'?\s*\n?", "", raw)
        lines = [l for l in clean.split("\n") if l.strip()]

        all_items = []
        data_indices = []

        for line in lines:
            try:
                arr = json.loads(line)
                if not isinstance(arr, list): continue
                for item in arr:
                    if not isinstance(item, list): continue
                    for idx in range(min(len(item), 6)):
                        if isinstance(item[idx], str) and len(item[idx]) > 50:
                            try:
                                json.loads(item[idx])
                                all_items.append(item)
                                data_indices.append(idx)
                                break
                            except: pass
            except: pass

        if not all_items:
            # Fallback: find JSON strings recursively
            def deep_search(obj, found):
                if isinstance(obj, str) and len(obj) > 50:
                    try: json.loads(obj); found.append(obj)
                    except: pass
                elif isinstance(obj, list):
                    for x in obj: deep_search(x, found)
            found = []
            for line in lines:
                try: deep_search(json.loads(line), found)
                except: pass
            for s in found:
                all_items.append([None, None, s])
                data_indices.append(2)

        if not all_items:
            raise Exception("Failed to parse Gemini response")

        # Extract conversation context
        try:
            inner = json.loads(all_items[0][data_indices[0]])
            if isinstance(inner[1], list):
                if isinstance(inner[1][0], str) and len(inner[1][0]) > 5:
                    self._conv_id = inner[1][0]
                if isinstance(inner[1][1], str) and len(inner[1][1]) > 5:
                    self._response_id = inner[1][1]
            if inner[4] and inner[4][0] and isinstance(inner[4][0][0], str):
                self._choice_id = inner[4][0][0]
        except: pass

        # Extract reply text — multiple paths like Proxima
        reply = ""
        for item, idx in zip(all_items, data_indices):
            try:
                inner = json.loads(item[idx])
                candidates = []
                try: candidates.append((inner[0][0] if isinstance(inner[0], list) and isinstance(inner[0][0], str) else ""))
                except: pass
                try: candidates.append(str(inner[4][0][1][0]) if inner[4] and inner[4][0] and inner[4][0][1] else "")
                except: pass
                try: candidates.append(str(inner[1][0]) if isinstance(inner[1], list) and isinstance(inner[1][0], str) else "")
                except: pass
                for c in candidates:
                    if isinstance(c, str) and len(c) > len(reply):
                        reply = c
            except: pass

        if not reply:
            raise Exception("Could not extract reply from Gemini")
        return reply

    async def ask(self, prompt: str) -> str:
        try:
            tokens = await self._get_tokens()
        except Exception as e:
            return f"[Gemini] Token error: {e}"

        req_id = str(int(time.time() * 1000))
        conv_ctx = [self._conv_id, self._response_id, self._choice_id]

        params = f"bl={tokens['bl']}&rt=c&_reqid={req_id}"
        body_data = {
            "at": tokens["at"],
            "f.req": json.dumps([None, json.dumps([[prompt], None, conv_ctx])])
        }
        body_str = "&".join(f"{k}={v}" for k, v in body_data.items())
        url = f"https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate?{params}"
        hdrs = {
            "Cookie": cookie_str("gemini"),
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "x-same-domain": "1",
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://gemini.google.com/app",
        }

        async with aiohttp.ClientSession() as s:
            async with s.post(url, data=body_str, headers=hdrs,
                               timeout=aiohttp.ClientTimeout(total=120)) as r:
                if r.status == 400:
                    # Token expired — refresh and retry
                    self._tokens = None
                    return await self.ask(prompt)
                if not r.ok:
                    return f"[Gemini] {r.status}"
                raw = await r.text()
                try:
                    return self._parse_response(raw)
                except Exception as e:
                    return f"[Gemini parse error: {e}]"

    def reset(self):
        self._conv_id = self._response_id = self._choice_id = ""

_gemini = GeminiSession()

# ── Perplexity — matches Proxima perplexity-engine.js exactly ─────────────────

class PerplexitySession:
    def __init__(self):
        self._last_backend_uuid = None

    async def ask(self, prompt: str) -> str:
        cookies = load_cookies("perplexity")
        if not cookies:
            return "[Perplexity] No cookies found"

        # Perplexity uses read_write_token from __NEXT_DATA__ in page
        # We get it from the session endpoint
        session_token = cookies.get("__Secure-next-auth.session-token", "")

        # Build params exactly like Proxima
        frontend_uuid = str(uuid.uuid4())
        params = {
            "last_backend_uuid": self._last_backend_uuid or str(uuid.uuid4()),
            "read_write_token": session_token,
            "attachments": [],
            "language": "en-US",
            "timezone": "America/Chicago",
            "search_focus": "internet",
            "sources": ["web"],
            "frontend_uuid": frontend_uuid,
            "mode": "copilot",
            "model_preference": "turbo",
            "is_related_query": False,
            "is_sponsored": False,
            "prompt_source": "user",
            "query_source": "followup" if self._last_backend_uuid else "home",
            "is_incognito": False,
            "time_from_first_type": 2500,
            "local_search_enabled": False,
            "use_schematized_api": True,
            "send_back_text_in_streaming_api": True,
            "supported_block_use_cases": [
                "answer_modes","media_items","knowledge_cards","inline_entity_cards",
                "place_widgets","finance_widgets","news_widgets","shopping_widgets",
                "search_result_widgets","inline_images","diff_blocks",
                "inline_knowledge_cards","refinement_filters","answer_tabs",
                "preserve_latex","in_context_suggestions","pending_followups",
                "inline_claims","unified_assets"
            ],
            "client_coordinates": None,
            "mentions": [],
            "skip_search_enabled": True,
            "source": "default",
            "always_search_override": False,
            "override_no_search": False,
            "extended_context": False,
            "version": "2.18"
        }

        hdrs = {
            "Cookie": cookie_str("perplexity"),
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "x-perplexity-request-endpoint": "https://www.perplexity.ai/rest/sse/perplexity_ask",
            "x-perplexity-request-reason": "perplexity-query-state-provider",
            "x-perplexity-request-try-number": "1",
            "x-request-id": frontend_uuid,
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.perplexity.ai/",
        }

        answer = ""
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://www.perplexity.ai/rest/sse/perplexity_ask",
                    json={"params": params, "query_str": prompt},
                    headers=hdrs,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as r:
                    if r.status in (401, 403):
                        return "[Perplexity] Not logged in — refresh cookies"
                    if r.status == 429:
                        return "[Perplexity] Rate limited"
                    if not r.ok:
                        return f"[Perplexity] {r.status}"

                    async for line in r.content:
                        line = line.decode("utf-8", errors="ignore").strip()
                        if not line.startswith("data:"): continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]": continue
                        try:
                            parsed = json.loads(data)
                            if parsed.get("backend_uuid"):
                                self._last_backend_uuid = parsed["backend_uuid"]
                            # Answer in blocks[].markdown_block.answer (Proxima's key finding)
                            for block in parsed.get("blocks", []):
                                mb = block.get("markdown_block", {})
                                if mb.get("answer") and len(mb["answer"]) > len(answer):
                                    answer = mb["answer"]
                                if mb.get("chunks"):
                                    chunked = "".join(mb["chunks"])
                                    if len(chunked) > len(answer):
                                        answer = chunked
                            if parsed.get("answer") and len(parsed["answer"]) > len(answer):
                                answer = parsed["answer"]
                            # NOTE: parsed.text is intentionally ignored (Proxima comment)
                        except: pass

            # Strip citation markers
            answer = re.sub(r"\[\d+\]", "", answer).strip()
            return answer or "[Perplexity] Empty response"

        except Exception as e:
            return f"[Perplexity error: {e}]"

    def reset(self):
        self._last_backend_uuid = None

_perplexity = PerplexitySession()

# ── Grok ──────────────────────────────────────────────────────────────────────

async def ask_grok(prompt: str) -> str:
    cookies = load_cookies("grok")
    if not cookies.get("sso"):
        return "[Grok] No SSO cookie"
    try:
        full = ""
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://grok.com/rest/app-chat/conversations/new",
                json={"responses": [], "systemPromptName": "",
                      "grokModelOptionId": "grok-3",
                      "conversationId": str(uuid.uuid4()),
                      "message": prompt,
                      "imageAttachments": [],
                      "returnSearchResults": False,
                      "returnCitations": False,
                      "promptSource": "CHAT_INPUT",
                      "requestFeatures": {"eagerTweets": False}},
                headers={"Cookie": cookie_str("grok"),
                         "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                         "Content-Type": "application/json",
                         "Referer": "https://grok.com/",
                         "Origin": "https://grok.com"},
                timeout=aiohttp.ClientTimeout(total=120)
            ) as r:
                if not r.ok:
                    return f"[Grok] {r.status}"
                async for line in r.content:
                    line = line.decode("utf-8", errors="ignore").strip()
                    if not line: continue
                    try:
                        d = json.loads(line)
                        t = d.get("result", {}).get("response", {}).get("token", "")
                        if t: full += t
                    except: pass
        return full.strip() or "[Grok] Empty response"
    except Exception as e:
        return f"[Grok error: {e}]"

# ── ChatGPT — forward to Proxima (needs POW in real browser) ─────────────────

async def ask_chatgpt(prompt: str) -> str:
    """
    Forward to running Proxima instance.
    ChatGPT requires SHA3-512 proof-of-work solvable only in browser context.
    Proxima handles this via Electron's Chromium.
    """
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{PROXIMA_UPSTREAM}/v1/chat/completions",
                json={"model": "chatgpt",
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=aiohttp.ClientTimeout(total=120)
            ) as r:
                if not r.ok:
                    return f"[ChatGPT via Proxima] {r.status}"
                data = await r.json()
                return (data.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                            .strip() or "[ChatGPT] Empty")
    except Exception as e:
        return f"[ChatGPT unavailable — Proxima not running: {e}]"

# ── Ollama fallback ───────────────────────────────────────────────────────────

async def ask_ollama(prompt: str) -> str:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{OLLAMA_BASE}/api/generate",
                               json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                               timeout=aiohttp.ClientTimeout(total=60)) as r:
                return (await r.json()).get("response", "").strip()
    except Exception as e:
        return f"[Ollama error: {e}]"

# ── Provider registry + routing ───────────────────────────────────────────────

PROVIDERS = {
    "claude":     lambda p: _claude.ask(p),
    "gemini":     lambda p: _gemini.ask(p),
    "perplexity": lambda p: _perplexity.ask(p),
    "grok":       ask_grok,
    "chatgpt":    ask_chatgpt,
    "ollama":     ask_ollama,
}

ROUTING = {
    "code":    ["claude", "chatgpt", "ollama"],
    "search":  ["perplexity", "gemini", "ollama"],
    "plan":    ["claude", "chatgpt", "ollama"],
    "analyze": ["chatgpt", "gemini", "ollama"],
    "default": ["chatgpt", "gemini", "grok", "claude", "perplexity", "ollama"],
}
INTENT_KW = {
    "code":    ["python","javascript","code","function","debug","error","script","def ","class "],
    "search":  ["latest","current","2026","news","who is","what is","when did","today"],
    "plan":    ["plan","architect","design","strategy","pipeline","workflow"],
    "analyze": ["analyze","review","compare","explain","why","difference"],
}

def detect_intent(p: str) -> str:
    pl = p.lower()
    scores = {k: sum(1 for kw in v if kw in pl) for k, v in INTENT_KW.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "default"

def available() -> list:
    avail = []
    for p in PROVIDERS:
        if p == "ollama": avail.append(p)
        elif p == "chatgpt": avail.append(p)  # always try via Proxima
        elif has_cookies(p): avail.append(p)
    return avail

def pick(model: str, prompt: str) -> str:
    avail = available()
    if model in avail: return model
    for c in ROUTING.get(detect_intent(prompt), ROUTING["default"]):
        if c in avail: return c
    return "ollama"

# ── FastAPI ───────────────────────────────────────────────────────────────────

app = FastAPI(title="Echo Proxima Native v4")

class ChatMessage(BaseModel):
    role: str; content: str
class ChatRequest(BaseModel):
    model: str = "auto"; messages: list[ChatMessage]
    stream: bool = False; max_tokens: Optional[int] = None
    temperature: Optional[float] = None

def mkresponse(content, model, rid=None):
    return {"id": rid or f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion", "created": int(time.time()), "model": model,
            "choices": [{"index":0,"message":{"role":"assistant","content":content},"finish_reason":"stop"}],
            "usage": {"prompt_tokens": len(content)//4, "completion_tokens": len(content)//4, "total_tokens": len(content)//2}}

async def stream_it(content, model, rid):
    for i, word in enumerate(content.split(" ")):
        yield f"data: {json.dumps({'id':rid,'object':'chat.completion.chunk','created':int(time.time()),'model':model,'choices':[{'index':0,'delta':{'content':word+(' ' if i<len(content.split())-1 else '')},'finish_reason':None}]})}\n\n"
        await asyncio.sleep(0.005)
    yield f"data: {json.dumps({'id':rid,'object':'chat.completion.chunk','created':int(time.time()),'model':model,'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]})}\n\ndata: [DONE]\n\n"

@app.get("/")
async def root(): return {"name":"Echo Proxima Native v4","available":available(),"proxima_upstream":PROXIMA_UPSTREAM}

@app.get("/v1/models")
async def models():
    avail = available()
    return {"object":"list","data":[{"id":p,"object":"model","created":1700000000,"owned_by":"echo","ready":p in avail} for p in list(PROVIDERS)+["auto"]]}

@app.post("/v1/chat/completions")
async def chat(req: ChatRequest):
    parts = []
    for m in req.messages:
        if m.role == "system": parts.append(f"[System: {m.content}]")
        elif m.role == "user": parts.append(m.content)
        elif m.role == "assistant": parts.append(f"[Previous: {m.content}]")
    prompt = "\n".join(parts).strip()
    if not prompt: raise HTTPException(400, "No prompt")
    provider = pick(req.model, prompt)
    log.info(f"→ {provider} | {prompt[:60]}...")
    text = await PROVIDERS[provider](prompt)
    rid = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    if req.stream:
        return StreamingResponse(stream_it(text, provider, rid), media_type="text/event-stream")
    return JSONResponse(mkresponse(text, provider, rid))

@app.post("/v1/completions")
async def completions(request: Request):
    body = await request.json()
    return await chat(ChatRequest(
        model=body.get("model","auto"),
        messages=[ChatMessage(role="user", content=body.get("prompt",""))],
        stream=body.get("stream",False)))

@app.get("/status")
async def status():
    avail = available()
    return {p: {"ready": p in avail, "has_cookies": has_cookies(p),
                "note": "forwarded to Proxima:3210" if p=="chatgpt" else None}
            for p in PROVIDERS}

@app.post("/reload_cookies/{provider}")
async def reload(provider: str):
    if provider not in PROVIDERS: raise HTTPException(404)
    if provider == "claude": _claude.reset()
    elif provider == "gemini": _gemini.reset()
    elif provider == "perplexity": _perplexity.reset()
    return {"provider": provider, "has_cookies": has_cookies(provider), "ready": has_cookies(provider)}

@app.post("/new_conversation/{provider}")
async def new_conv(provider: str):
    """Reset conversation context for a provider."""
    if provider == "claude": _claude.reset()
    elif provider == "gemini": _gemini.reset()
    elif provider == "perplexity": _perplexity.reset()
    return {"provider": provider, "conversation": "reset"}

@app.on_event("startup")
async def startup():
    log.info(f"Echo Proxima Native v4 | port={PORT}")
    log.info(f"Available: {available()}")
    log.info(f"ChatGPT forwarded to Proxima at {PROXIMA_UPSTREAM}")
    for p in ["claude","gemini","perplexity","grok"]:
        c = load_cookies(p)
        status = f"{len(c)} cookies ✓" if c else "no cookies ✗"
        log.info(f"  {p:<12}: {status}")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument("--host", default=HOST)
    p.add_argument("--headless", action="store_true")
    p.add_argument("--login", nargs="+")
    args = p.parse_args()
    if args.login:
        print(f"v4 uses direct API — export cookies from Firefox instead")
        print(f"Run: python3 extract_firefox_cookies.py")
        sys.exit(0)
    print(f"\nEcho Proxima Native v4")
    print(f"Available: {available()}")
    print(f"http://{args.host}:{args.port}\n")
    uvicorn.run("echo_proxima_native:app", host=args.host, port=args.port,
                reload=False, log_level=LOG_LEVEL.lower())
