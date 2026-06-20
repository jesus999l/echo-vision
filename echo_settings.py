#!/usr/bin/env python3
"""
echo_settings.py — Echo Cookie & Provider Settings
Run: ~/vision_env/bin/python3 ~/vision_assistant/echo_settings.py
Opens on http://localhost:8766
"""
from flask import Flask, request, jsonify, render_template_string
import json, pathlib, subprocess

app = Flask(__name__)
COOKIE_FILE = pathlib.Path.home() / "vision_assistant/config/session_cookies.json"
COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)

HTML = """
<!DOCTYPE html>
<html>
<head>
<title>Echo Settings</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #060810; color: #e0e0e0; font-family: monospace; padding: 30px; }
h1 { color: #00ffc8; margin-bottom: 6px; font-size: 20px; }
.sub { color: #ffffff44; font-size: 12px; margin-bottom: 30px; }
.card { background: #0d1117; border: 1px solid #ffffff11; border-radius: 8px; padding: 20px; margin-bottom: 20px; }
.card h2 { color: #7b2fff; font-size: 14px; margin-bottom: 14px; }
label { display: block; color: #ffffff88; font-size: 11px; margin-bottom: 4px; margin-top: 12px; }
input, textarea { width: 100%; background: #060810; border: 1px solid #ffffff22; color: #e0e0e0;
  padding: 8px; border-radius: 4px; font-family: monospace; font-size: 12px; }
textarea { height: 80px; resize: vertical; }
button { margin-top: 16px; background: #7b2fff; color: white; border: none; padding: 10px 24px;
  border-radius: 4px; cursor: pointer; font-family: monospace; font-size: 13px; }
button:hover { background: #00ffc8; color: #060810; }
.status { margin-top: 10px; font-size: 12px; color: #00ffc8; min-height: 18px; }
.providers { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
</style>
</head>
<body>
<h1>⚡ Echo Settings</h1>
<p class="sub">Cookie manager & provider config — changes take effect immediately</p>

<div class="card">
  <h2>🍪 Provider Cookies</h2>
  <p style="color:#ffffff44;font-size:11px;margin-bottom:12px">
    Get cookies from Firefox → Cookie Editor extension → Export as JSON for each provider
  </p>
  <div class="providers">
    <div>
      <label>ChatGPT Cookie</label>
      <textarea id="chatgpt" placeholder="Paste ChatGPT session cookie here..."></textarea>
    </div>
    <div>
      <label>Gemini Cookie</label>
      <textarea id="gemini" placeholder="Paste Gemini session cookie here..."></textarea>
    </div>
    <div>
      <label>Perplexity Cookie</label>
      <textarea id="perplexity" placeholder="Paste Perplexity session cookie here..."></textarea>
    </div>
    <div>
      <label>Grok Cookie</label>
      <textarea id="grok" placeholder="Paste Grok session cookie here..."></textarea>
    </div>
  </div>
  <button onclick="saveCookies()">💾 Save Cookies</button>
  <button onclick="loadCookies()" style="background:#ffffff11;margin-left:8px">📂 Load Current</button>
  <div class="status" id="cookie-status"></div>
</div>

<div class="card">
  <h2>🔑 API Keys</h2>
  <label>OpenRouter API Key</label>
  <input type="password" id="openrouter" placeholder="sk-or-...">
  <button onclick="saveKeys()">💾 Save Keys</button>
  <div class="status" id="key-status"></div>
</div>

<div class="card">
  <h2>🧪 Test Providers</h2>
  <button onclick="testProvider('proxima')">Test Proxima</button>
  <button onclick="testProvider('ollama')" style="margin-left:8px">Test Ollama</button>
  <div class="status" id="test-status"></div>
</div>

<script>
async function saveCookies() {
  const cookies = {
    chatgpt: document.getElementById('chatgpt').value,
    gemini: document.getElementById('gemini').value,
    perplexity: document.getElementById('perplexity').value,
    grok: document.getElementById('grok').value,
  };
  const r = await fetch('/api/cookies', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(cookies)});
  const d = await r.json();
  document.getElementById('cookie-status').textContent = d.ok ? '✅ Saved!' : '❌ ' + d.error;
}
async function loadCookies() {
  const r = await fetch('/api/cookies');
  const d = await r.json();
  if (d.cookies) {
    document.getElementById('chatgpt').value = d.cookies.chatgpt || '';
    document.getElementById('gemini').value = d.cookies.gemini || '';
    document.getElementById('perplexity').value = d.cookies.perplexity || '';
    document.getElementById('grok').value = d.cookies.grok || '';
    document.getElementById('cookie-status').textContent = '✅ Loaded';
  }
}
async function saveKeys() {
  const r = await fetch('/api/keys', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({openrouter: document.getElementById('openrouter').value})});
  const d = await r.json();
  document.getElementById('key-status').textContent = d.ok ? '✅ Saved!' : '❌ ' + d.error;
}
async function testProvider(p) {
  document.getElementById('test-status').textContent = 'Testing...';
  const r = await fetch('/api/test/' + p);
  const d = await r.json();
  document.getElementById('test-status').textContent = d.ok ? '✅ ' + d.response : '❌ ' + d.error;
}
window.onload = loadCookies;
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.get("/api/cookies")
def get_cookies():
    try:
        data = json.loads(COOKIE_FILE.read_text()) if COOKIE_FILE.exists() else {}
        return jsonify({"cookies": data})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.post("/api/cookies")
def set_cookies():
    try:
        data = request.json
        COOKIE_FILE.write_text(json.dumps(data, indent=2))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.post("/api/keys")
def set_keys():
    try:
        data = request.json
        env_file = pathlib.Path.home() / "vision_assistant/.env"
        lines = env_file.read_text().splitlines() if env_file.exists() else []
        lines = [l for l in lines if not l.startswith("OPENROUTER_API_KEY=")]
        if data.get("openrouter"):
            lines.append(f"OPENROUTER_API_KEY={data['openrouter']}")
        env_file.write_text("\n".join(lines) + "\n")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.get("/api/test/<provider>")
def test_provider(provider):
    try:
        import requests as req
        if provider == "proxima":
            r = req.post("http://localhost:3210/v1/chat/completions",
                json={"messages":[{"role":"user","content":"say hi in 3 words"}]},
                timeout=300)
            text = r.json()["choices"][0]["message"]["content"]
            return jsonify({"ok": True, "response": text[:100]})
        elif provider == "ollama":
            r = req.post("http://localhost:11434/api/generate",
                json={"model":"qwen3:4b","prompt":"say hi","stream":False,"think":False,"num_predict":20,"keep_alive":-1},
                timeout=300)
            text = r.json().get("response","")
            return jsonify({"ok": True, "response": text[:100]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

if __name__ == "__main__":
    print("Echo Settings running at http://localhost:8766")
    app.run(host="0.0.0.0", port=8766, debug=False)
