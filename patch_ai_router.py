#!/usr/bin/env python3
"""
patch_ai_router.py
Wires event_router telemetry calls into ai.py.
Run from anywhere:  python3 patch_ai_router.py
"""
import shutil, sys
from pathlib import Path

AI_PY = Path.home() / "vision_assistant" / "ai.py"

if not AI_PY.exists():
    print(f"ERROR: {AI_PY} not found"); sys.exit(1)

src = AI_PY.read_text()

# Guard — don't double-patch
if "event_router" in src:
    print("SKIP: event_router already present in ai.py"); sys.exit(0)

# ── Backup ────────────────────────────────────────────────────────────
backup = AI_PY.with_suffix(".py.bak")
shutil.copy2(AI_PY, backup)
print(f"[1/4] Backup saved → {backup}")

# ── Patch 1: import ───────────────────────────────────────────────────
OLD_IMPORT = 'from config import LLM_URL, VISION_API_URL, VISION_MODELS, DEFAULT_MODEL'
NEW_IMPORT = (
    'from config import LLM_URL, VISION_API_URL, VISION_MODELS, DEFAULT_MODEL\n'
    '\n'
    'try:\n'
    '    from event_router import router as _router\n'
    'except ImportError:\n'
    '    _router = None'
)

if OLD_IMPORT not in src:
    print("ERROR: could not find import anchor in ai.py"); sys.exit(1)

src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)
print("[2/4] Import block patched")

# ── Patch 2: ask() — activate on entry, idle on exit ─────────────────
OLD_ASK = (
    'def ask(prompt, model=None, ocr_text="", screenshot_path="", ui_callback=None):\n'
    '    model = model or DEFAULT_MODEL\n'
    '    try:\n'
    '        if is_vision_model(model) and screenshot_path and os.path.exists(screenshot_path):\n'
    '            response = _ask_vision(prompt, model, screenshot_path)\n'
    '        else:\n'
    '            response = _ask_text(prompt, model, ocr_text, screenshot_path)\n'
    '\n'
    '        clean, action_results = parse_and_execute_actions(response)\n'
    '        save_message("user", prompt, model=model, screenshot=screenshot_path, ocr_text=ocr_text)\n'
    '        save_message("ai", clean, model=model)\n'
    '        if action_results and ui_callback:\n'
    '            ui_callback(action_results)\n'
    '        return clean\n'
    '    except Exception as e:\n'
    '        print(f"[ai] error: {e}")\n'
    '        return f"AI error: {e}"'
)

NEW_ASK = (
    'def ask(prompt, model=None, ocr_text="", screenshot_path="", ui_callback=None):\n'
    '    model = model or DEFAULT_MODEL\n'
    '    if _router:\n'
    '        _router.activate("LLM", 85)\n'
    '        _router.activate("ROUTER", 70)\n'
    '        _router.activate("CONTEXT", 60)\n'
    '        _router.set_thought(prompt[:80])\n'
    '    try:\n'
    '        if is_vision_model(model) and screenshot_path and os.path.exists(screenshot_path):\n'
    '            response = _ask_vision(prompt, model, screenshot_path)\n'
    '        else:\n'
    '            response = _ask_text(prompt, model, ocr_text, screenshot_path)\n'
    '\n'
    '        clean, action_results = parse_and_execute_actions(response)\n'
    '        save_message("user", prompt, model=model, screenshot=screenshot_path, ocr_text=ocr_text)\n'
    '        save_message("ai", clean, model=model)\n'
    '        if action_results and ui_callback:\n'
    '            ui_callback(action_results)\n'
    '        return clean\n'
    '    except Exception as e:\n'
    '        print(f"[ai] error: {e}")\n'
    '        return f"AI error: {e}"\n'
    '    finally:\n'
    '        if _router:\n'
    '            _router.idle("LLM")\n'
    '            _router.standby("ROUTER", 25)\n'
    '            _router.standby("CONTEXT", 20)'
)

if OLD_ASK not in src:
    print("WARN: ask() body not matched exactly — skipping patch 2")
    print("      You may need to add router calls to ask() manually")
else:
    src = src.replace(OLD_ASK, NEW_ASK, 1)
    print("[3/4] ask() wrapped with router activate/idle")

# ── Patch 3: execute_ai_action() — TASKS node ────────────────────────
OLD_EXEC = (
    'def execute_ai_action(data):\n'
    '    try:\n'
    '        t = data.get("type", "")'
)

NEW_EXEC = (
    'def execute_ai_action(data):\n'
    '    try:\n'
    '        if _router:\n'
    '            _router.activate("TASKS", 75)\n'
    '        t = data.get("type", "")'
)

if OLD_EXEC not in src:
    print("WARN: execute_ai_action() anchor not matched — skipping patch 3")
else:
    src = src.replace(OLD_EXEC, NEW_EXEC, 1)
    # Also idle TASKS at end of function — find the last return in execute_ai_action
    src = src.replace(
        '        return False, f"Unknown action: {t}"\n'
        '    except Exception as e:\n'
        '        return False, f"Action error: {e}"',
        '        return False, f"Unknown action: {t}"\n'
        '    except Exception as e:\n'
        '        return False, f"Action error: {e}"\n'
        '    finally:\n'
        '        if _router:\n'
        '            _router.idle("TASKS")',
        1
    )
    print("[4/4] execute_ai_action() wrapped with TASKS activate/idle")

# ── Write ─────────────────────────────────────────────────────────────
AI_PY.write_text(src)
print(f"\nDone. {AI_PY} patched.")
print(f"Backup at: {backup}")
print("\nTest with:")
print("  cd ~/vision_assistant && python3 -c \"from ai import ask; print('ok')\"")
