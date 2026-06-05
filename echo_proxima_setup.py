#!/usr/bin/env python3
"""
echo_proxima_setup.py
=====================
One-time setup tool that:
  1. Fixes config.py to route through proxima native (:3210)
  2. Fixes the broken cookie file
  3. Installs deps into vision_env (the real Echo env)
  4. Creates start-echo.sh boot script

Run: python3 echo_proxima_setup.py
"""
import os, sys, json, shutil, subprocess
from pathlib import Path

VA    = Path.home() / "vision_assistant"
VENV  = Path.home() / "vision_env"
ECHO  = Path.home() / ".echo"
CONF  = VA / "config.py"

R="\033[0m"; B="\033[1m"; G="\033[92m"; Y="\033[93m"; C="\033[96m"; E="\033[91m"
def ok(t):   print(f"  {G}✓{R} {t}")
def warn(t): print(f"  {Y}⚠{R} {t}")
def info(t): print(f"  {C}→{R} {t}")
def err(t):  print(f"  {E}✗{R} {t}")

print(f"\n{B}{C}Echo Proxima Setup{R}\n")

# ── 1. Fix broken cookie file ────────────────────────────────────────────────
cookie_path = ECHO / "cookies" / "claude.json"
if cookie_path.exists():
    raw = cookie_path.read_text().strip()
    if raw == "[PASTE YOUR CLAUDE COOKIE JSON HERE]" or len(raw) < 50:
        cookie_path.write_text("[]")
        warn("Cleared broken claude.json placeholder — ready for real cookies")
    else:
        try:
            json.loads(raw)
            ok(f"claude.json looks valid ({len(raw)} bytes)")
        except:
            cookie_path.write_text("[]")
            warn("Fixed malformed claude.json")

# ── 2. Patch config.py ───────────────────────────────────────────────────────
print(f"\n{B}Patching config.py{R}")
conf_text = CONF.read_text()

if "PROXIMA_URL" in conf_text:
    ok("config.py already has PROXIMA_URL")
else:
    shutil.copy2(CONF, CONF.with_suffix(".py.pre_proxima_native"))
    
    # Add proxima config block after OLLAMA_BASE line
    proxima_block = '''
# ── Echo Proxima Native ───────────────────────────────────────────────────────
# Browser-based multi-AI proxy (Claude, ChatGPT, Gemini, Perplexity, Grok)
# Runs on :3210, OpenAI-compatible. Start: python3 ~/vision_assistant/echo_proxima_native.py
PROXIMA_URL     = "http://localhost:3210/v1/chat/completions"
PROXIMA_MODELS  = "http://localhost:3210/v1/models"
PROXIMA_STATUS  = "http://localhost:3210/status"
PROXIMA_DEFAULT = "auto"   # auto | claude | chatgpt | gemini | perplexity | grok

def _proxima_alive():
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:3210/", timeout=1)
        return True
    except:
        return False

# Smart LLM_URL: use Proxima if running, fallback to Ollama
import os as _os
LLM_URL = PROXIMA_URL if _proxima_alive() else f"{OLLAMA_BASE}/v1/chat/completions"
# ─────────────────────────────────────────────────────────────────────────────
'''
    # Replace the static LLM_URL line
    conf_text = conf_text.replace(
        'LLM_URL         = f"{OLLAMA_BASE}/v1/chat/completions"',
        '# LLM_URL set dynamically below — proxima if running, ollama as fallback'
    )
    conf_text += proxima_block
    CONF.write_text(conf_text)
    ok("config.py patched — LLM_URL now auto-selects Proxima or Ollama")

# ── 3. Install deps into vision_env ─────────────────────────────────────────
print(f"\n{B}Installing deps into vision_env{R}")
pip = VENV / "bin" / "pip"
if pip.exists():
    for pkg in ["fastapi", "uvicorn", "playwright"]:
        r = subprocess.run([str(pip), "install", pkg, "-q"], capture_output=True)
        if r.returncode == 0:
            ok(f"{pkg} installed in vision_env")
        else:
            warn(f"{pkg} may already be installed")
    # Install chromium for playwright in vision_env
    pw = VENV / "bin" / "playwright"
    if pw.exists():
        subprocess.run([str(pw), "install", "chromium"], capture_output=True)
        ok("Chromium installed for vision_env playwright")
else:
    warn(f"vision_env not found at {VENV} — skipping dep install")

# ── 4. Copy proxima native to vision_assistant ───────────────────────────────
print(f"\n{B}Checking echo_proxima_native.py{R}")
native = VA / "echo_proxima_native.py"
downloads = Path.home() / "Downloads" / "echo_proxima_native.py"
if native.exists():
    ok("echo_proxima_native.py already in vision_assistant/")
elif downloads.exists():
    shutil.copy2(downloads, native)
    ok("Copied echo_proxima_native.py to vision_assistant/")
else:
    warn("echo_proxima_native.py not found — download it from the chat first")

# ── 5. Create start-echo.sh ──────────────────────────────────────────────────
print(f"\n{B}Creating start-echo.sh{R}")
start_sh = Path.home() / "start-echo.sh"
start_sh.write_text('''#!/usr/bin/env bash
# start-echo.sh — boot the full Echo stack
set -e

VA="$HOME/vision_assistant"
VENV="$HOME/vision_env/bin"
ECHO_VENV="$HOME/.echo/venv/bin"
COOKIE_DIR="$HOME/.echo/cookies"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║         Echo Stack Launcher          ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. Echo Proxima Native (:3210) ──────────────────────────────────────────
if pgrep -f "echo_proxima_native" > /dev/null; then
    echo "  ✓ Proxima native already running"
else
    if ls "$COOKIE_DIR"/*.json 2>/dev/null | grep -v "^\[\]" | head -1 > /dev/null 2>&1; then
        echo "  → Starting Proxima Native (:3210)..."
        cd "$VA"
        nohup "$VENV/python3" echo_proxima_native.py --headless > /tmp/echo_proxima.log 2>&1 &
        sleep 2
        if pgrep -f "echo_proxima_native" > /dev/null; then
            echo "  ✓ Proxima native running"
        else
            echo "  ⚠ Proxima native failed — check /tmp/echo_proxima.log"
        fi
    else
        echo "  ⚠ No cookies found — Proxima skipped"
        echo "    Add cookies: ~/.echo/cookies/claude.json"
    fi
fi

# ── 2. Echo Browser Server (:59996) ─────────────────────────────────────────
if pgrep -f "echo_browser_server" > /dev/null; then
    echo "  ✓ Browser server already running"
else
    echo "  → Starting Browser Server (:59996)..."
    nohup "$VENV/python3" "$VA/echo_browser_server.py" > /tmp/echo_browser.log 2>&1 &
    echo "  ✓ Browser server started"
fi

# ── 3. Echo Group Chat Server (:8484) ────────────────────────────────────────
if pgrep -f "echo_group_chat" > /dev/null; then
    echo "  ✓ Group chat server already running"
else
    echo "  → Starting Group Chat Server (:8484)..."
    nohup "$VENV/python3" "$VA/echo_group_chat_server.py" > /tmp/echo_groupchat.log 2>&1 &
    echo "  ✓ Group chat server started"
fi

# ── 4. Hermes Gateway ────────────────────────────────────────────────────────
if pgrep -f "hermes_cli.main" > /dev/null; then
    echo "  ✓ Hermes gateway already running"
else
    echo "  → Starting Hermes gateway..."
    nohup hermes gateway run --replace > /tmp/echo_hermes.log 2>&1 &
    echo "  ✓ Hermes gateway started"
fi

# ── 5. Echo Vision Assistant (main UI) ──────────────────────────────────────
if pgrep -f "vision_assistant/main.py" > /dev/null; then
    echo "  ✓ Echo Vision already running"
else
    echo "  → Starting Echo Vision Assistant..."
    nohup "$VENV/python3" "$VA/main.py" --ui > /tmp/echo_main.log 2>&1 &
    echo "  ✓ Echo Vision started"
fi

echo ""
echo "  Stack status:"
echo "    Proxima Native : http://localhost:3210/status"
echo "    Browser Server : http://localhost:59996"  
echo "    Group Chat     : http://localhost:8484"
echo "    Open WebUI     : http://localhost:8080"
echo ""
echo "  Logs:"
echo "    tail -f /tmp/echo_proxima.log"
echo "    tail -f /tmp/echo_browser.log"
echo ""
''')
start_sh.chmod(0o755)
ok("Created ~/start-echo.sh")

# ── 6. Cookie save helper ────────────────────────────────────────────────────
print(f"\n{B}Creating cookie save helper{R}")
cookie_helper = VA / "echo_save_cookies.py"
cookie_helper.write_text('''#!/usr/bin/env python3
"""
echo_save_cookies.py — Easy cookie saver
Run this after copying cookie JSON from Cookie-Editor.

Usage:
  python3 echo_save_cookies.py claude    # then paste JSON, press Ctrl+D
  python3 echo_save_cookies.py chatgpt
  python3 echo_save_cookies.py gemini
  python3 echo_save_cookies.py perplexity
  python3 echo_save_cookies.py grok
"""
import sys, json, urllib.request
from pathlib import Path

provider = sys.argv[1] if len(sys.argv) > 1 else None
if not provider:
    print("Usage: python3 echo_save_cookies.py <provider>")
    print("Providers: claude chatgpt gemini perplexity grok")
    sys.exit(1)

cookie_dir = Path.home() / ".echo" / "cookies"
cookie_dir.mkdir(parents=True, exist_ok=True)
out = cookie_dir / f"{provider}.json"

print(f"Paste your Cookie-Editor JSON for {provider}")
print("Press Ctrl+D when done:")
print("-" * 40)

try:
    data = sys.stdin.read().strip()
    # Clean up common paste artifacts
    data = data.replace("[~", "").replace("~", "").strip()
    if not data.startswith("["):
        data = "[" + data
    if not data.endswith("]"):
        data = data + "]"
    parsed = json.loads(data)
    out.write_text(json.dumps(parsed, indent=2))
    print(f"\\n✓ Saved {len(parsed)} cookies to {out}")
    
    # Hot-reload if server running
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                f"http://localhost:3210/reload_cookies/{provider}",
                method="POST"
            ), timeout=2
        )
        print(f"✓ Hot-reloaded into running server")
    except:
        print(f"→ Server not running — cookies will load on next start")
except json.JSONDecodeError as e:
    print(f"✗ Invalid JSON: {e}")
    print("  Make sure you copied the full JSON from Cookie-Editor")
    sys.exit(1)
''')
ok("Created echo_save_cookies.py")

print(f"""
{B}{G}Setup complete!{R}

{B}Next steps:{R}

  1. Save your Claude cookies properly:
     {C}python3 ~/vision_assistant/echo_save_cookies.py claude{R}
     (paste the JSON, press Ctrl+D)

  2. Boot the full stack:
     {C}~/start-echo.sh{R}

  3. Check everything is running:
     {C}curl http://localhost:3210/status{R}

  {Y}Cookie-Editor tip:{R}
  In Firefox/Chrome → Cookie-Editor extension
  → Go to claude.ai → Export → Copy to clipboard
  → Run the save helper above and paste
""")
