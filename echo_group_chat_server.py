#!/usr/bin/env python3
"""
echo_group_chat_server.py v2 — Echo Multi-AI Group Chat
- Provider selection (pick which AIs respond)
- Modes: chat / think / plan / learn / vault
- Obsidian vault integration for saving insights
- Mobile-friendly via Tailscale
"""
import os, sys, json, time, threading, logging, urllib.request, subprocess
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from collections import deque
import re

sys.path.insert(0, str(Path.home() / "vision_assistant"))

PORT           = 8484
PROXIMA_URL    = "http://localhost:3210"
OLLAMA_URL     = "http://127.0.0.1:11434/api/generate"
HISTORY_FILE   = Path.home() / "vision_assistant/group_chat_history.json"
VAULT_DIR      = Path("/home/jesus999l/Documents/ObsidianVault")
PLANS_DIR      = VAULT_DIR / "Echo/Plans"
INSIGHTS_DIR   = VAULT_DIR / "Echo/Insights"
MAX_HISTORY    = 100

PROVIDERS = [
    {"id":"perplexity","label":"Perplexity","emoji":"🔍","color":"#20B2AA","fallback":False,"default":True},
    {"id":"chatgpt",   "label":"ChatGPT",   "emoji":"💬","color":"#74AA9C","fallback":False,"default":True},
    {"id":"gemini",    "label":"Gemini",    "emoji":"✦", "color":"#4285F4","fallback":False,"default":True},
    {"id":"claude",    "label":"Claude",    "emoji":"◆", "color":"#CC785C","fallback":True, "default":False},
]

MODES = {
    "chat":  {"label":"Chat",    "emoji":"💬","desc":"Normal conversation"},
    "think": {"label":"Think",   "emoji":"🧠","desc":"Deep reasoning — all AIs think step by step"},
    "plan":  {"label":"Plan",    "emoji":"📋","desc":"ChatGPT+Gemini debate → Perplexity checks → synthesis"},
    "learn": {"label":"Learn",   "emoji":"📚","desc":"Extract key insights, save to Obsidian"},
    "vault": {"label":"Vault",   "emoji":"🗄","desc":"Organize + clean Obsidian vault"},
}

MODE_PROMPTS = {
    "think": "Think through this step by step, showing your reasoning. Be thorough.\n\nQuestion: {msg}",
    "plan":  "Create a detailed actionable plan for: {msg}\n\nInclude: steps, timeline, dependencies, risks.",
    "learn": "Explain this clearly and extract the 3-5 most important insights a learner should remember: {msg}",
    "vault": "Suggest how to organize this in a personal knowledge base. Recommend: folder structure, tags, connections to related concepts: {msg}",
}

log = logging.getLogger("echo_group")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

history = deque(maxlen=MAX_HISTORY)
provider_status = {p["id"]: "unknown" for p in PROVIDERS}

def load_history():
    if HISTORY_FILE.exists():
        try:
            history.extend(json.loads(HISTORY_FILE.read_text())[-MAX_HISTORY:])
        except: pass

def save_history():
    try: HISTORY_FILE.write_text(json.dumps(list(history), indent=2))
    except: pass

def proxima_available():
    try:
        urllib.request.urlopen(f"{PROXIMA_URL}/api/status", timeout=2)
        return True
    except: return False

def ask_proxima(provider_id, message, conv_history=None):
    start = time.time()
    try:
        messages = []
        if conv_history:
            for h in list(conv_history)[-4:]:
                messages.append({"role":"user","content":h["message"]})
                for r in h.get("responses",[]):
                    if r.get("provider")==provider_id and r.get("text"):
                        messages.append({"role":"assistant","content":r["text"][:400]})
        messages.append({"role":"user","content":message})
        payload = json.dumps({"model":provider_id,"messages":messages}).encode()
        req = urllib.request.Request(
            f"{PROXIMA_URL}/v1/chat/completions", data=payload,
            headers={"Content-Type":"application/json"}
        )
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
            text = (data.get("choices",[{}])[0].get("message",{}).get("content")
                    or data.get("response") or data.get("text") or str(data))
            provider_status[provider_id] = "ok"
            return {"provider":provider_id,"text":text.strip(),"ms":round((time.time()-start)*1000),"error":None}
    except Exception as e:
        provider_status[provider_id] = "error"
        return {"provider":provider_id,"text":"","ms":0,"error":str(e)[:120]}

def ask_local(message):
    try:
        payload = json.dumps({"model":"qwen3:4b","prompt":f"/no_think\n{message}","stream":False,
                               "options":{"temperature":0.3,"num_predict":400}}).encode()
        req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read()).get("response","").strip()
    except: return ""

def save_to_vault(topic, responses, mode):
    """Save responses to Obsidian vault."""
    try:
        if mode == "plan":
            target = PLANS_DIR
            prefix = "Plan"
        else:
            target = INSIGHTS_DIR
            prefix = "Insight" if mode == "learn" else "Note"
        target.mkdir(parents=True, exist_ok=True)
        date = datetime.now().strftime("%Y-%m-%d")
        slug = re.sub(r'[^\w\s-]','',topic[:40]).strip().replace(' ','-')
        fname = target / f"{date}-{prefix}-{slug}.md"
        lines = [f"# {topic}", f"*{date} · mode:{mode}*", ""]
        for r in responses:
            if r.get("text"):
                p = next((p for p in PROVIDERS if p["id"]==r["provider"]),{})
                lines += [f"## {p.get('emoji','')} {p.get('label',r['provider'])}", r["text"], ""]
        lines += ["---", f"tags: echo/{mode} ai-generated", ""]
        fname.write_text("\n".join(lines))
        return str(fname)
    except Exception as e:
        return f"vault save failed: {e}"

def fan_out(message, mode, selected_providers):
    """Fan out message to selected providers based on mode."""
    actual_msg = MODE_PROMPTS.get(mode, "{msg}").format(msg=message) if mode != "chat" else message

    # Plan mode: structured debate
    if mode == "plan":
        results = []
        debaters = [p for p in selected_providers if p in ["chatgpt","gemini"]]
        factcheck = [p for p in selected_providers if p == "perplexity"]
        rest = [p for p in selected_providers if p not in debaters + factcheck]

        for p_id in debaters:
            r = ask_proxima(p_id, f"Debate this plan from your perspective: {message}", list(history))
            results.append(r)
            yield r

        for p_id in factcheck:
            debate_text = " | ".join(r["text"][:200] for r in results if r["text"])
            r = ask_proxima(p_id, f"Fact-check and find gaps in these plans: {debate_text}\nOriginal request: {message}", list(history))
            results.append(r)
            yield r

        for p_id in rest:
            r = ask_proxima(p_id, actual_msg, list(history))
            results.append(r)
            yield r
        return

    # All other modes: parallel fan-out
    with ThreadPoolExecutor(max_workers=len(selected_providers)) as pool:
        futures = {pool.submit(ask_proxima, p_id, actual_msg, list(history)): p_id
                   for p_id in selected_providers}
        for future in as_completed(futures):
            yield future.result()

# ── HTML ─────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Echo · Group Chat</title>
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#7c6af7">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Echo">
<script>if('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');</script>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0c0d10;--surface:#13141a;--surface2:#1a1b23;--border:#252630;
  --text:#dde0ed;--muted:#585970;--accent:#7c6af7;
  --perplexity:#20B2AA;--chatgpt:#74AA9C;--gemini:#4285F4;--claude:#CC785C;
}
body{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;
     height:100dvh;display:flex;flex-direction:column;overflow:hidden}

/* HEADER */
.hdr{display:flex;align-items:center;gap:10px;padding:10px 14px;
     background:var(--surface);border-bottom:1px solid var(--border);flex-shrink:0}
.logo{font-family:'Space Mono',monospace;font-size:12px;font-weight:700;
      color:var(--accent);letter-spacing:3px}
.live{width:6px;height:6px;border-radius:50%;background:#2ecc71;
      box-shadow:0 0 5px #2ecc71;animation:blink 2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
.hdr-right{margin-left:auto;display:flex;align-items:center;gap:8px}

/* TOOLBAR */
.toolbar{display:flex;gap:6px;padding:8px 14px;background:var(--surface);
         border-bottom:1px solid var(--border);flex-shrink:0;overflow-x:auto;flex-wrap:wrap}

/* PROVIDER TOGGLES */
.provider-toggle{display:flex;align-items:center;gap:5px;padding:5px 10px;
  border-radius:20px;border:1.5px solid var(--border);cursor:pointer;
  font-size:11px;font-family:'Space Mono',monospace;letter-spacing:.5px;
  transition:all .15s;user-select:none;color:var(--muted);white-space:nowrap}
.provider-toggle.active{border-color:var(--col);color:var(--col);
  background:color-mix(in srgb,var(--col) 10%,transparent)}
.provider-toggle input{display:none}

.divider{width:1px;background:var(--border);margin:0 2px;flex-shrink:0}

/* MODE BUTTONS */
.mode-btn{padding:5px 10px;border-radius:20px;border:1.5px solid var(--border);
  cursor:pointer;font-size:11px;font-family:'Space Mono',monospace;
  transition:all .15s;background:transparent;color:var(--muted);white-space:nowrap}
.mode-btn.active{border-color:var(--accent);color:var(--accent);
  background:color-mix(in srgb,var(--accent) 12%,transparent)}

/* MESSAGES */
.messages{flex:1;overflow-y:auto;padding:14px;display:flex;
          flex-direction:column;gap:18px;scroll-behavior:smooth}
.messages::-webkit-scrollbar{width:3px}
.messages::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}

/* USER BUBBLE */
.user-row{display:flex;justify-content:flex-end;gap:8px;align-items:flex-end}
.user-bubble{background:var(--accent);color:#fff;padding:9px 14px;
  border-radius:16px 16px 4px 16px;max-width:78%;font-size:13.5px;
  line-height:1.55;word-break:break-word}
.mode-tag{font-size:10px;font-family:'Space Mono',monospace;
  color:var(--muted);padding:3px 7px;background:var(--surface2);
  border-radius:8px;margin-bottom:4px;align-self:flex-end}

/* AI GRID */
.ai-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}
@media(max-width:560px){.ai-grid{grid-template-columns:1fr}}

.card{background:var(--surface);border:1px solid var(--border);border-radius:11px;
  overflow:hidden;position:relative;transition:border-color .2s}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:var(--cc)}
.card:hover{border-color:var(--cc)}
.card-hdr{display:flex;align-items:center;gap:7px;padding:9px 12px 7px;
  border-bottom:1px solid var(--border)}
.card-emoji{font-size:13px}
.card-name{font-family:'Space Mono',monospace;font-size:10px;font-weight:700;
  letter-spacing:1px;text-transform:uppercase;color:var(--cc)}
.card-ms{margin-left:auto;font-size:10px;color:var(--muted);font-family:'Space Mono',monospace}
.card-body{padding:11px 13px;font-size:13px;line-height:1.65;white-space:pre-wrap;
  word-break:break-word;color:var(--text)}
.card.loading .card-body{color:var(--muted);display:flex;align-items:center;gap:6px}
.card.error .card-body{color:#e74c3c;font-size:12px}

/* COPY BUTTON */
.card-copy{position:absolute;top:8px;right:8px;width:22px;height:22px;
  border-radius:5px;border:1px solid var(--border);background:var(--surface2);
  color:var(--muted);cursor:pointer;font-size:11px;display:flex;
  align-items:center;justify-content:center;opacity:0;transition:opacity .15s}
.card:hover .card-copy{opacity:1}

/* VAULT SAVE BUTTON */
.vault-btn{display:none;margin:4px 12px 10px;padding:5px 10px;border-radius:7px;
  border:1px solid #2ecc7144;background:transparent;color:#2ecc71;
  font-size:11px;font-family:'Space Mono',monospace;cursor:pointer;
  transition:background .15s}
.vault-btn:hover{background:color-mix(in srgb,#2ecc71 12%,transparent)}
.vault-btn.show{display:block}

/* TYPING DOTS */
.dots span{display:inline-block;width:4px;height:4px;background:var(--muted);
  border-radius:50%;animation:dot .9s infinite}
.dots span:nth-child(2){animation-delay:.15s}
.dots span:nth-child(3){animation-delay:.3s}
@keyframes dot{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}

/* EMPTY STATE */
.empty{flex:1;display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:10px;color:var(--muted);text-align:center;padding:32px}
.empty-logo{font-family:'Space Mono',monospace;font-size:28px;
  font-weight:700;color:var(--accent);letter-spacing:4px}
.empty-sub{font-size:12px;line-height:1.6;max-width:260px}

/* INPUT */
.input-area{padding:10px 14px;background:var(--surface);
  border-top:1px solid var(--border);display:flex;gap:8px;
  align-items:flex-end;flex-shrink:0}
.input-wrap{flex:1;background:var(--surface2);border:1px solid var(--border);
  border-radius:12px;display:flex;align-items:flex-end;padding:9px 12px;gap:7px;
  transition:border-color .2s}
.input-wrap:focus-within{border-color:var(--accent)}
textarea{flex:1;background:transparent;border:none;outline:none;
  color:var(--text);font-family:'DM Sans',sans-serif;font-size:14px;
  resize:none;max-height:110px;line-height:1.5}
textarea::placeholder{color:var(--muted)}
.send-btn{width:34px;height:34px;border-radius:9px;border:none;
  background:var(--accent);color:#fff;cursor:pointer;font-size:15px;
  display:flex;align-items:center;justify-content:center;
  transition:opacity .15s,transform .1s;flex-shrink:0}
.send-btn:hover{opacity:.85}
.send-btn:active{transform:scale(.92)}
.send-btn:disabled{opacity:.25;cursor:not-allowed}
@media(max-width:480px){
  .toolbar{gap:4px;padding:7px 10px}
  .messages{padding:10px 9px;gap:14px}
  .user-bubble{max-width:90%;font-size:13px}
  .card-body{font-size:12.5px}
}
</style>
</head>
<body>
<div class="hdr">
  <div class="live"></div>
  <div class="logo">ECHO</div>
  <div class="hdr-right">
    <span id="proxStatus" style="font-size:11px;color:var(--muted);font-family:'Space Mono',monospace">proxima…</span>
  </div>
</div>

<div class="toolbar" id="toolbar">
  <!-- provider toggles injected by JS -->
</div>

<div class="messages" id="messages">
  <div class="empty" id="empty">
    <div class="empty-logo">ECHO</div>
    <div class="empty-sub">Select AIs and a mode, then send a message.<br>All selected AIs respond in parallel.</div>
  </div>
</div>

<div class="input-area">
  <div class="input-wrap">
    <textarea id="input" placeholder="Ask anything…" rows="1"
      oninput="autoResize(this)"
      onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();send()}"></textarea>
  </div>
  <button class="send-btn" id="sendBtn" onclick="send()">↑</button>
</div>

<script>
const PROVIDERS = [
  {id:'perplexity',label:'Perplexity',emoji:'🔍',color:'#20B2AA',fallback:false,on:true},
  {id:'chatgpt',   label:'ChatGPT',   emoji:'💬',color:'#74AA9C',fallback:false,on:true},
  {id:'gemini',    label:'Gemini',    emoji:'✦', color:'#4285F4',fallback:false,on:true},
  {id:'claude',    label:'Claude',    emoji:'◆', color:'#CC785C',fallback:true, on:false},
];
const MODES = [
  {id:'chat', label:'💬 Chat',  desc:'Normal conversation'},
  {id:'think',label:'🧠 Think', desc:'Step-by-step reasoning'},
  {id:'plan', label:'📋 Plan',  desc:'Debate → fact-check → synthesis'},
  {id:'learn',label:'📚 Learn', desc:'Extract key insights'},
  {id:'vault',label:'🗄 Vault', desc:'Organize for Obsidian'},
];
let currentMode = 'chat';
let loading = false;

// Build toolbar
function buildToolbar() {
  const tb = document.getElementById('toolbar');
  tb.innerHTML = '';
  PROVIDERS.forEach(p => {
    const el = document.createElement('label');
    el.className = 'provider-toggle' + (p.on?' active':'');
    el.style.setProperty('--col', p.color);
    el.innerHTML = `<input type="checkbox" ${p.on?'checked':''} onchange="toggleProvider('${p.id}',this.checked)">
      ${p.emoji} ${p.label}${p.fallback?' <span style="color:var(--muted);font-size:9px">(fallback)</span>':''}`;
    tb.appendChild(el);
  });
  const div = document.createElement('div');
  div.className = 'divider';
  tb.appendChild(div);
  MODES.forEach(m => {
    const btn = document.createElement('button');
    btn.className = 'mode-btn' + (m.id===currentMode?' active':'');
    btn.textContent = m.label;
    btn.title = m.desc;
    btn.onclick = () => setMode(m.id);
    tb.appendChild(btn);
  });
}

function toggleProvider(id, on) {
  const p = PROVIDERS.find(p=>p.id===id);
  if (p) p.on = on;
  buildToolbar();
}

function setMode(id) {
  currentMode = id;
  buildToolbar();
  const input = document.getElementById('input');
  const hints = {think:'Think through: ',plan:'Plan: ',learn:'Explain: ',vault:'Organize: '};
  if (hints[id] && !input.value) input.placeholder = hints[id] + '…';
  else input.placeholder = 'Ask anything…';
}

function autoResize(el) {
  el.style.height='auto';
  el.style.height=Math.min(el.scrollHeight,110)+'px';
}

function scrollBot() {
  const m=document.getElementById('messages');
  requestAnimationFrame(()=>{ m.scrollTop=m.scrollHeight; });
}

function clearEmpty() {
  const e=document.getElementById('empty');
  if(e) e.remove();
}

function mkCard(p, exchangeId) {
  const card = document.createElement('div');
  card.className = 'card loading';
  card.id = `card-${p.id}-${exchangeId}`;
  card.style.setProperty('--cc', p.color);
  card.innerHTML = `
    <button class="card-copy" title="Copy" onclick="copyCard('${p.id}','${exchangeId}')">⧉</button>
    <div class="card-hdr">
      <span class="card-emoji">${p.emoji}</span>
      <span class="card-name">${p.label}</span>
      <span class="card-ms" id="ms-${p.id}-${exchangeId}">…</span>
    </div>
    <div class="card-body" id="body-${p.id}-${exchangeId}">
      <span class="dots"><span></span><span></span><span></span></span> waiting
    </div>`;
  return card;
}

function updateCard(result, exchangeId) {
  const body = document.getElementById(`body-${result.provider}-${exchangeId}`);
  const ms = document.getElementById(`ms-${result.provider}-${exchangeId}`);
  const card = document.getElementById(`card-${result.provider}-${exchangeId}`);
  if (!body || !card) return;
  card.classList.remove('loading');
  if (result.error || !result.text) {
    card.classList.add('error');
    body.textContent = result.error || '(no response)';
    if(ms) ms.textContent = 'error';
  } else {
    body.textContent = result.text;
    if(ms) ms.textContent = result.ms + 'ms';
  }
  scrollBot();
}

function copyCard(providerId, exchangeId) {
  const body = document.getElementById(`body-${providerId}-${exchangeId}`);
  if (body) navigator.clipboard.writeText(body.textContent).catch(()=>{});
}

async function saveVault(message, exchangeId) {
  const btn = document.getElementById(`vault-${exchangeId}`);
  if(btn) { btn.textContent='saving…'; btn.disabled=true; }
  try {
    const r = await fetch('/vault', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({message, exchange_id: exchangeId, mode: currentMode})
    });
    const d = await r.json();
    if(btn) btn.textContent = d.ok ? '✓ saved to vault' : '✗ failed';
  } catch(e) {
    if(btn) btn.textContent = '✗ error';
  }
}

async function send() {
  const input = document.getElementById('input');
  const btn = document.getElementById('sendBtn');
  const message = input.value.trim();
  const selected = PROVIDERS.filter(p=>p.on).map(p=>p.id);
  if (!message || loading || !selected.length) return;

  clearEmpty();
  loading = true;
  btn.disabled = true;
  input.value = '';
  input.style.height = 'auto';

  const exId = Date.now().toString();
  const mode = currentMode;

  // Build exchange DOM
  const ex = document.createElement('div');
  ex.id = `ex-${exId}`;
  const modeInfo = MODES.find(m=>m.id===mode);
  if (mode !== 'chat') {
    const tag = document.createElement('div');
    tag.className = 'user-row';
    tag.innerHTML = `<div class="mode-tag">${modeInfo?.label||mode}</div>`;
    ex.appendChild(tag);
  }
  const row = document.createElement('div');
  row.className = 'user-row';
  row.innerHTML = `<div class="user-bubble">${message.replace(/</g,'&lt;')}</div>`;
  ex.appendChild(row);

  const grid = document.createElement('div');
  grid.className = 'ai-grid';
  PROVIDERS.filter(p=>p.on).forEach(p => grid.appendChild(mkCard(p, exId)));
  ex.appendChild(grid);

  // Vault save button (show for learn/plan/vault modes)
  if (['learn','plan','vault'].includes(mode)) {
    const vb = document.createElement('button');
    vb.className = 'vault-btn show';
    vb.id = `vault-${exId}`;
    vb.textContent = '🗄 Save to Obsidian vault';
    vb.onclick = () => saveVault(message, exId);
    ex.appendChild(vb);
  }

  document.getElementById('messages').appendChild(ex);
  scrollBot();

  try {
    const resp = await fetch('/chat', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({message, mode, providers: selected})
    });
    if (!resp.ok) throw new Error('HTTP '+resp.status);
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true) {
      const {done,value} = await reader.read();
      if (done) break;
      buf += dec.decode(value,{stream:true});
      const lines = buf.split('\n');
      buf = lines.pop();
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const d = JSON.parse(line.slice(6));
            if (d.type==='response') updateCard(d, exId);
            if (d.type==='proxima') {
              document.getElementById('proxStatus').textContent =
                d.ok ? '● proxima' : '○ proxima down';
            }
          } catch(e){}
        }
      }
    }
  } catch(e) {
    selected.forEach(id => updateCard({provider:id,text:'',error:'Connection error',ms:0}, exId));
  }
  loading = false;
  btn.disabled = false;
  input.focus();
}

async function loadStatus() {
  try {
    const d = await (await fetch('/status')).json();
    const el = document.getElementById('proxStatus');
    el.textContent = d.proxima ? '● proxima' : '○ proxima down';
    el.style.color = d.proxima ? '#2ecc71' : '#e74c3c';
  } catch(e){}
}

buildToolbar();
loadStatus();
setInterval(loadStatus, 20000);
document.getElementById('input').focus();
</script>
</body>
</html>"""

# ── HTTP HANDLER ─────────────────────────────────────────────────────────────
vault_exchanges = {}  # exId -> results, saved in memory until vault save

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if '/status' not in str(args): log.info(f"{self.address_string()} - {fmt%args}")

    def cors(self):
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")

    def do_OPTIONS(self):
        self.send_response(200); self.cors(); self.end_headers()

    def do_GET(self):
        if self.path in ("/","/index.html"):
            self.send_response(200)
            self.send_header("Content-Type","text/html;charset=utf-8")
            self.cors(); self.end_headers()
            self.wfile.write(HTML.encode())
        elif self.path=="/status":
            body=json.dumps({"proxima":proxima_available(),"providers":provider_status,
                             "history":len(history)}).encode()
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.cors(); self.end_headers(); self.wfile.write(body)
        elif self.path=="/history":
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.cors(); self.end_headers()
            self.wfile.write(json.dumps(list(history)).encode())

        elif self.path == "/manifest.json":
            manifest = json.dumps({
                "name": "Echo · Group Chat",
                "short_name": "Echo",
                "description": "Multi-AI group chat via Proxima",
                "start_url": "/",
                "display": "standalone",
                "background_color": "#0c0d10",
                "theme_color": "#7c6af7",
                "orientation": "portrait-primary",
                "icons": [
                    {"src": "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='20' fill='%237c6af7'/><text y='70' x='50' text-anchor='middle' font-size='55' font-family='monospace' fill='white'>E</text></svg>",
                     "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}
                ]
            })
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json")
            self.cors(); self.end_headers()
            self.wfile.write(manifest.encode())

        elif self.path == "/sw.js":
            sw = """
self.addEventListener('fetch', e => {
  if (e.request.url.includes('/chat') || e.request.url.includes('/status')) return;
  e.respondWith(
    caches.open('echo-v1').then(cache =>
      cache.match(e.request).then(resp => resp || fetch(e.request).then(r => {
        cache.put(e.request, r.clone()); return r;
      }))
    )
  );
});"""
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.cors(); self.end_headers()
            self.wfile.write(sw.encode())

        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length",0))
        body = json.loads(self.rfile.read(length) or b'{}')

        if self.path=="/vault":
            ex_id = body.get("exchange_id")
            message = body.get("message","")
            mode = body.get("mode","learn")
            results = vault_exchanges.get(ex_id,[])
            path = save_to_vault(message, results, mode)
            resp = json.dumps({"ok": not path.startswith("vault save failed"), "path":path}).encode()
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.cors(); self.end_headers(); self.wfile.write(resp)
            return

        if self.path != "/chat":
            self.send_response(404); self.end_headers(); return

        message  = body.get("message","").strip()
        mode     = body.get("mode","chat")
        selected = body.get("providers", [p["id"] for p in PROVIDERS if p["default"]])
        if not message: self.send_response(400); self.end_headers(); return

        self.send_response(200)
        self.send_header("Content-Type","text/event-stream")
        self.send_header("Cache-Control","no-cache")
        self.send_header("X-Accel-Buffering","no")
        self.cors(); self.end_headers()

        def sse(obj):
            try:
                self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
                self.wfile.flush()
            except: pass

        sse({"type":"proxima","ok":proxima_available()})

        results = []
        ex_id = str(int(time.time()*1000))

        for result in fan_out(message, mode, selected):
            results.append(result)
            sse({"type":"response",**result})

        # Store for vault save
        vault_exchanges[ex_id] = results

        # Auto-save to vault for learn/vault modes
        if mode in ("learn","vault") and any(r["text"] for r in results):
            save_to_vault(message, results, mode)

        # Persist history
        history.append({"message":message,"mode":mode,"timestamp":datetime.now().isoformat(),
                        "responses":results})
        save_history()
        sse({"type":"done","exchange_id":ex_id})

def main():
    load_history()
    if proxima_available(): log.info("✓ Proxima connected")
    else: log.warning("⚠ Start Proxima: cd ~/Applications/Proxima && npm start")
    try:
        ip = subprocess.check_output(["tailscale","ip","-4"],text=True).strip()
        log.info(f"📱 Mobile: http://{ip}:{PORT}")
    except: pass
    log.info(f"🖥  Local:  http://localhost:{PORT}")
    HTTPServer(("0.0.0.0",PORT),Handler).serve_forever()

if __name__=="__main__": main()
