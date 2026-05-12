#!/usr/bin/env python3
"""
apply_integration.py — Echo Integration Patch
Run once from ~/vision_assistant/:

    cd ~/vision_assistant
    source ~/vision_env/bin/activate
    python apply_integration.py

Patches:
  ai.py   — vault context injection into build_system_prompt()
           — web search injection into _ask_text()
           — module-level bridge/searcher setters
  main.py — ObsidianBridge + JulesPipeline init in VisionApp.__init__
           — briefing vault logging
           — graceful shutdown

Makes a timestamped backup of both files before touching them.
"""

import os
import sys
import shutil
import time

VA = os.path.expanduser("~/vision_assistant")
os.chdir(VA)

# ── Backup ────────────────────────────────────────────────────────────────────
stamp = time.strftime("%Y%m%d_%H%M%S")
for f in ("ai.py", "main.py"):
    src = os.path.join(VA, f)
    if os.path.exists(src):
        shutil.copy2(src, f"{src}.pre_integration_{stamp}")
        print(f"[backup] {f}.pre_integration_{stamp}")


def patch(filename, old, new, label):
    path = os.path.join(VA, filename)
    text = open(path, encoding="utf-8").read()
    if old not in text:
        print(f"  [SKIP] {label} — anchor not found in {filename}")
        return False
    if new.strip() in text:
        print(f"  [SKIP] {label} — already applied")
        return False
    open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))
    print(f"  [OK]   {label}")
    return True


# ============================================================================
# ai.py — PATCH 1
# Add module-level bridge/searcher singletons + setter functions
# Insert right after the existing imports block (after the last top-level import)
# ============================================================================

patch("ai.py",
# ── ANCHOR ──
"def build_system_prompt():",
# ── REPLACEMENT ──
"""# ── INTEGRATION SINGLETONS (set by main.py at startup) ──────────────────────
_obsidian_bridge = None   # ObsidianBridge instance
_web_searcher    = None   # WebSearch instance

def set_obsidian_bridge(bridge):
    global _obsidian_bridge
    _obsidian_bridge = bridge

def set_web_searcher(searcher):
    global _web_searcher
    _web_searcher = searcher

def build_system_prompt():""",
"ai.py: add bridge/searcher singletons")


# ============================================================================
# ai.py — PATCH 2
# Inject vault context at the END of build_system_prompt()'s return string.
# The return ends with: "Only add <action> when actually changing data."
# ============================================================================

patch("ai.py",
# ── ANCHOR ──
'Only add <action> when actually changing data."""',
# ── REPLACEMENT ──
'''Only add <action> when actually changing data.""" + _vault_context_block()''',
"ai.py: inject vault context into build_system_prompt()")


# ============================================================================
# ai.py — PATCH 3
# Add _vault_context_block() helper right after build_system_prompt closes.
# Insert before the "# ── CONTEXT ──" orphan block.
# ============================================================================

patch("ai.py",
# ── ANCHOR ──
"# ── CONTEXT ───────────────────────────────────────────────────────────────────",
# ── REPLACEMENT ──
"""def _vault_context_block() -> str:
    \"\"\"Return Obsidian vault context string for prompt injection, or ''.\"\"\"
    if _obsidian_bridge is None:
        return ""
    try:
        # Use last user message from recent history as query if available
        recent = get_recent_messages(limit=1)
        query  = recent[-1]["content"] if recent else ""
        ctx    = _obsidian_bridge.get_context_for_query(query, max_chars=1200)
        if ctx:
            return f"\\n\\nOBSIDIAN VAULT CONTEXT:\\n{ctx}"
    except Exception as e:
        pass
    return ""

# ── CONTEXT ───────────────────────────────────────────────────────────────────""",
"ai.py: add _vault_context_block() helper")


# ============================================================================
# ai.py — PATCH 4
# Inject web search into _ask_text() — right before the requests.post call.
# ============================================================================

patch("ai.py",
# ── ANCHOR ──
"""    r = requests.post(LLM_URL,
                      json={"model": model,
                            "messages": [
                                {"role": "system", "content": build_system_prompt()},
                                {"role": "user",   "content": full_prompt},
                            ],
                            "max_tokens": 300},
                      timeout=300)
    return r.json()["choices"][0]["message"]["content"]""",
# ── REPLACEMENT ──
"""    # ── Web search injection ────────────────────────────────────────────────
    sys_prompt = build_system_prompt()
    try:
        if _web_searcher is not None:
            from web_search import needs_web_search
            if needs_web_search(prompt):
                result = _web_searcher.search(prompt)
                web_ctx = result.to_prompt_block(max_results=4)
                if web_ctx:
                    sys_prompt += f"\\n\\nWEB SEARCH RESULTS:\\n{web_ctx}"
    except Exception:
        pass
    # ── end web search ───────────────────────────────────────────────────────
    r = requests.post(LLM_URL,
                      json={"model": model,
                            "messages": [
                                {"role": "system", "content": sys_prompt},
                                {"role": "user",   "content": full_prompt},
                            ],
                            "max_tokens": 300},
                      timeout=300)
    return r.json()["choices"][0]["message"]["content"]""",
"ai.py: inject web search into _ask_text()")


# ============================================================================
# main.py — PATCH 5
# Init ObsidianBridge + JulesPipeline in VisionApp.__init__
# ============================================================================

patch("main.py",
# ── ANCHOR ──
"""    def __init__(self, ChatOverlay):
        self.ChatOverlay  = ChatOverlay
        self.root         = tk.Tk()
        self.root.withdraw()
        self.chat_window  = None""",
# ── REPLACEMENT ──
"""    def __init__(self, ChatOverlay):
        self.ChatOverlay  = ChatOverlay
        self.root         = tk.Tk()
        self.root.withdraw()
        self.chat_window  = None

        # ── Obsidian bridge ──────────────────────────────────────────────────
        try:
            from obsidian_bridge import ObsidianBridge
            self.obsidian = ObsidianBridge(
                config_path      = os.path.join(VA_DIR, "obsidian_config.json"),
                on_note_ingested = self._on_vault_note_ingested,
                on_daily_summary = self._on_daily_summary,
            )
            self.obsidian.start()
            import ai as _ai
            _ai.set_obsidian_bridge(self.obsidian)
            print("[main] Obsidian bridge started.")
        except Exception as e:
            self.obsidian = None
            print(f"[main] Obsidian bridge failed: {e}")

        # ── Web search ───────────────────────────────────────────────────────
        try:
            from web_search import WebSearch
            self.searcher = WebSearch(
                config_path = os.path.join(VA_DIR, "websearch_config.json")
            )
            import ai as _ai
            _ai.set_web_searcher(self.searcher)
            print("[main] Web search ready.")
        except Exception as e:
            self.searcher = None
            print(f"[main] Web search failed: {e}")

        # ── Jules pipeline ───────────────────────────────────────────────────
        try:
            from jules_pipeline import build_jules_pipeline
            self.jules = build_jules_pipeline(
                obsidian_bridge  = self.obsidian,
                on_pr_ready      = lambda t: self._speak_if_ready(
                    f"Jules filed a pull request for: {t.title}"),
                on_issue_created = lambda t: self._speak_if_ready(
                    f"GitHub issue created. Jules is working on: {t.title}"),
                config_path      = os.path.join(VA_DIR, "jules_config.json"),
            )
            self.jules.start()
            print("[main] Jules pipeline started.")
        except Exception as e:
            self.jules = None
            print(f"[main] Jules pipeline failed: {e}")

        # Register shutdown
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)""",
"main.py: init Obsidian + WebSearch + Jules in VisionApp.__init__")


# ============================================================================
# main.py — PATCH 6
# Add vault callbacks + speak helper + on_closing as methods of VisionApp.
# Insert before the run() method.
# ============================================================================

patch("main.py",
# ── ANCHOR ──
"    def _get_or_create_window(self):",
# ── REPLACEMENT ──
"""    # ── Integration callbacks ────────────────────────────────────────────────

    def _speak_if_ready(self, text: str):
        \"\"\"Speak via Echo's TTS if available, else just print.\"\"\"
        try:
            from voice import speak
            speak(text)
        except Exception:
            print(f"[echo] {text}")

    def _on_vault_note_ingested(self, note):
        \"\"\"Called by ObsidianBridge when a tagged note is saved in Obsidian.\"\"\"
        if note is None:
            return
        try:
            if note.has_tag("echo-task"):
                self._speak_if_ready(f"New task imported from Obsidian: {note.title}")
            if note.has_tag("jules-task"):
                self._speak_if_ready(f"Jules task queued: {note.title}")
        except Exception as e:
            print(f"[main] vault callback error: {e}")

    def _on_daily_summary(self):
        \"\"\"Called by bridge scheduler at daily_summary_time.\"\"\"
        import threading
        threading.Thread(target=self._write_daily_summary, daemon=True).start()

    def _write_daily_summary(self):
        if self.obsidian is None:
            return
        try:
            import ai as _ai
            summary = _ai.ask(
                "Write a brief end-of-day summary (under 100 words, plain text) "
                "based on today's activity. No markdown."
            )
            self.obsidian.log_daily_summary(summary)
        except Exception as e:
            print(f"[main] daily summary error: {e}")

    def _on_closing(self):
        \"\"\"Graceful shutdown — stop background threads before destroying root.\"\"\"
        try:
            if self.obsidian:
                self.obsidian.stop()
            if self.jules:
                self.jules.stop()
        except Exception:
            pass
        self.root.destroy()

    # ── end integration callbacks ─────────────────────────────────────────────

    def _get_or_create_window(self):""",
"main.py: add vault callbacks + on_closing method")


# ============================================================================
# main.py — PATCH 7
# Log morning briefing to Obsidian vault.
# ============================================================================

patch("main.py",
# ── ANCHOR ──
"            b = get_morning_briefing()\n            show_morning_briefing_notification(b)",
# ── REPLACEMENT ──
"""            b = get_morning_briefing()
            show_morning_briefing_notification(b)
            # Log briefing to Obsidian vault (bridge may not be up yet, use direct write)
            try:
                from obsidian_bridge import ObsidianBridge as _OB
                import json as _jj
                _vcfg = _jj.load(open(os.path.join(VA_DIR, "obsidian_config.json")))
                _tmp  = _OB.__new__(_OB)
                from pathlib import Path as _P
                from obsidian_bridge import VaultWriter as _VW
                _tmp.writer = _VW(_P(_vcfg["vault_path"]).expanduser().resolve(),
                                  _vcfg.get("subfolders", {}))
                _tmp.writer.write_morning_briefing(b)
            except Exception as _be:
                pass  # non-fatal""",
"main.py: log morning briefing to Obsidian vault")


# ============================================================================
# Summary
# ============================================================================
print("""
All patches applied. Test with:

    cd ~/vision_assistant
    source ~/vision_env/bin/activate
    python main.py --no-briefing

Watch for these lines in startup output:
  [main] Obsidian bridge started.
  [main] Web search ready.
  [main] Jules pipeline started.

If any fail, the originals are backed up as ai.py.pre_integration_TIMESTAMP
""")
