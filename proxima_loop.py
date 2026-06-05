"""
proxima_loop.py — Echo's Multi-AI Planning Engine
ChatGPT + Gemini debate → Perplexity fact-checks → Claude synthesizes final plan
Saves to Obsidian, exposes HTTP bridge for Echo desktop app.

Usage:
  Interactive REPL:   python3 proxima_loop.py
  One-shot:           python3 proxima_loop.py "your topic here"
  Echo bridge server: python3 proxima_loop.py --server
"""

import sys
import os
import json
import time
import signal
import hashlib
import argparse
import requests
import threading
from datetime import datetime
from pathlib import Path

# ─── CONFIG ──────────────────────────────────────────────────────────────────

PROXIMA_URL = "http://localhost:3210"       # update if port shifts again
OBSIDIAN_VAULT = Path("/home/jesus999l/Documents/ObsidianVault")
PLANS_DIR     = OBSIDIAN_VAULT / "Echo/Plans"
INDEX_FILE    = PLANS_DIR / "INDEX.md"
ECHO_BRIDGE_PORT = 7799                       # Echo desktop app calls this
DEBATE_TURNS  = 2
MAX_CHARS     = 3000
TIMEOUT       = 240

# Provider pool — order = priority. Failed providers are skipped automatically.
PROVIDER_POOL = {
    "debate":      ["chatgpt", "gemini"],     # alternating debaters
    "factcheck":   ["perplexity"],            # real-world verification
    "synthesizer": ["claude"],                # final planner
}

# Strings that indicate a provider is out of tokens / rate-limited
QUOTA_SIGNALS = [
    "rate limit", "quota", "too many requests", "out of tokens",
    "limit exceeded", "try again later", "context length",
    "maximum context", "error", "[no response]"
]

# ─── STATE ───────────────────────────────────────────────────────────────────

_provider_status = {p: "ok" for p in ["chatgpt", "gemini", "perplexity", "claude"]}
_partial_log = []           # saved on Ctrl+C
_interrupted = False

def _handle_interrupt(sig, frame):
    global _interrupted
    _interrupted = True
    print("\n\n[INTERRUPTED] Saving partial results...", flush=True)

signal.signal(signal.SIGINT, _handle_interrupt)

# ─── CORE: ASK WITH FALLBACK ─────────────────────────────────────────────────

def ask(provider: str, prompt: str, role: str = "") -> str:
    """
    Send prompt to provider via Proxima REST.
    If provider is unavailable, tries next available provider in pool.
    Returns [PROVIDER_DOWN] string if all fallbacks exhausted.
    """
    if _provider_status.get(provider) == "down":
        fallback = _find_fallback(provider)
        if fallback:
            print(f"  [!] {provider} down, falling back to {fallback}", flush=True)
            return ask(fallback, prompt, role)
        return f"[PROVIDER_DOWN: {provider}]"

    try:
        r = requests.post(
            f"{PROXIMA_URL}/v1/chat/completions",
            json={"model": provider, "messages": [{"role": "user", "content": prompt}]},
            timeout=TIMEOUT
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]

        # Detect quota/token exhaustion
        if any(sig in text.lower() for sig in QUOTA_SIGNALS) and len(text) < 300:
            print(f"  [!] {provider} appears rate-limited: {text[:100]}", flush=True)
            _provider_status[provider] = "down"
            fallback = _find_fallback(provider)
            if fallback:
                print(f"  [!] Retrying with {fallback}", flush=True)
                return ask(fallback, prompt, role)
            return f"[QUOTA_EXCEEDED: {provider}]"

        return text

    except requests.exceptions.Timeout:
        print(f"  [!] {provider} timed out after {TIMEOUT}s", flush=True)
        _provider_status[provider] = "down"
        fallback = _find_fallback(provider)
        if fallback:
            return ask(fallback, prompt, role)
        return f"[TIMEOUT: {provider}]"

    except requests.exceptions.ConnectionError:
        print(f"  [!] Proxima unreachable at {PROXIMA_URL} — check port", flush=True)
        return "[PROXIMA_OFFLINE]"

    except Exception as e:
        print(f"  [!] {provider} error: {e}", flush=True)
        _provider_status[provider] = "down"
        fallback = _find_fallback(provider)
        if fallback:
            return ask(fallback, prompt, role)
        return f"[ERROR: {provider}: {e}]"


def _find_fallback(failed_provider: str) -> str | None:
    """Find next available provider from the same role pool."""
    all_debate = PROVIDER_POOL["debate"]
    all_fact   = PROVIDER_POOL["factcheck"]
    all_synth  = PROVIDER_POOL["synthesizer"]

    if failed_provider in all_debate:
        pool = all_debate
    elif failed_provider in all_fact:
        pool = all_fact
    elif failed_provider in all_synth:
        pool = all_synth
    else:
        pool = list(_provider_status.keys())

    for p in pool:
        if p != failed_provider and _provider_status.get(p) == "ok":
            return p
    return None


def trim(text: str) -> str:
    if len(text) > MAX_CHARS:
        return text[:MAX_CHARS] + "\n...[truncated for relay]"
    return text


# ─── MAIN LOOP ───────────────────────────────────────────────────────────────

def run_loop(topic: str) -> str:
    global _partial_log, _interrupted
    _partial_log = []
    _interrupted = False

    # Reset provider statuses for each new topic
    for p in _provider_status:
        _provider_status[p] = "ok"

    print(f"\n{'='*60}")
    print(f"TOPIC: {topic}")
    print(f"{'='*60}")
    print_status()

    # ── Round 0: ChatGPT drafts ──────────────────────────────────
    response = ask("chatgpt", f"Draft a detailed solution for: {topic}\n\nBe specific and technical.")
    print(f"\n[ChatGPT Draft]\n{response[:400]}...\n{'-'*50}")
    _partial_log.append({"model": "chatgpt", "turn": 0, "content": response})
    if _interrupted:
        return _save_partial(topic)

    # ── Rounds 1+: Gemini ↔ ChatGPT debate ──────────────────────
    debaters = [p for p in PROVIDER_POOL["debate"] if _provider_status[p] == "ok"]

    for turn in range(DEBATE_TURNS):
        if _interrupted:
            return _save_partial(topic)

        # Gemini critiques
        critic = debaters[1] if len(debaters) > 1 else debaters[0]
        response = ask(critic,
            f"Critique this plan concisely. Identify bugs, edge cases, and improvements:\n\n{trim(response)}")
        print(f"\n[{critic.upper()} critique turn {turn+1}]\n{response[:400]}...\n{'-'*50}")
        _partial_log.append({"model": critic, "turn": turn+1, "content": response})

        if _interrupted:
            return _save_partial(topic)

        # ChatGPT refines
        drafter = debaters[0]
        response = ask(drafter,
            f"Refine and improve based on this critique. Be concise:\n\n{trim(response)}")
        print(f"\n[{drafter.upper()} refinement turn {turn+1}]\n{response[:400]}...\n{'-'*50}")
        _partial_log.append({"model": drafter, "turn": turn+1, "content": response})

    # ── Perplexity fact-check ────────────────────────────────────
    if _provider_status.get("perplexity") == "ok" and not _interrupted:
        fact_topic = topic[:200]
        perp = ask("perplexity",
            f"Verify against current docs: are there known issues or better practices for: {fact_topic}? Be concise.")
        print(f"\n[Perplexity fact-check]\n{perp[:400]}...\n{'-'*50}")
        _partial_log.append({"model": "perplexity", "turn": 99, "content": perp})
    else:
        perp = "[Perplexity unavailable]"

    if _interrupted:
        return _save_partial(topic)

    # ── Claude synthesizes ───────────────────────────────────────
    full_debate = "\n\n---\n\n".join(
        f"[{e['model'].upper()} Turn {e['turn']}]:\n{trim(e['content'])}"
        for e in _partial_log
    )

    claude_prompt = f"""You are Echo's chief architect. Review this debate and produce the final plan.

Topic: "{topic}"

Debate:
{full_debate}

Deliver:
1. Strongest ideas extracted from both models
2. Contradictions resolved (state which model was right and why)
3. Numbered implementation steps, concrete and specific
4. Mark [HUMAN DECISION NEEDED] where a design choice requires human input
5. Section: "What both models got wrong" — be honest if anything was bad
6. Section: "What to build first" — ordered by dependency

Be decisive. This is the authoritative output saved to Echo's knowledge base."""

    print("\n[Claude synthesizing final plan...]\n")
    final_plan = ask("claude", claude_prompt)
    print(f"\n[CLAUDE FINAL PLAN]\n{final_plan[:600]}...\n{'='*60}")
    _partial_log.append({"model": "claude", "turn": 999, "content": final_plan})

    # ── Save ─────────────────────────────────────────────────────
    path = save_to_obsidian(topic, _partial_log, final_plan, partial=False)
    update_index(topic, path, partial=False)
    return final_plan


# ─── OBSIDIAN ────────────────────────────────────────────────────────────────

def save_to_obsidian(topic: str, debate_log: list, final_plan: str, partial: bool = False) -> Path:
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    safe_topic = topic[:50].replace(" ", "-").replace("/", "-").replace(":", "")
    suffix = "_PARTIAL" if partial else ""
    filename = PLANS_DIR / f"{timestamp}_{safe_topic}{suffix}.md"

    provider_states = ", ".join(
        f"{p}={'✓' if s == 'ok' else '✗'}" for p, s in _provider_status.items()
    )

    note = f"""# {topic}
*Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}*
*Pipeline: ChatGPT → Gemini ×{DEBATE_TURNS} → Perplexity → Claude*
*Providers: {provider_states}*
{"*⚠️ PARTIAL — interrupted before Claude synthesis*" if partial else ""}

---

## Claude Final Plan

{final_plan if not partial else "_Plan not generated — loop was interrupted._"}

---

## Debate Log

"""
    for e in debate_log:
        label = e["model"].upper()
        turn  = e["turn"]
        content = e["content"]
        note += f"### [{label}] Turn {turn}\n\n{content}\n\n---\n\n"

    filename.write_text(note, encoding="utf-8")
    print(f"\n[Obsidian] Saved → {filename}")
    return filename


def update_index(topic: str, path: Path, partial: bool = False):
    """Append entry to INDEX.md in the Plans folder."""
    PLANS_DIR.mkdir(parents=True, exist_ok=True)

    if not INDEX_FILE.exists():
        INDEX_FILE.write_text(
            "# Echo Planning Index\n\nAll plans generated by the Proxima multi-AI pipeline.\n\n| Date | Topic | File | Status |\n|------|-------|------|--------|\n",
            encoding="utf-8"
        )

    date_str  = datetime.now().strftime("%Y-%m-%d %H:%M")
    rel_path  = path.name
    status    = "⚠️ Partial" if partial else "✅ Complete"
    short_topic = topic[:60] + ("..." if len(topic) > 60 else "")

    with open(INDEX_FILE, "a", encoding="utf-8") as f:
        f.write(f"| {date_str} | {short_topic} | [[{rel_path}]] | {status} |\n")

    print(f"[Obsidian] Index updated → {INDEX_FILE.name}")


def compress_old_plans(days_old: int = 30):
    """
    Compress plans older than N days into a monthly summary note.
    Run this manually or hook into Echo's maintenance daemon.
    """
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - (days_old * 86400)
    old_files = [
        f for f in PLANS_DIR.glob("*.md")
        if f.stat().st_mtime < cutoff
        and f.name != "INDEX.md"
        and "_ARCHIVE_" not in f.name
    ]

    if not old_files:
        print("[Compress] No files old enough to archive.")
        return

    month_groups: dict[str, list] = {}
    for f in old_files:
        month_key = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m")
        month_groups.setdefault(month_key, []).append(f)

    for month, files in month_groups.items():
        archive_name = PLANS_DIR / f"_ARCHIVE_{month}.md"
        content = f"# Echo Plans Archive — {month}\n\n*Auto-compressed {len(files)} plans*\n\n"

        for f in sorted(files):
            text = f.read_text(encoding="utf-8")
            # Extract just the Claude Final Plan section
            final_section = ""
            if "## Claude Final Plan" in text:
                parts = text.split("## Claude Final Plan")
                if len(parts) > 1:
                    final_section = parts[1].split("## Debate Log")[0].strip()

            content += f"## {f.stem}\n\n{final_section[:1500]}\n\n---\n\n"
            f.unlink()
            print(f"[Compress] Archived {f.name}")

        archive_name.write_text(content, encoding="utf-8")
        print(f"[Compress] Created {archive_name.name}")

    update_index(f"Monthly archive {month}", archive_name, partial=False)


def _save_partial(topic: str) -> str:
    if _partial_log:
        path = save_to_obsidian(topic, _partial_log, "", partial=True)
        update_index(topic, path, partial=True)
        return "[PARTIAL SAVE COMPLETE]"
    return "[NOTHING TO SAVE]"


# ─── ECHO DESKTOP BRIDGE ─────────────────────────────────────────────────────

def start_echo_bridge():
    """
    Lightweight HTTP server that lets Echo desktop app trigger the loop.

    In vision_assistant.py, add:
        import requests
        def run_proxima_plan(topic):
            r = requests.post("http://localhost:7799/plan", json={"topic": topic}, timeout=600)
            return r.json().get("plan", "")

    Then call it from an AI command handler or UI button.
    """
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class BridgeHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # silence default access log

        def do_POST(self):
            if self.path == "/plan":
                length = int(self.headers.get("Content-Length", 0))
                body   = json.loads(self.rfile.read(length))
                topic  = body.get("topic", "").strip()

                if not topic:
                    self._respond(400, {"error": "topic required"})
                    return

                print(f"\n[Bridge] Received topic from Echo: {topic}", flush=True)
                plan = run_loop(topic)
                self._respond(200, {"plan": plan, "status": "complete"})

            elif self.path == "/status":
                self._respond(200, {
                    "providers": _provider_status,
                    "proxima_url": PROXIMA_URL
                })

            elif self.path == "/compress":
                compress_old_plans(days_old=30)
                self._respond(200, {"status": "compressed"})

            else:
                self._respond(404, {"error": "unknown endpoint"})

        def _respond(self, code, data):
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", ECHO_BRIDGE_PORT), BridgeHandler)
    print(f"[Bridge] Echo bridge listening on http://localhost:{ECHO_BRIDGE_PORT}")
    print(f"[Bridge] Endpoints: POST /plan  GET /status  POST /compress")
    server.serve_forever()


# ─── STATUS DISPLAY ──────────────────────────────────────────────────────────

def print_status():
    icons = {"ok": "✓", "down": "✗"}
    states = "  ".join(
        f"{icons[s]} {p}" for p, s in _provider_status.items()
    )
    print(f"Providers: {states}")


# ─── REPL ────────────────────────────────────────────────────────────────────

def interactive_repl():
    global PROXIMA_URL
    print("\n╔══════════════════════════════════════╗")
    print("║  Echo Proxima Planning Engine        ║")
    print("║  ChatGPT → Gemini → Perplexity       ║")
    print("║  → Claude → Obsidian                 ║")
    print("╚══════════════════════════════════════╝")
    print("\nCommands:")
    print("  <topic>    — run planning loop")
    print("  status     — show provider health")
    print("  compress   — archive plans >30 days old")
    print("  port <N>   — switch Proxima port")
    print("  quit       — exit\n")

    while True:
        try:
            raw = input("echo-plan> ").strip()
        except EOFError:
            break

        if not raw:
            continue

        if raw == "quit":
            break
        elif raw == "status":
            print_status()
            print(f"Proxima: {PROXIMA_URL}")
            print(f"Vault:   {OBSIDIAN_VAULT}")
        elif raw == "compress":
            compress_old_plans(days_old=30)
        elif raw.startswith("port "):
            PROXIMA_URL = f"http://localhost:{raw.split()[1]}"
            print(f"Proxima URL → {PROXIMA_URL}")
        else:
            run_loop(raw)


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Echo Proxima Planning Engine")
    parser.add_argument("topic", nargs="?", help="Topic to plan (one-shot mode)")
    parser.add_argument("--server", action="store_true", help="Run Echo bridge server")
    parser.add_argument("--compress", action="store_true", help="Archive old Obsidian plans")
    parser.add_argument("--port", type=int, help="Override Proxima port")
    args = parser.parse_args()

    if args.port:
        PROXIMA_URL = f"http://localhost:{args.port}"

    if args.compress:
        compress_old_plans(days_old=30)
        sys.exit(0)

    if args.server:
        # Run bridge in background thread, REPL in foreground
        t = threading.Thread(target=start_echo_bridge, daemon=True)
        t.start()
        interactive_repl()
    elif args.topic:
        run_loop(args.topic)
    else:
        interactive_repl()
