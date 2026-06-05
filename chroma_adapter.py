#!/usr/bin/env python3
"""
chroma_adapter.py — Echo KB → ChromaDB Bridge
Embeds Knowledge_Base/ files using nomic-embed-text via Ollama.
Stores in a persistent local ChromaDB collection (no server needed).

Usage:
  python3 chroma_adapter.py --sync        # embed all KB files
  python3 chroma_adapter.py --query "X"   # test semantic search
  python3 chroma_adapter.py --status      # show collection state
  python3 chroma_adapter.py --rebuild     # wipe + re-embed everything

Import:
  from chroma_adapter import query_kb, sync_kb
"""

import sys, os, re, json, hashlib, logging, urllib.request
from pathlib import Path
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────────────────

VAULT        = Path.home() / "Documents/ObsidianVault/Echo"
KB           = VAULT / "Knowledge_Base"
CHROMA_PATH  = Path.home() / ".chromadb" / "echo"
COLLECTION   = "echo_kb"
EMBED_MODEL  = "nomic-embed-text"
OLLAMA_EMBED = "http://127.0.0.1:11434/api/embeddings"
HASH_CACHE   = CHROMA_PATH / "file_hashes.json"
TOP_K        = 3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("chroma_adapter")

# ── CHROMADB CLIENT ───────────────────────────────────────────────────

def get_client():
    try:
        import chromadb
        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        return chromadb.PersistentClient(path=str(CHROMA_PATH))
    except ImportError:
        log.error("chromadb not installed. Run: pip3 install chromadb --break-system-packages")
        sys.exit(1)

def get_collection(client=None):
    c = client or get_client()
    return c.get_or_create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"}
    )

# ── EMBEDDING ─────────────────────────────────────────────────────────

def embed(text: str) -> list | None:
    """Get embedding vector from Ollama nomic-embed-text."""
    payload = json.dumps({
        "model": EMBED_MODEL,
        "prompt": text[:3000]
    }).encode()
    req = urllib.request.Request(
        OLLAMA_EMBED, data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()).get("embedding")
    except Exception as e:
        log.error(f"Embed failed: {e}")
        return None

def check_ollama():
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
        return True
    except:
        return False

# ── FILE PARSING ──────────────────────────────────────────────────────

def parse_kb_file(path: Path) -> dict:
    """Parse a KB markdown file into structured metadata + content."""
    raw = path.read_text(encoding="utf-8").strip()

    # Extract frontmatter
    fm = {}
    content = raw
    if raw.startswith("---"):
        end = raw.find("---", 3)
        if end > 0:
            fm_block = raw[3:end].strip()
            content = raw[end+3:].strip()
            for line in fm_block.split("\n"):
                if ":" in line:
                    k, _, v = line.partition(":")
                    fm[k.strip()] = v.strip()

    # Extract title
    title_m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else path.stem.replace("-", " ").title()

    # Extract status
    status = fm.get("status", "unknown")

    # Build searchable text: title + rules + what_works + current_status sections
    sections = []
    for section in re.split(r"^##\s+", content, flags=re.MULTILINE):
        if section.strip():
            sections.append(section.strip()[:500])
    search_text = f"{title}\n\n" + "\n\n".join(sections[:4])

    return {
        "id": path.stem,
        "title": title,
        "status": status,
        "tags": fm.get("tags", ""),
        "compiled_at": fm.get("compiled_at", ""),
        "content": content[:2000],
        "search_text": search_text[:2000],
        "path": str(path),
        "hash": hashlib.md5(raw.encode()).hexdigest()
    }

# ── HASH CACHE ────────────────────────────────────────────────────────

def load_hashes() -> dict:
    if HASH_CACHE.exists():
        try:
            return json.loads(HASH_CACHE.read_text())
        except:
            pass
    return {}

def save_hashes(hashes: dict):
    HASH_CACHE.parent.mkdir(parents=True, exist_ok=True)
    HASH_CACHE.write_text(json.dumps(hashes, indent=2))

# ── SYNC ─────────────────────────────────────────────────────────────

def sync_kb(force=False) -> dict:
    """
    Embed all new/changed KB files into ChromaDB.
    Skips unchanged files (hash comparison).
    Returns: {added, updated, skipped, errors}
    """
    if not check_ollama():
        log.error("Ollama not running — cannot embed. Start Ollama first.")
        return {"added": 0, "updated": 0, "skipped": 0, "errors": 1}

    if not KB.exists():
        log.error(f"Knowledge_Base not found at {KB}")
        return {"added": 0, "updated": 0, "skipped": 0, "errors": 1}

    col = get_collection()
    hashes = {} if force else load_hashes()
    stats = {"added": 0, "updated": 0, "skipped": 0, "errors": 0}

    kb_files = list(KB.glob("*.md"))
    log.info(f"Syncing {len(kb_files)} KB files to ChromaDB...")

    for f in kb_files:
        try:
            parsed = parse_kb_file(f)
            file_hash = parsed["hash"]

            # Skip if unchanged
            if not force and hashes.get(parsed["id"]) == file_hash:
                stats["skipped"] += 1
                continue

            # Get embedding
            vec = embed(parsed["search_text"])
            if not vec:
                log.warning(f"  Could not embed {f.name}")
                stats["errors"] += 1
                continue

            # Upsert into ChromaDB
            col.upsert(
                ids=[parsed["id"]],
                embeddings=[vec],
                documents=[parsed["content"]],
                metadatas=[{
                    "title": parsed["title"],
                    "status": parsed["status"],
                    "path": parsed["path"],
                    "compiled_at": parsed["compiled_at"],
                    "hash": file_hash
                }]
            )

            action = "updated" if hashes.get(parsed["id"]) else "added"
            stats[action] += 1
            hashes[parsed["id"]] = file_hash
            log.info(f"  {action}: {parsed['title']}")

        except Exception as e:
            log.error(f"  Error processing {f.name}: {e}")
            stats["errors"] += 1

    save_hashes(hashes)
    total = col.count()
    log.info(f"Sync complete. Collection: {total} entries. {stats}")
    return stats

# ── QUERY ─────────────────────────────────────────────────────────────

def query_kb(query: str, top_k: int = TOP_K) -> list:
    """
    Semantic search over KB collection.
    Returns: [{id, title, content, status, score}]
    """
    if not check_ollama():
        return []

    col = get_collection()
    if col.count() == 0:
        log.warning("ChromaDB collection empty — run sync first")
        return []

    vec = embed(query)
    if not vec:
        return []

    try:
        results = col.query(
            query_embeddings=[vec],
            n_results=min(top_k, col.count()),
            include=["documents", "metadatas", "distances"]
        )
    except Exception as e:
        log.error(f"Query failed: {e}")
        return []

    output = []
    ids       = results.get("ids", [[]])[0]
    docs      = results.get("documents", [[]])[0]
    metas     = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for i, doc_id in enumerate(ids):
        # ChromaDB cosine distance: 0=identical, 2=opposite. Convert to similarity.
        similarity = 1 - (distances[i] / 2) if distances else 0
        if similarity < 0.3:
            continue
        meta = metas[i] if i < len(metas) else {}
        output.append({
            "id": doc_id,
            "title": meta.get("title", doc_id),
            "content": docs[i] if i < len(docs) else "",
            "status": meta.get("status", "unknown"),
            "path": meta.get("path", ""),
            "score": round(similarity, 3)
        })

    return output

def get_context_block(query: str, top_k: int = TOP_K) -> str:
    """
    Returns formatted context string for Ollama prompt injection.
    Drop-in replacement for echo_kb_context.get_kb_context()
    """
    results = query_kb(query, top_k)
    if not results:
        return ""

    lines = ["[ECHO KNOWLEDGE BASE — semantic context]"]
    for r in results:
        lines.append(f"\n## {r['title']} [score: {r['score']}]")
        # Extract most relevant section
        content = r["content"]
        excerpt = content[:400].strip()
        lines.append(excerpt)
    lines.append("\n[end KB context]")
    return "\n".join(lines)

# ── STATUS ─────────────────────────────────────────────────────────────

def status():
    print(f"\nChromaDB Adapter Status")
    print(f"{'─'*40}")
    print(f"Storage  : {CHROMA_PATH}")
    print(f"KB path  : {KB}")
    print(f"Ollama   : {'running ✓' if check_ollama() else 'not running ✗'}")

    try:
        col = get_collection()
        count = col.count()
        print(f"Collection: {COLLECTION} — {count} entries")

        hashes = load_hashes()
        kb_files = list(KB.glob("*.md"))
        unsynced = [f.stem for f in kb_files if f.stem not in hashes]
        if unsynced:
            print(f"Unsynced : {len(unsynced)} files need embedding")
            for u in unsynced:
                print(f"  - {u}")
        else:
            print(f"Sync     : all {len(kb_files)} KB files embedded ✓")
    except Exception as e:
        print(f"Collection error: {e}")
    print()

# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--status" in args:
        status()

    elif "--sync" in args or not args:
        status()
        sync_kb(force="--rebuild" in args)

    elif "--rebuild" in args:
        log.info("Rebuilding — wiping existing collection...")
        c = get_client()
        try:
            c.delete_collection(COLLECTION)
            log.info("Collection wiped.")
        except:
            pass
        # Also clear hash cache
        if HASH_CACHE.exists():
            HASH_CACHE.unlink()
        sync_kb(force=True)

    elif "--query" in args:
        idx = args.index("--query")
        q = " ".join(args[idx+1:])
        if not q:
            print("Usage: chroma_adapter.py --query <text>")
            sys.exit(1)
        print(f"Query: {q}\n")
        results = query_kb(q)
        if results:
            for r in results:
                print(f"  {r['score']:.3f}  {r['title']}  [{r['status']}]")
            print(f"\nContext block:\n{get_context_block(q)}")
        else:
            print("No results — run --sync first")

    else:
        print(__doc__)
