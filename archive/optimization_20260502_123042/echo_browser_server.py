"""
echo_browser_server.py — Local HTTP server for Echo Firefox sidebar.

Endpoints:
  GET  /status          — health check
  POST /chat            — chat with Echo (Ollama or Claude API)
  GET  /interests       — Echo's current interest topics (from Firefox history)
  GET  /bookmarks       — recent bookmarks
  POST /announce        — Echo announces something to user
  GET  /models          — available AI models

Runs on port 59996. Started by main.py on boot.
"""
import json, os, sys, sqlite3, shutil, tempfile, threading, time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.request

sys.path.insert(0, os.path.expanduser("~/vision_assistant"))

PORT = 59996
FF_PROFILE = os.path.expanduser(
    "~/.mozilla/firefox/sjkuigqa.default-release"
)
PLACES_DB  = os.path.join(FF_PROFILE, "places.sqlite")
INTERESTS_FILE = os.path.expanduser("~/vision_assistant/echo_interests.json")

AVAILABLE_MODELS = [
    {"id": "gemma3:latest",   "name": "Gemma 3 (Local/Fast)",    "type": "ollama"},
    {"id": "qwen2.5:14b",     "name": "Qwen 2.5 14B (Local)",    "type": "ollama"},
    {"id": "mistral:latest",  "name": "Mistral (Local)",         "type": "ollama"},
    {"id": "claude",          "name": "Claude (Anthropic API)",  "type": "claude"},
]

_current_model = "mistral:latest"

# ── FIREFOX DATA ──────────────────────────────────────────────────────────────
def _read_places(query, params=()):
    """Read from places.sqlite safely (copy to temp to avoid lock)."""
    if not os.path.exists(PLACES_DB):
        return []
    tmp = tempfile.mktemp(suffix=".sqlite")
    try:
        shutil.copy2(PLACES_DB, tmp)
        conn = sqlite3.connect(tmp)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[browser] places.sqlite error: {e}")
        return []
    finally:
        try: os.unlink(tmp)
        except: pass

def get_recent_bookmarks(limit=20):
    rows = _read_places("""
        SELECT b.title, p.url, b.dateAdded/1000000 as ts
        FROM moz_bookmarks b
        JOIN moz_places p ON b.fk = p.id
        WHERE b.type = 1 AND p.url NOT LIKE 'place:%'
        ORDER BY b.dateAdded DESC LIMIT ?
    """, (limit,))
    return rows

def get_recent_history(limit=50):
    rows = _read_places("""
        SELECT title, url, last_visit_date/1000000 as ts, visit_count
        FROM moz_places
        WHERE last_visit_date IS NOT NULL AND title IS NOT NULL
          AND url NOT LIKE 'about:%' AND url NOT LIKE 'moz-%'
        ORDER BY last_visit_date DESC LIMIT ?
    """, (limit,))
    return rows

def get_tab_groups():
    """Read Firefox tab groups from sessionstore."""
    session_file = os.path.join(FF_PROFILE, "sessionstore-backups", "recovery.jsonlz4")
    session_json  = os.path.join(FF_PROFILE, "sessionstore.jsonlz4")
    # Try to read tab titles from session
    tabs = []
    for sf in [session_json, session_file]:
        if os.path.exists(sf):
            try:
                import subprocess
                # Use Python to decompress mozlz4
                r = subprocess.run(
                    ["/home/jesus999l/vision_env/bin/python3", "-c", f"""
import struct, lz4.block, json, sys
with open('{sf}', 'rb') as f:
    magic = f.read(8)
    data = lz4.block.decompress(f.read(), uncompressed_size=100*1024*1024)
    session = json.loads(data)
    tabs = []
    for w in session.get('windows', []):
        for t in w.get('tabs', []):
            entries = t.get('entries', [])
            if entries:
                tabs.append(entries[-1].get('title', ''))
    print(json.dumps(tabs))
"""], capture_output=True, text=True, timeout=5
                )
                if r.returncode == 0:
                    tabs = json.loads(r.stdout.strip())
                    break
            except: pass
    return tabs

# ── INTEREST ENGINE ────────────────────────────────────────────────────────────
def build_interest_profile():
    """Analyze bookmarks + history to build topic profile."""
    bookmarks = get_recent_bookmarks(30)
    history   = get_recent_history(100)

    topics = {}
    keywords = [
        "warframe", "linux", "python", "ai", "gaming", "music", "privacy",
        "android", "ollama", "docker", "homelab", "security", "tech",
        "video", "anime", "programming", "modding", "hardware"
    ]

    all_text = " ".join([
        (b.get("title") or "") + " " + (b.get("url") or "")
        for b in bookmarks + history
    ]).lower()

    for kw in keywords:
        count = all_text.count(kw)
        if count > 0:
            topics[kw] = count

    # Sort by frequency
    sorted_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)

    profile = {
        "timestamp":    time.time(),
        "top_topics":   sorted_topics[:10],
        "bookmark_count": len(bookmarks),
        "history_count":  len(history),
        "recent_sites": list(set([
            urlparse(h.get("url", "")).netloc
            for h in history[:20]
            if h.get("url")
        ]))[:10]
    }

    with open(INTERESTS_FILE, "w") as f:
        json.dump(profile, f, indent=2)

    return profile

def get_interests():
    """Load cached interests or rebuild."""
    if os.path.exists(INTERESTS_FILE):
        try:
            data = json.load(open(INTERESTS_FILE))
            # Rebuild if older than 1 hour
            if time.time() - data.get("timestamp", 0) < 3600:
                return data
        except: pass
    return build_interest_profile()

# ── CHAT ──────────────────────────────────────────────────────────────────────
def chat_ollama(message, model="gemma3:latest", context=""):
    """Chat with local Ollama model."""
    system = f"""You are Echo, an AI assistant integrated into the user's browser.
You know their interests: {context}
Be concise, helpful, and personal. Announce yourself as Echo when starting a conversation."""

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": message}
        ],
        "stream": False
    }).encode()

    req = urllib.request.Request(
        "http://127.0.0.1:11434/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        result = json.loads(r.read())
        return result["choices"][0]["message"]["content"]

def _get_api_key():
    """Read Claude API key from settings.json."""
    try:
        cfg = json.load(open(os.path.expanduser("~/vision_assistant/settings.json")))
        key = cfg.get("claude_api_key", "")
        if key and key != "YOUR_API_KEY_HERE":
            return key
    except: pass
    return None

def chat_claude(message, context=""):
    """Chat with Claude via Anthropic API."""
    api_key = _get_api_key()
    if not api_key:
        return "Claude API key not configured. Add your key to ~/vision_assistant/settings.json as claude_api_key."
    try:
        payload = json.dumps({
            "model": "claude-sonnet-4-5",
            "max_tokens": 1000,
            "system": f"You are helping Echo, a personal AI assistant, learn about her user. User interests: {context}. Be helpful and concise.",
            "messages": [{"role": "user", "content": message}]
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            }
        )
        with urllib.request.urlopen(req, timeout=90) as r:
            result = json.loads(r.read())
            return result["content"][0]["text"]
    except Exception as e:
        return f"Claude API error: {e}"

def do_chat(message, model=None):
    global _current_model
    m = model or _current_model
    interests = get_interests()
    context = ", ".join([t[0] for t in interests.get("top_topics", [])[:5]])

    if m == "claude":
        return chat_claude(message, context)
    else:
        return chat_ollama(message, m, context)

# ── HTTP HANDLER ──────────────────────────────────────────────────────────────
class EchoHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress default HTTP logs

    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Origin")
        self.send_header("Access-Control-Allow-Credentials", "false")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/status":
            self._send_json({"status": "ok", "model": _current_model})

        elif path == "/interests":
            self._send_json(get_interests())

        elif path == "/bookmarks":
            self._send_json(get_recent_bookmarks(15))

        elif path == "/models":
            self._send_json(AVAILABLE_MODELS)

        elif path == "/history":
            self._send_json(get_recent_history(20))

        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        global _current_model
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if path == "/chat":
            message = body.get("message", "")
            model   = body.get("model", _current_model)
            if not message:
                self._send_json({"error": "no message"}, 400)
                return
            try:
                response = do_chat(message, model)
                self._send_json({"response": response, "model": model})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif path == "/model":
            model = body.get("model")
            if model:
                _current_model = model
                self._send_json({"ok": True, "model": _current_model})
            else:
                self._send_json({"error": "no model"}, 400)

        elif path == "/announce":
            # Echo announces something — trigger TTS
            text = body.get("text", "")
            if text:
                try:
                    sys.path.insert(0, os.path.expanduser("~/vision_assistant"))
                    from voice import speak
                    speak(f"Echo here. {text}")
                except: pass
            self._send_json({"ok": True})

        elif path == "/rebuild_interests":
            profile = build_interest_profile()
            self._send_json(profile)

        else:
            self._send_json({"error": "not found"}, 404)

# ── SERVER LIFECYCLE ──────────────────────────────────────────────────────────
_server = None

def start_browser_server():
    global _server
    try:
        _server = HTTPServer(("127.0.0.1", PORT), EchoHandler)
        t = threading.Thread(target=_server.serve_forever, daemon=True)
        t.start()
        print(f"[browser] Echo browser server running on port {PORT}")
        # Build initial interest profile in background
        threading.Thread(target=build_interest_profile, daemon=True).start()
        return _server
    except Exception as e:
        print(f"[browser] Server failed to start: {e}")
        return None

if __name__ == "__main__":
    print(f"Starting Echo browser server on port {PORT}...")
    start_browser_server()
    print("Testing interests...")
    p = get_interests()
    print(f"Top topics: {p.get('top_topics', [])[:5]}")
    print(f"Recent sites: {p.get('recent_sites', [])[:5]}")
    input("Press Enter to stop...")
