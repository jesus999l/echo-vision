#!/usr/bin/env python3
"""
apply_memory.py — Wire EchoMemory into Echo
Run once from ~/vision_assistant/:

    python apply_memory.py

Changes:
  ai.py   — add _echo_memory singleton + set_echo_memory()
           — _vault_context_block() uses semantic search when memory is ready,
             falls back to keyword pool otherwise
  main.py — init EchoMemory in VisionApp.__init__
           — chain handle_note_ingested with existing ObsidianBridge callback
"""

import os, shutil, time

VA    = os.path.expanduser("~/vision_assistant")
stamp = time.strftime("%Y%m%d_%H%M%S")

for f in ("ai.py", "main.py"):
    src = os.path.join(VA, f)
    if os.path.exists(src):
        shutil.copy2(src, f"{src}.pre_memory_{stamp}")
        print(f"[backup] {f}.pre_memory_{stamp}")


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


# ── ai.py PATCH 1: add _echo_memory singleton ────────────────────────────────
patch("ai.py",
"_obsidian_bridge = None   # ObsidianBridge instance",
"""_obsidian_bridge = None   # ObsidianBridge instance
_echo_memory     = None   # EchoMemory instance (semantic search)

def set_echo_memory(memory):
    global _echo_memory
    _echo_memory = memory""",
"ai.py: add _echo_memory singleton + setter")


# ── ai.py PATCH 2: upgrade _vault_context_block() ────────────────────────────
patch("ai.py",
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
""",
"""def _vault_context_block() -> str:
    \"\"\"
    Return Obsidian vault context string for prompt injection.
    Uses semantic search (EchoMemory/ChromaDB) when available,
    falls back to ObsidianBridge keyword matching otherwise.
    \"\"\"
    # Try semantic search first
    if _echo_memory is not None and _echo_memory._ready:
        try:
            recent = get_recent_messages(limit=1)
            query  = recent[-1]["content"] if recent else ""
            ctx    = _echo_memory.context_for(query, k=5, max_chars=1500)
            if ctx:
                return f"\\n\\nSEMANTIC MEMORY:\\n{ctx}"
        except Exception as e:
            pass   # fall through to keyword fallback

    # Keyword fallback (ObsidianBridge context pool)
    if _obsidian_bridge is not None:
        try:
            recent = get_recent_messages(limit=1)
            query  = recent[-1]["content"] if recent else ""
            ctx    = _obsidian_bridge.get_context_for_query(query, max_chars=1200)
            if ctx:
                return f"\\n\\nOBSIDIAN VAULT CONTEXT:\\n{ctx}"
        except Exception:
            pass
    return ""
""",
"ai.py: upgrade _vault_context_block() to semantic search with keyword fallback")


# ── main.py PATCH 3: init EchoMemory in VisionApp.__init__ ───────────────────
patch("main.py",
"        # ── Jules pipeline ───────────────────────────────────────────────────",
"""        # ── Semantic memory (ChromaDB) ───────────────────────────────────────
        try:
            from echo_memory import EchoMemory
            self.echo_memory = EchoMemory(
                config_path = os.path.join(VA_DIR, "obsidian_config.json")
            )
            self.echo_memory.start()

            import ai as _ai
            _ai.set_echo_memory(self.echo_memory)

            # Chain with ObsidianBridge callback so new vault saves are indexed
            if self.obsidian is not None:
                _orig_cb = self.obsidian.on_note_ingested
                def _chained(note):
                    if _orig_cb and note:
                        _orig_cb(note)
                    self.echo_memory.handle_note_ingested(note)
                self.obsidian.on_note_ingested = _chained

            print("[main] EchoMemory started — semantic search active.")
        except Exception as e:
            self.echo_memory = None
            print(f"[main] EchoMemory failed: {e}")

        # ── Jules pipeline ───────────────────────────────────────────────────""",
"main.py: init EchoMemory + chain ObsidianBridge callback")


# ── main.py PATCH 4: stop memory on shutdown ─────────────────────────────────
patch("main.py",
"""    def _on_closing(self):
        \"\"\"Graceful shutdown — stop background threads before destroying root.\"\"\"
        try:
            if self.obsidian:
                self.obsidian.stop()
            if self.jules:
                self.jules.stop()
        except Exception:
            pass
        self.root.destroy()""",
"""    def _on_closing(self):
        \"\"\"Graceful shutdown — stop background threads before destroying root.\"\"\"
        try:
            if self.obsidian:
                self.obsidian.stop()
            if self.jules:
                self.jules.stop()
            if getattr(self, "echo_memory", None):
                self.echo_memory.stop()
        except Exception:
            pass
        self.root.destroy()""",
"main.py: stop EchoMemory on closing")


print("""
Done. Test:

    cd ~/vision_assistant
    source ~/vision_env/bin/activate

    # 1. Smoke test memory standalone:
    python echo_memory.py

    # 2. Start Echo — watch for:
    #    [main] EchoMemory started — semantic search active.
    python main.py --no-briefing

Background ingestion starts immediately on launch.
Vault notes get indexed over ~5-15 min depending on vault size.
Status check while Echo is running:
    from echo_memory import EchoMemory   # in Python shell
    # Or check ~/vision_assistant/chroma_db/ folder size — grows as notes index.
""")
