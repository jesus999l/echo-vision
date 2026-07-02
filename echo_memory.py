"""
echo_memory.py — ChromaDB persistent conversation memory
Uses embedded PersistentClient (no server required).
"""
import hashlib, json, time
from pathlib import Path
import chromadb

CHROMA_PATH = Path.home() / "vision_assistant" / "chroma_db"
COLLECTION  = "echo_memory"
EMBED_MODEL = "nomic-embed-text"
OLLAMA_EMBED = "http://127.0.0.1:11434/api/embed"

def _client():
    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_PATH))

def _embed(text):
    try:
        import urllib.request, json as _json
        payload = _json.dumps({"model": EMBED_MODEL, "input": text}).encode()
        req = urllib.request.Request(
            OLLAMA_EMBED, data=payload,
            headers={"Content-Type": "application/json"})
        resp = _json.loads(urllib.request.urlopen(req, timeout=10).read())
        return resp["embeddings"][0]
    except Exception:
        return None

def _collection():
    return _client().get_or_create_collection(
        COLLECTION, metadata={"hnsw:space": "cosine"})

def save_turn(session_id, role, content):
    vec = _embed(content)
    if vec is None:
        return False
    col = _collection()
    doc_id = hashlib.md5(f"{session_id}{role}{time.time()}".encode()).hexdigest()
    col.upsert(ids=[doc_id], embeddings=[vec],
        documents=[content],
        metadatas=[{"session": session_id, "role": role, "ts": int(time.time())}])
    return True

def recall(query, n=3, session_id=None):
    vec = _embed(query)
    if vec is None:
        return []
    col = _collection()
    if col.count() == 0:
        return []
    where = {"session": session_id} if session_id else None
    results = col.query(query_embeddings=[vec],
        n_results=min(n, col.count()),
        where=where,
        include=["documents", "metadatas", "distances"])
    out = []
    for i, doc in enumerate(results["documents"][0]):
        score = 1 - results["distances"][0][i] / 2
        if score > 0.25:
            meta = results["metadatas"][0][i]
            out.append({"role": meta.get("role"), "content": doc, "score": round(score, 3)})
    return out

def health_check():
    try:
        col = _collection()
        return {"ok": True, "entries": col.count(), "path": str(CHROMA_PATH)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    print("Health:", health_check())
    save_turn("test", "user", "Echo is a privacy-first AI assistant built on Linux Mint")
    save_turn("test", "assistant", "Memory wired. I will remember this.")
    print("Recall:", recall("what is Echo"))

# ── Compatibility interface expected by ai.py ──
class EchoMemory:
    def __init__(self):
        h = health_check()
        self._ready = h["ok"]

    def context_for(self, query: str, k: int = 5, max_chars: int = 1500) -> str:
        if not query.strip():
            return ""
        results = recall(query, n=k)
        if not results:
            return ""
        lines = []
        for r in results:
            role = r.get("role", "?")
            content = r.get("content", "")[:300]
            lines.append(f"[{role}] {content}")
        return "\n".join(lines)[:max_chars]
