"""
echo_ai_toggle_fix.py
=====================
Diagnoses the AI toggle filter bug and patches ui.py + ai.py.

Run:  python3 echo_ai_toggle_fix.py scan     → show where the bug is
Run:  python3 echo_ai_toggle_fix.py patch    → apply the fix with permission gate

The bug: ui.py._toggle_ai() updates self._active_providers (or similar)
but never pushes that list to ai.py. So ask() always uses the full chain.

The fix: one line in _toggle_ai() that calls self.ai.set_enabled([...])
plus set_enabled() + _filtered_chain() methods added to EchoAI in ai.py.
"""

import re
import sys
import shutil
from pathlib import Path
from datetime import datetime

VA = Path.home() / "vision_assistant"
AI_PY = VA / "ai.py"
UI_PY = VA / "ui.py"

# ── Colors ────────────────────────────────────────────────────────────────────
R = "\033[0m"; B = "\033[1m"; G = "\033[92m"; Y = "\033[93m"
C = "\033[96m"; X = "\033[90m"; E = "\033[91m"

def ok(t):   print(f"  {G}✓{R} {t}")
def warn(t): print(f"  {Y}⚠{R} {t}")
def err(t):  print(f"  {E}✗{R} {t}")
def info(t): print(f"  {X}→{R} {t}")

# ── Scanner ───────────────────────────────────────────────────────────────────

def cmd_scan():
    print(f"\n{B}{C}AI Toggle Flow Tracer{R}\n")

    for path, label in [(AI_PY, "ai.py"), (UI_PY, "ui.py")]:
        if not path.exists():
            err(f"{label} not found at {path}")
            continue

        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()
        print(f"{B}{label}{R}  ({len(lines)} lines)")

        # Check for key patterns
        checks = {
            "ai.py": [
                ("set_enabled",      "set_enabled() method",         True),
                ("_filtered_chain",  "_filtered_chain() method",     True),
                ("enabled_ais",      "enabled_ais attribute used",   True),
                ("PROVIDER_CHAIN",   "PROVIDER_CHAIN defined",       True),
                ("async def ask",    "ask() is async",               False),
            ],
            "ui.py": [
                ("_toggle_ai",       "_toggle_ai() method",          True),
                ("set_enabled",      "pushes to ai.set_enabled()",   True),
                ("_active_providers","_active_providers list",       False),
                ("enabled_ais",      "enabled_ais referenced",       False),
            ],
        }

        for pattern, description, needed in checks[label]:
            found = pattern in content
            if found and needed:
                ok(f"{description}")
            elif not found and needed:
                warn(f"MISSING: {description}  ← needs to be added")
            elif found and not needed:
                info(f"{description}  (informational)")
            else:
                info(f"not found: {description}")

        # Find _toggle_ai body and check if it calls set_enabled
        if label == "ui.py" and "_toggle_ai" in content:
            # Find the method
            toggle_match = re.search(r"def _toggle_ai\(.*?\)(.*?)(?=\n    def |\nclass |\Z)",
                                     content, re.DOTALL)
            if toggle_match:
                body = toggle_match.group(1)
                if "set_enabled" in body:
                    ok("_toggle_ai() calls set_enabled() ✓")
                else:
                    warn("_toggle_ai() does NOT call set_enabled() ← THIS IS THE BUG")
                    # Show the current body
                    print(f"\n  Current _toggle_ai body:")
                    for line in body.splitlines()[:15]:
                        print(f"  {X}{line}{R}")
                    print()

        print()

    print(f"Run: python3 {Path(__file__).name} patch   → apply the fix")


# ── Patcher ───────────────────────────────────────────────────────────────────

AI_SET_ENABLED = '''
    def set_enabled(self, providers: list):
        """Called by UI AI toggles. Controls which providers participate in pipeline."""
        all_providers = list(self.PROVIDER_CHAIN) if hasattr(self, "PROVIDER_CHAIN") else []
        self.enabled_ais = [p for p in providers if not all_providers or p in all_providers]
        if not self.enabled_ais:
            self.enabled_ais = all_providers  # safety: never disable everything
        print(f"[ai] enabled: {self.enabled_ais}")

    def _filtered_chain(self) -> list:
        """Return provider chain filtered to only enabled AIs."""
        if not hasattr(self, "enabled_ais") or not self.enabled_ais:
            return list(self.PROVIDER_CHAIN) if hasattr(self, "PROVIDER_CHAIN") else []
        base = list(self.PROVIDER_CHAIN) if hasattr(self, "PROVIDER_CHAIN") else list(self.enabled_ais)
        return [p for p in base if p in self.enabled_ais]
'''

UI_TOGGLE_FIX_COMMENT = """
        # ── AI TOGGLE FIX: push enabled list to ai.py ───────────────────────
        # Find your EchoApp or parent that holds self.ai and call set_enabled.
        # Replace the block below with whatever your app structure looks like:
        ai_ref = None
        if hasattr(self, "ai"):
            ai_ref = self.ai
        elif hasattr(self, "parent") and callable(self.parent):
            parent = self.parent()
            if parent and hasattr(parent, "ai"):
                ai_ref = parent.ai
        # Walk up the widget tree if needed
        if ai_ref is None:
            widget = self
            for _ in range(5):
                if hasattr(widget, "ai"):
                    ai_ref = widget.ai
                    break
                if hasattr(widget, "parent") and callable(widget.parent):
                    widget = widget.parent()
                    if widget is None: break
        if ai_ref:
            ai_ref.set_enabled(self._active_providers)
        # ────────────────────────────────────────────────────────────────────
"""


def cmd_patch():
    print(f"\n{B}{C}AI Toggle Fix — Patch{R}\n")

    # Check files exist
    for path, label in [(AI_PY, "ai.py"), (UI_PY, "ui.py")]:
        if not path.exists():
            err(f"{label} not found at {path}")
            err(f"Expected: {path}")
            print(f"\n  Make sure vision_assistant/ is at ~/vision_assistant/")
            return

    ai_content = AI_PY.read_text(encoding="utf-8")
    ui_content = UI_PY.read_text(encoding="utf-8")

    changes = []

    # What we'll do to ai.py
    if "set_enabled" not in ai_content:
        changes.append("ai.py: add set_enabled() method to EchoAI class")
        changes.append("ai.py: add _filtered_chain() method to EchoAI class")
    else:
        changes.append("ai.py: set_enabled() already exists — skip")

    # What we'll do to ui.py
    toggle_match = re.search(r"def _toggle_ai\(.*?\)(.*?)(?=\n    def |\nclass |\Z)",
                             ui_content, re.DOTALL)
    if toggle_match and "set_enabled" not in toggle_match.group(1):
        changes.append("ui.py: inject set_enabled() call into _toggle_ai() body")
    elif "set_enabled" in ui_content:
        changes.append("ui.py: set_enabled() call already present — skip")
    else:
        changes.append("ui.py: _toggle_ai() not found — will add usage comment at top of file")

    changes.append(f"Both files backed up as .bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

    print("  Changes planned:")
    for c in changes: info(c)
    print(f"\n{B}  Proceed? [y/N]{R} ", end="")
    if input().strip().lower() not in ("y", "yes"):
        warn("Cancelled.")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── Patch ai.py ───────────────────────────────────────────────────────────
    if "set_enabled" not in ai_content:
        shutil.copy2(AI_PY, AI_PY.with_suffix(f".bak_{ts}"))
        # Find the EchoAI class and inject after the class definition line
        # Try to insert before the last method or after __init__
        insert_after = re.search(r"(def __init__\(self.*?\n(?:.*?\n)*?(?=    def ))", ai_content)
        if insert_after:
            pos = insert_after.end()
            ai_content = ai_content[:pos] + AI_SET_ENABLED + ai_content[pos:]
        else:
            # Append to end of file
            ai_content += "\n" + AI_SET_ENABLED
        AI_PY.write_text(ai_content, encoding="utf-8")
        ok("ai.py patched — set_enabled() + _filtered_chain() added")
    else:
        ok("ai.py already has set_enabled() — skipped")

    # ── Patch ui.py ───────────────────────────────────────────────────────────
    shutil.copy2(UI_PY, UI_PY.with_suffix(f".bak_{ts}"))

    toggle_match = re.search(
        r"(    def _toggle_ai\(self[^)]*\):[^\n]*\n)(.*?)(?=\n    def |\nclass |\Z)",
        ui_content, re.DOTALL
    )
    if toggle_match and "set_enabled" not in toggle_match.group(2):
        # Find where the method body ends its first logical block
        # Inject the fix comment + call right before the last line of the method
        method_start = toggle_match.start(2)
        method_end = toggle_match.end(2)
        body = toggle_match.group(2)

        # Find a good insertion point — after any provider list manipulation
        inject_after = None
        for pattern in [r"_active_providers.*\n", r"enabled_ais.*\n", r"provider.*\n"]:
            m = list(re.finditer(pattern, body))
            if m:
                inject_after = m[-1].end()
                break

        if inject_after:
            new_body = body[:inject_after] + UI_TOGGLE_FIX_COMMENT + body[inject_after:]
        else:
            # Just append before the last line
            new_body = body.rstrip() + "\n" + UI_TOGGLE_FIX_COMMENT

        ui_content = ui_content[:method_start] + new_body + ui_content[method_end:]
        UI_PY.write_text(ui_content, encoding="utf-8")
        ok("ui.py patched — set_enabled() call injected into _toggle_ai()")
    elif "set_enabled" in ui_content:
        ok("ui.py already calls set_enabled() — skipped")
    else:
        # Can't find _toggle_ai — add a prominent comment at top
        header = f"""# ── AI TOGGLE FIX NEEDED ────────────────────────────────────────────────────
# _toggle_ai() not found automatically. Add this to your toggle handler:
#
#   if hasattr(self, "ai") and self.ai:
#       self.ai.set_enabled(self._active_providers)
#
# And add set_enabled() + _filtered_chain() to EchoAI in ai.py.
# See echo_ai_toggle_fix.py for the full method code.
# ─────────────────────────────────────────────────────────────────────────────

"""
        UI_PY.write_text(header + ui_content, encoding="utf-8")
        warn("_toggle_ai() not found — added fix instructions at top of ui.py")

    print(f"\n  {B}Done!{R} Test by:")
    print(f"  1. Toggle off all providers except one in the UI")
    print(f"  2. Send a message")
    print(f"  3. Check terminal — should show: [ai] enabled: ['<provider>']")
    print(f"  4. Confirm only that provider responds\n")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"
    if cmd == "scan":   cmd_scan()
    elif cmd == "patch": cmd_patch()
    else:
        print(f"Usage: python3 {Path(__file__).name} scan|patch")
