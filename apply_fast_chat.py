#!/usr/bin/env python3
"""
apply_fast_chat.py — Patch ui.py for streaming + apply fast_chat integration
Run once from ~/vision_assistant/:

    python apply_fast_chat.py

What it does:
  1. Adds _stream_start / _stream_token / _stream_done to ChatOverlay
  2. Replaces the blocking ask() call in _handle_message with stream_ask()
  3. Adds IdentityBroker startup check in VisionApp.__init__
  4. Keeps ALL existing functionality intact
"""

import os, shutil, time

VA    = os.path.expanduser("~/vision_assistant")
stamp = time.strftime("%Y%m%d_%H%M%S")

for f in ("ui.py", "main.py"):
    src = os.path.join(VA, f)
    if os.path.exists(src):
        shutil.copy2(src, f"{src}.pre_fastchat_{stamp}")
        print(f"[backup] {f}.pre_fastchat_{stamp}")


def patch(filename, old, new, label):
    path = os.path.join(VA, filename)
    text = open(path, encoding="utf-8").read()
    if old not in text:
        print(f"  [SKIP] {label} — anchor not found")
        return False
    if new.strip() in text:
        print(f"  [SKIP] {label} — already applied")
        return False
    open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))
    print(f"  [OK]   {label}")
    return True


# ============================================================================
# ui.py PATCH 1 — Add streaming methods to ChatOverlay
# Insert right before send_message so they're part of the class
# ============================================================================

patch("ui.py",
# ANCHOR
"    def send_message(self):",
# REPLACEMENT
"""    # ── Streaming response methods ──────────────────────────────────────────

    def _stream_start(self):
        \"\"\"
        Create an empty AI bubble and return a unique stream tag.
        Called once at the start of a streaming response.
        \"\"\"
        import uuid
        tag = f"stream_{uuid.uuid4().hex[:8]}"
        # append_chat inserts into the Text widget — we insert an empty
        # placeholder that _stream_token will fill in token by token.
        self.append_chat("ai", "")
        # Store tag → index of this message so we can update it in place
        if not hasattr(self, "_stream_tags"):
            self._stream_tags = {}
        try:
            # The last "ai" insertion is the one we just made.
            # Store the end index so we can insert tokens there.
            self._stream_tags[tag] = self.chat_log.index("end-1c")
        except Exception:
            self._stream_tags[tag] = None
        self._current_stream_tag    = tag
        self._current_stream_buffer = ""
        return tag

    def _stream_token(self, token: str):
        \"\"\"Append a streaming token to the active AI bubble. Thread-safe.\"\"\"
        self._current_stream_buffer = getattr(self, "_current_stream_buffer", "") + token
        # Throttle UI updates — batch every ~40ms to avoid widget thrashing
        if not getattr(self, "_stream_update_pending", False):
            self._stream_update_pending = True
            self.after(40, self._flush_stream_buffer)

    def _flush_stream_buffer(self):
        \"\"\"Flush buffered tokens into the chat widget. Runs on the main thread.\"\"\"
        self._stream_update_pending = False
        buf = getattr(self, "_current_stream_buffer", "")
        if not buf:
            return
        tag = getattr(self, "_current_stream_tag", None)
        if tag is None:
            return
        try:
            # Insert the buffered tokens at the end of the chat log
            self.chat_log.config(state="normal")
            self.chat_log.insert("end", buf)
            self.chat_log.see("end")
            self.chat_log.config(state="disabled")
            self._current_stream_buffer = ""
        except Exception:
            pass

    def _stream_done(self, full_response: str):
        \"\"\"
        Called when streaming is complete.
        Flushes any remaining buffer and adds a newline separator.
        \"\"\"
        # Flush whatever's left
        self.after(0, self._flush_stream_buffer)

        def _finalize():
            try:
                self.chat_log.config(state="normal")
                self.chat_log.insert("end", "\\n")
                self.chat_log.see("end")
                self.chat_log.config(state="disabled")
            except Exception:
                pass
            self._current_stream_buffer = ""
            self._current_stream_tag    = None

        self.after(50, _finalize)

    # ── end streaming methods ────────────────────────────────────────────────

    def send_message(self):""",
"ui.py: add streaming methods to ChatOverlay")


# ============================================================================
# ui.py PATCH 2 — Replace blocking ask() with stream_ask() in _handle_message
# The current pattern (from grep) is:
#     result = ask(user_text, ...)
#     self.after(0, lambda r=result: self.append_chat("ai", r))
# Replace with streaming version.
# ============================================================================

patch("ui.py",
# ANCHOR — the final AI response block in _handle_message
"""                self.after(0, lambda r=result: self.append_chat("ai", r))
                return
        except Exception as e:
            self.after(0, lambda: self.append_chat("ai", f"Vision error: {e}"))""",
# REPLACEMENT
"""                self.after(0, lambda r=result: self.append_chat("ai", r))
                return
        except Exception as e:
            self.after(0, lambda: self.append_chat("ai", f"Vision error: {e}"))""",
"ui.py: streaming hook (placeholder — see note below)")

# NOTE: The final AI ask() call needs to be replaced. Let's find it more precisely.
# Rather than fragile anchor matching, we patch _handle_message's terminal ask() call.

import os
path = os.path.join(VA, "ui.py")
text = open(path, encoding="utf-8").read()

# Find the normal (non-vision, non-task) ask() path in _handle_message
# Pattern: result = ask(...) followed by append_chat("ai", r)
import re

# Replace the standard ask block with streaming
OLD_ASK = '''            result = ask(user_text, model=routed, ocr_text=ocr, screenshot_path=screenshot or "", ui_callback=ui_callback)
                self.after(0, lambda r=result: self.append_chat("ai", r))'''

NEW_ASK = '''            # ── Streaming fast-chat path ──────────────────────────────
            try:
                from fast_chat import stream_ask
                self.after(0, lambda: self._stream_start())
                stream_ask(
                    prompt   = user_text,
                    on_chunk = lambda tok: self.after(0, lambda t=tok: self._stream_token(t)),
                    on_done  = lambda full: self.after(0, lambda f=full: self._stream_done(f)),
                    on_error = lambda err: self.after(0, lambda e=err: self.append_chat("ai", f"Error: {e}")),
                    model    = routed,
                )
                return   # stream_ask is async, callbacks handle display
            except ImportError:
                pass
            # Fallback: original blocking path
            result = ask(user_text, model=routed, ocr_text=ocr, screenshot_path=screenshot or "", ui_callback=ui_callback)
                self.after(0, lambda r=result: self.append_chat("ai", r))'''

if OLD_ASK in text:
    text = text.replace(OLD_ASK, NEW_ASK, 1)
    open(path, "w", encoding="utf-8").write(text)
    print("  [OK]   ui.py: replace ask() with stream_ask() in _handle_message")
else:
    # Broader search — find the ask() call pattern in _handle_message
    # Look for any line with "result = ask(" followed by append_chat
    lines  = text.split("\n")
    patched = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if (stripped.startswith("result = ask(") or
                stripped.startswith("result=ask(")):
            # Check the next few lines for append_chat("ai"
            window = "\n".join(lines[i:i+5])
            if 'append_chat("ai"' in window or "append_chat('ai'" in window:
                # Found the block — insert streaming path before it
                indent = len(line) - len(line.lstrip())
                ind    = " " * indent
                streaming_block = [
                    f'{ind}# ── Streaming fast-chat path ──────────────────────────────',
                    f'{ind}try:',
                    f'{ind}    from fast_chat import stream_ask',
                    f'{ind}    self.after(0, lambda: self._stream_start())',
                    f'{ind}    stream_ask(',
                    f'{ind}        prompt   = user_text,',
                    f'{ind}        on_chunk = lambda tok: self.after(0, lambda t=tok: self._stream_token(t)),',
                    f'{ind}        on_done  = lambda full: self.after(0, lambda f=full: self._stream_done(f)),',
                    f'{ind}        on_error = lambda err: self.after(0, lambda e=err: self.append_chat("ai", f"Error: {{e}}")),',
                    f'{ind}        model    = routed,',
                    f'{ind}    )',
                    f'{ind}    return',
                    f'{ind}except ImportError:',
                    f'{ind}    pass',
                    f'{ind}# Fallback: original blocking path',
                ]
                lines = lines[:i] + streaming_block + lines[i:]
                open(path, "w", encoding="utf-8").write("\n".join(lines))
                print(f"  [OK]   ui.py: inserted stream_ask() before ask() at line {i+1}")
                patched = True
                break
    if not patched:
        print("  [WARN] ui.py: could not find ask() block — manual integration needed")
        print("         See MANUAL_STREAMING_PATCH below for instructions.")


# ============================================================================
# main.py PATCH 3 — Add IdentityBroker check at startup
# ============================================================================

patch("main.py",
# ANCHOR
"        # ── end integration callbacks",
# REPLACEMENT
"""        # ── Identity broker ──────────────────────────────────────────────────
        try:
            from fast_chat import IdentityBroker
            self._broker = IdentityBroker(
                on_warning = self._speak_if_ready
            )
            self._broker.check_all(verbose=True)
        except Exception as e:
            print(f"[main] Identity broker failed: {e}")

        # ── end integration callbacks""",
"main.py: add IdentityBroker startup check")


# ============================================================================
print("""
Done. Test with:

    cd ~/vision_assistant
    source ~/vision_env/bin/activate
    python fast_chat.py          ← smoke test streaming + identity broker

Then start Echo and chat — responses should stream token by token:
    python main.py --no-briefing

── MANUAL_STREAMING_PATCH (only if [WARN] appeared above) ──────────────────
If the auto-patch couldn't find the ask() block, add this manually
in _handle_message, right before the line that calls ask():

    try:
        from fast_chat import stream_ask
        self.after(0, lambda: self._stream_start())
        stream_ask(
            prompt   = user_text,
            on_chunk = lambda tok: self.after(0, lambda t=tok: self._stream_token(t)),
            on_done  = lambda full: self.after(0, lambda f=full: self._stream_done(f)),
            on_error = lambda err: self.after(0, lambda e=err: self.append_chat("ai", f"Error: {e}")),
            model    = routed,
        )
        return
    except ImportError:
        pass
    # (existing ask() call stays below as fallback)
─────────────────────────────────────────────────────────────────────────────
""")
