#!/usr/bin/env python3
"""
echo_vault.py — Echo's knowledge base server
Port: 8767
Backend: turbovec (TurboQuant vector index) + sentence-transformers
Reads: ~/Documents/ObsidianVault/Echo/ + ~/.flint/vault/
"""
import os, json, re, time, threading
from pathlib import Path
from flask import Flask, request, jsonify

app = Flask(__name__)

VAULT_PATHS = [
    Path.home() / "Documents/ObsidianVault/Echo",
    Path.home() / ".flint/vault",
    Path.home() / "Documents/ObsidianVault",
    Path.home() / "Documents/ObsidianVault/Echo",
    Path.home() / ".flint/vault",
    Path.home() / "Documents/ObsidianVault/Cognition",
    Path.home() / "Documents/ObsidianVault/Conversations",
]

# Global state
index = None
docs = []  # list of {id, path, title, content, chunk}
embedder = None
INDEX_READY = False

def load_embedder():
    global embedder
    try:
        from sentence_transformers import SentenceTransformer
        embedder = SentenceTransformer("all-MiniLM-L6-v2")
        print("[vault] Embedder ready: all-MiniLM-L6-v2")
    except ImportError:
        print("[vault] sentence-transformers not installed — install with pip install sentence-transformers")
        embedder = None

def chunk_text(text, size=300, overlap=50):
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i+size])
        chunks.append(chunk)
        i += size - overlap
    return chunks

def load_vault():
    global index, docs, INDEX_READY
    if embedder is None:
        print("[vault] No embedder, skipping index build")
        return

    import turbovec
    import numpy as np

    all_docs = []
    for vault_path in VAULT_PATHS:
        if not vault_path.exists():
            continue
        print(f"[vault] Scanning {vault_path}")
        for md_file in vault_path.rglob("*.md"):
            try:
                content = md_file.read_text(errors="ignore")
                title = md_file.stem
                chunks = chunk_text(content)
                for i, chunk in enumerate(chunks):
                    all_docs.append({
                        "id": len(all_docs),
                        "path": str(md_file),
                        "title": title,
                        "content": chunk,
                        "chunk_idx": i,
                    })
            except Exception as e:
                print(f"[vault] Error reading {md_file}: {e}")

    if not all_docs:
        print("[vault] No documents found")
        return

    print(f"[vault] Embedding {len(all_docs)} chunks...")
    texts = [d["content"] for d in all_docs]
    embeddings = embedder.encode(texts, batch_size=64, show_progress_bar=True)
    embeddings = embeddings.astype("float32")

    dim = embeddings.shape[1]
    idx = turbovec.TurboQuantIndex(dim, bits=4)
    ids = list(range(len(all_docs)))
    idx.add(embeddings, ids)

    docs = all_docs
    index = idx
    INDEX_READY = True
    print(f"[vault] Index ready — {len(docs)} chunks from {len(set(d['path'] for d in docs))} files")

@app.route("/")
def root():
    return jsonify({
        "status": "ready" if INDEX_READY else "loading",
        "docs": len(docs),
        "files": len(set(d["path"] for d in docs)) if docs else 0,
    })

@app.route("/search", methods=["POST"])
def search():
    if not INDEX_READY:
        return jsonify({"error": "Index not ready yet"}), 503

    data = request.json or {}
    query = data.get("query", "").strip()
    k = int(data.get("k", 5))

    if not query:
        return jsonify({"error": "No query provided"}), 400

    import numpy as np
    q_vec = embedder.encode([query]).astype("float32")
    results = index.search(q_vec, k=k)

    hits = []
    for doc_id, score in zip(results[0][0], results[1][0]):
        if doc_id < len(docs):
            d = docs[doc_id]
            hits.append({
                "title": d["title"],
                "path": d["path"],
                "content": d["content"][:500],
                "score": float(score),
            })

    return jsonify({"query": query, "results": hits})

@app.route("/list", methods=["GET"])
def list_files():
    files = {}
    for d in docs:
        p = d["path"]
        if p not in files:
            files[p] = d["title"]
    return jsonify({"files": list(files.values()), "count": len(files)})

@app.route("/read", methods=["POST"])
def read_file():
    data = request.json or {}
    title = data.get("title", "").lower()
    for d in docs:
        if d["title"].lower() == title and d["chunk_idx"] == 0:
            full = Path(d["path"]).read_text(errors="ignore")
            return jsonify({"title": d["title"], "content": full})
    return jsonify({"error": "Not found"}), 404

@app.route("/ingest", methods=["POST"])
def ingest():
    """Add a new note directly"""
    data = request.json or {}
    title = data.get("title", f"note_{int(time.time())}")
    content = data.get("content", "")
    vault = VAULT_PATHS[0]
    vault.mkdir(parents=True, exist_ok=True)
    path = vault / f"{title}.md"
    path.write_text(f"# {title}\n\n{content}")
    # Trigger reload in background
    threading.Thread(target=load_vault, daemon=True).start()
    return jsonify({"status": "saved", "path": str(path)})

if __name__ == "__main__":
    print("[vault] Starting Echo Vault on :8767")
    threading.Thread(target=load_embedder, daemon=False).start()
    # Wait for embedder then load vault
    def delayed_load():
        for _ in range(60):
            time.sleep(2)
            if embedder is not None:
                load_vault()
                return
        print('[vault] embedder never loaded')
    threading.Thread(target=delayed_load, daemon=True).start()
    app.run(host="0.0.0.0", port=8767, debug=False)
