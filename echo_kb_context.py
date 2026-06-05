#!/usr/bin/env python3
"""echo_kb_context.py v2 — ChromaDB first, keyword fallback"""
import sys, re, math, logging
from pathlib import Path
from collections import Counter

VAULT = Path.home() / "Documents/ObsidianVault/Echo"
KB    = VAULT / "Knowledge_Base"
TOP_K = 3
log   = logging.getLogger("echo_kb_context")

def _try_chroma(query, top_k):
    try:
        sys.path.insert(0, str(Path.home() / "vision_assistant"))
        from chroma_adapter import query_kb, get_context_block
        results = query_kb(query, top_k)
        if results: return get_context_block(query, top_k), results
    except Exception as e: log.debug(f"ChromaDB: {e}")
    return None, []

def _tokenize(t): return re.findall(r"\b[a-z]{3,}\b", t.lower())

def _load_entries():
    entries = []
    if not KB.exists(): return entries
    for f in sorted(KB.glob("*.md")):
        try: raw = f.read_text(encoding="utf-8").strip()
        except: continue
        if len(raw) < 30: continue
        m = re.search(r"^#\s+(.+)$", raw, re.MULTILINE)
        title = m.group(1).strip() if m else f.stem.replace("-"," ").title()
        content = re.sub(r"^---.*?---\s*","",raw,flags=re.DOTALL).strip()
        entries.append({"path":f,"name":f.stem,"title":title,"content":content,"raw":raw})
    return entries

def _keyword_search(query, entries, top_k):
    N = len(entries); df = Counter()
    for e in entries:
        for w in set(_tokenize(e["content"])): df[w] += 1
    idf = {w: math.log((N+1)/(n+1))+1 for w,n in df.items()}
    qt = set(_tokenize(query)); scored = []
    for e in entries:
        tokens = _tokenize(e["content"]); tf = Counter(tokens); total = len(tokens) or 1
        score = sum((tf[t]/total)*idf.get(t,0) for t in qt if t in tf)
        for t in qt:
            if len(t)>4 and t in e["content"].lower(): score += 0.3
            if t in e["title"].lower(): score += 0.5
        if score > 0: scored.append((score, e))
    scored.sort(reverse=True); return scored[:top_k]

def _excerpt(entry, query):
    content = entry["content"]; qt = set(_tokenize(query))
    sections = re.split(r"^##\s+", content, flags=re.MULTILINE)
    best, best_score = content[:400], -1
    for s in sections:
        if not s.strip(): continue
        overlap = len(qt & set(_tokenize(s)))
        if overlap > best_score: best_score, best = overlap, s[:400]
    return best.strip()

def get_kb_context(query, top_k=TOP_K):
    ctx, results = _try_chroma(query, top_k)
    if ctx: return ctx
    entries = _load_entries()
    if not entries: return ""
    scored = _keyword_search(query, entries, top_k)
    if not scored: return ""
    lines = ["[ECHO KNOWLEDGE BASE — keyword context]"]
    for score, e in scored:
        lines.append(f"\n## {e['title']}")
        lines.append(_excerpt(e, query))
    lines.append("\n[end KB context]")
    return "\n".join(lines)

def get_kb_summary():
    entries = _load_entries()
    if not entries: return "Knowledge Base is empty."
    lines = [f"Echo Knowledge Base — {len(entries)} entries:"]
    for e in entries:
        sm = re.search(r"status:\s*(\w+)", e["raw"])
        lines.append(f"  · {e['title']} [{sm.group(1) if sm else 'unknown'}]")
    return "\n".join(lines)

def build_intent_contract(objective, plan_steps, kb_context=""):
    import json, urllib.request
    prompt = f"""Echo intent compressor. ONLY valid JSON no markdown:
{{"goal":"one sentence","allowed":["files/systems that MAY change"],"forbidden":["must NOT touch"],"side_effects":["what else changes"],"verification":"one command proving success","abort_if":"stop condition"}}
Objective: {objective}
Steps: {json.dumps([s.get('action','') for s in plan_steps[:8]])}"""
    payload = json.dumps({"model":"qwen3:4b","prompt":prompt,"stream":False,
        "options":{"temperature":0.2,"num_predict":400}}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate",
        data=payload, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read()).get("response","").strip()
        return json.loads(re.sub(r"```json\s*|```\s*","",resp).strip())
    except:
        return {"goal":objective,"allowed":[],"forbidden":["echo_browser_server.py","memory.db"],
                "side_effects":["unknown"],"verification":"check logs","abort_if":"any service stops"}

def validate_against_contract(command, contract):
    for item in contract.get("forbidden", []):
        if item.lower() in command.lower():
            return {"ok": False, "violation": f"Touches forbidden: {item}"}
    return {"ok": True, "violation": None}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(get_kb_summary()); sys.exit(0)
    query = " ".join(sys.argv[1:])
    print(f"Query: {query}\n{'─'*50}")
    ctx, results = _try_chroma(query, TOP_K)
    print(f"\n[ChromaDB — {len(results)} results]")
    for r in results: print(f"  {r['score']:.3f}  {r['title']}")
    if not results: print("  (run: python3 chroma_adapter.py --sync)")
    print("\n[Context block]")
    print(get_kb_context(query))
