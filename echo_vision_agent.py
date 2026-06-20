#!/usr/bin/env python3
"""
echo_vision_agent.py — EchoSprite's eyes and hands
- Captures screen via grim
- Sends to AI with context
- Executes wlrctl/xdotool actions based on AI response
- Runs as REST server on :8769
"""
import subprocess, base64, json, re, os, time, asyncio
from pathlib import Path
from flask import Flask, request, jsonify
import sys

sys.path.insert(0, str(Path.home() / "vision_assistant"))

app = Flask(__name__)

VISION_PYTHON = Path.home() / "vision_env/bin/python3"
OLLAMA_URL = "http://localhost:11434"

# Action patterns Echo can execute
ACTION_PATTERNS = {
    "focus":  r"FOCUS:(.+)",        # FOCUS:window_title
    "close":  r"CLOSE:(.+)",        # CLOSE:window_title
    "exec":   r"EXEC:(.+)",         # EXEC:command
    "type":   r"TYPE:(.+)",         # TYPE:text to type
    "click":  r"CLICK:(\d+),(\d+)", # CLICK:x,y
    "scroll": r"SCROLL:(\w+):(\d+)",# SCROLL:up/down:amount
    "speak":  r"SPEAK:(.+)",        # SPEAK:what to say
}

def capture_screen(output_path="/tmp/echo_screen.png"):
    """Capture current screen via grim"""
    try:
        result = subprocess.run(
            ["grim", output_path],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[vision] capture error: {e}")
        return False

def capture_region(x, y, w, h, output_path="/tmp/echo_region.png"):
    """Capture a specific region"""
    try:
        result = subprocess.run(
            ["grim", "-g", f"{x},{y} {w}x{h}", output_path],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[vision] region capture error: {e}")
        return False

def image_to_base64(path):
    """Convert image to base64"""
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except:
        return None

def get_window_list():
    """Get current open windows"""
    try:
        out = subprocess.check_output(
            ["wlrctl", "toplevel", "list"],
            text=True, stderr=subprocess.DEVNULL
        )
        windows = []
        for line in out.strip().splitlines():
            parts = line.split(None, 2)
            if len(parts) >= 2:
                app_id = parts[1].rstrip(":")
                if "sticky" in app_id.lower():
                    continue
                windows.append({
                    "id": parts[0],
                    "app": app_id,
                    "title": parts[2] if len(parts) > 2 else parts[1]
                })
        return windows
    except:
        return []

def execute_action(action_type, *args):
    """Execute a compositor action"""
    try:
        if action_type == "focus":
            title = args[0].strip()
            subprocess.run(["wlrctl", "toplevel", "focus", f"title:{title}"],
                         capture_output=True)
            return f"Focused: {title}"

        elif action_type == "close":
            title = args[0].strip()
            subprocess.run(["wlrctl", "toplevel", "close", f"title:{title}"],
                         capture_output=True)
            return f"Closed: {title}"

        elif action_type == "exec":
            cmd = args[0].strip()
            subprocess.Popen(cmd, shell=True, start_new_session=True)
            return f"Executed: {cmd}"

        elif action_type == "type":
            text = args[0].strip()
            subprocess.run(["wtype", text], capture_output=True)
            return f"Typed: {text[:30]}"

        elif action_type == "click":
            x, y = int(args[0]), int(args[1])
            subprocess.run(["wlrctl", "pointer", "move", str(x), str(y)],
                         capture_output=True)
            subprocess.run(["wlrctl", "pointer", "click", "BTN_LEFT"],
                         capture_output=True)
            return f"Clicked: {x},{y}"

        elif action_type == "speak":
            text = args[0].strip()
            Path("/tmp/echo_bubble.txt").write_text(text[:280])
            try:
                import voice
                import threading
                threading.Thread(target=voice.speak, args=(text,), daemon=True).start()
            except:
                subprocess.Popen(
                    ["espeak-ng", "-v", "en-us+f2", "-s", "128", text[:200]],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            return f"Speaking: {text[:40]}"

    except Exception as e:
        return f"Action error: {e}"

def parse_and_execute_actions(ai_response):
    """Parse AI response for action commands and execute them"""
    executed = []
    for action_type, pattern in ACTION_PATTERNS.items():
        matches = re.findall(pattern, ai_response, re.MULTILINE)
        for match in matches:
            if isinstance(match, tuple):
                result = execute_action(action_type, *match)
            else:
                result = execute_action(action_type, match)
            executed.append({"action": action_type, "result": result})
            time.sleep(0.1)
    return executed

def ask_with_vision(question, include_screen=True):
    """Ask AI a question with optional screen context"""
    try:
        from echo_ai_hub import ask as ask_text
    except ImportError:
        return {"error": "echo_ai_hub not available"}

    # Build context
    windows = get_window_list()
    window_summary = "\n".join([f"- {w['app']}: {w['title'][:50]}" for w in windows[:10]])

    context = f"""You are Echo, an AI assistant with access to the user's desktop environment.

Current open windows:
{window_summary}

You can control the desktop by including action commands in your response:
- FOCUS:window_title — bring a window to focus
- CLOSE:window_title — close a window  
- EXEC:command — run a terminal command
- TYPE:text — type text in the focused window
- SPEAK:text — say something out loud
- CLICK:x,y — click at screen coordinates

User request: {question}

Respond naturally, and include action commands if needed to help the user."""

    if include_screen:
        if capture_screen():
            b64 = image_to_base64("/tmp/echo_screen.png")
            if b64:
                context += f"\n\n[Screen captured — {len(b64)//1024}KB image available]"

    response = ask_text(context)
    actions = parse_and_execute_actions(response)

    # Clean response for display (remove action commands)
    clean = re.sub(r'(FOCUS|CLOSE|EXEC|TYPE|CLICK|SCROLL|SPEAK):[^\n]+\n?', '', response).strip()

    # Auto-speak if no SPEAK action was found
    if not any(a["action"] == "speak" for a in actions) and clean:
        execute_action("speak", clean[:280])

    return {
        "question": question,
        "response": clean,
        "actions_executed": actions,
        "windows_visible": len(windows),
    }

@app.route("/")
def root():
    return jsonify({"status": "ready", "port": 8769, "name": "echo_vision_agent"})

@app.route("/ask", methods=["POST"])
def ask():
    data = request.json or {}
    question = data.get("question") or data.get("message", "")
    include_screen = data.get("screen", True)
    if not question:
        return jsonify({"error": "No question"}), 400
    result = ask_with_vision(question, include_screen)
    return jsonify(result)

@app.route("/screen", methods=["GET"])
def get_screen():
    """Return current screenshot as base64"""
    if capture_screen():
        b64 = image_to_base64("/tmp/echo_screen.png")
        if b64:
            return jsonify({"image": b64, "format": "png"})
    return jsonify({"error": "Capture failed"}), 500

@app.route("/windows", methods=["GET"])
def get_windows():
    return jsonify({"windows": get_window_list()})

@app.route("/action", methods=["POST"])
def do_action():
    """Execute a direct action"""
    data = request.json or {}
    action = data.get("action", "")
    args = data.get("args", [])
    if not action:
        return jsonify({"error": "No action"}), 400
    result = execute_action(action, *args)
    return jsonify({"result": result})

@app.route("/observe", methods=["POST"])
def observe():
    """Echo observes screen and reports what she sees"""
    capture_screen()
    windows = get_window_list()
    focused = windows[0] if windows else None

    summary = f"I can see {len(windows)} windows open."
    if focused:
        summary += f" The active window is {focused['app']}: {focused['title'][:50]}."

    execute_action("speak", summary)
    return jsonify({
        "summary": summary,
        "windows": windows,
    })

if __name__ == "__main__":
    print("[vision_agent] Starting EchoSprite vision+action layer on :8769")
    app.run(host="0.0.0.0", port=8769, debug=False)
