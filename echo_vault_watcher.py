#!/usr/bin/env python3
"""
Echo Vault Watcher Agent — Stage 2
Persistent daemon: watches Subconscious/ for new notes, clusters related files,
distills to KB via Ollama when critical mass is reached.

Usage:
  python3 echo_vault_watcher.py            # run daemon
  python3 echo_vault_watcher.py --once     # process queue once, exit
  python3 echo_vault_watcher.py --force    # distill everything in Subconscious/ now

Requires: pip3 install watchdog --break-system-packages
"""
import os, sys, re, json, time, signal, logging, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from threading import Timer

# ── CONFIG ────────────────────────────────────────────────────────────

VAULT        = Path.home() / "Documents/ObsidianVault/Echo"
SUBCONSCIOUS = VAULT / "Subconscious"
KB           = VAULT / "Knowledge_Base"
ARCHIVE      = VAULT / "Archive"
PLANS        = VAULT / "Plans"
LOG_FILE     = Path.home() / "vision_assistant" / "logs" / "echo_vault_watcher.log"

OLLAMA_URL   = "http://127.0.0.1:11434/api/generate"
DISTILL_MODEL = "qwen3:4b"        # fast distiller
CLUSTER_MODEL = "qwen3:4b"    # for subject clustering

CLUSTER_THRESHOLD = 3     # min files to trigger distillation
DEBOUNCE_SECS     = 30    # wait after last file write before processing
INDEX_REFRESH_SEC = 3600  # rebuild index every hour

# ── LOGGING ───────────────────────────────────────────────────────────

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("echo_vault_watcher")

# ── OLLAMA ────────────────────────────────────────────────────────────

def ollama_generate(prompt, model=DISTILL_MODEL, timeout=90):
    """Call Ollama and return the full response text."""
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 800}
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data.get("response", "").strip()
    except urllib.error.URLError as e:
        log.error(f"Ollama unreachable: {e}")
        return None
    except Exception as e:
        log.error(f"Ollama error: {e}")
        return None

def check_ollama():
    """Return True if Ollama is running."""
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
        return True
    except:
        return False

# ── FILE UTILS ────────────────────────────────────────────────────────

def read_file(path):
    try:
        return path.read_text(encoding="utf-8").strip()
    except:
        return ""

def write_kb_entry(slug, content):
    """Write or merge a KB entry."""
    out = KB / f"{slug}.md"
    KB.mkdir(parents=True, exist_ok=True)

    if out.exists():
        # Merge: append new findings section
        existing = read_file(out)
        now = datetime.now().isoformat(timespec="seconds")
        merged = existing.rstrip() + f"\n\n---\n<!-- merged {now} -->\n\n" + content
        out.write_text(merged, encoding="utf-8")
        log.info(f"Merged into existing KB entry: {out.name}")
    else:
        out.write_text(content, encoding="utf-8")
        log.info(f"Created KB entry: {out.name}")

    return out

def archive_files(files, reason="processed"):
    """Move files to Archive/ with prefix."""
    sub = ARCHIVE / f"subconscious_{reason}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    sub.mkdir(parents=True, exist_ok=True)
    for f in files:
        try:
            f.rename(sub / f.name)
        except Exception as e:
            log.warning(f"Could not archive {f.name}: {e}")

def rebuild_index():
    """Quick index refresh — updates Plans/INDEX.md."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    kb_files = sorted(KB.glob("*.md"))
    sub_files = sorted(SUBCONSCIOUS.glob("*.md")) if SUBCONSCIOUS.exists() else []

    lines = [
        f"# Echo Vault Index",
        f"updated: {now}",
        f"",
        f"## Knowledge Base ({len(kb_files)} entries)",
        ""
    ]
    for f in kb_files:
        lines.append(f"- [[Knowledge_Base/{f.stem}]]")

    if sub_files:
        lines += ["", f"## Subconscious Queue ({len(sub_files)} pending)", ""]
        for f in sub_files[:10]:
            lines.append(f"- [[Subconscious/{f.stem}]]")

    content = "\n".join(lines) + "\n"
    index_path = PLANS / "INDEX.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(content, encoding="utf-8")
    (VAULT / "INDEX.md").write_text(content, encoding="utf-8")

# ── CLUSTERING ────────────────────────────────────────────────────────

def cluster_files(files):
    """
    Group files by subject using Ollama.
    Returns: {subject_slug: [file_list], ...}
    Falls back to single cluster if Ollama unavailable.
    """
    if not files:
        return {}

    # Build content summary for clustering
    summaries = []
    for f in files:
        content = read_file(f)[:400]
        summaries.append(f"FILE: {f.name}\n{content[:200]}")

    prompt = f"""Group these notes by subject. Return ONLY valid JSON.
Format: {{"clusters": [{{"subject": "slug-lowercase", "files": ["filename.md", ...]}}]}}
Do not add any explanation. Notes:\n\n{''.join(summaries[:10])}"""

    response = ollama_generate(prompt, model=CLUSTER_MODEL, timeout=30)

    if not response:
        # Fallback: single cluster
        log.warning("Clustering unavailable — treating all files as one cluster")
        return {"subconscious-batch": files}

    try:
        clean = re.sub(r"```json\s*|```\s*", "", response).strip()
        data = json.loads(clean)
        clusters = {}
        file_map = {f.name: f for f in files}
        for c in data.get("clusters", []):
            slug = re.sub(r"[^\w\-]", "-", c["subject"].lower())
            matched = [file_map[fn] for fn in c.get("files", []) if fn in file_map]
            if matched:
                clusters[slug] = matched
        return clusters if clusters else {"subconscious-batch": files}
    except Exception as e:
        log.warning(f"Cluster parse failed ({e}) — single cluster fallback")
        return {"subconscious-batch": files}

# ── DISTILLATION ──────────────────────────────────────────────────────

DISTILL_PROMPT = """You are Echo's KB distiller. Extract only architectural decisions, rules, failures, and current status.
Strip all conversational noise, pleasantries, and AI filler.

Return a clean Markdown KB entry using EXACTLY this format (no extra text before or after):

---
compiled_at: {now}
source_files: {source_files}
tags: [distilled, knowledge_base, {subject}]
status: stable
---

# {title}

## What Works
- [finding]

## What Failed
- [what was tried and why it failed]

## Rules
- [constraint or decision]

## Current Status
[one sentence]

NOTES TO DISTILL:
{content}"""

def distill_cluster(subject_slug, files):
    """Distill a cluster of files into a single KB entry."""
    log.info(f"Distilling cluster '{subject_slug}' ({len(files)} files)...")

    # Aggregate content
    all_content = []
    for f in files:
        c = read_file(f)
        if c and len(c) > 50:
            all_content.append(f"=== {f.name} ===\n{c}")
        elif c:
            log.info(f"  Skipping {f.name} — too short ({len(c)} chars)")

    if not all_content:
        log.warning(f"No usable content in cluster '{subject_slug}', skipping.")
        return None

    combined = "\n\n".join(all_content)
    now = datetime.now().isoformat(timespec="seconds")
    source_list = ", ".join(f.name for f in files)

    # Infer title from subject slug
    title = subject_slug.replace("-", " ").title()

    prompt = DISTILL_PROMPT.format(
        now=now,
        source_files=source_list,
        subject=subject_slug,
        title=title,
        content=combined[:3000]  # token budget
    )

    response = ollama_generate(prompt, model=DISTILL_MODEL, timeout=120)
    if not response:
        log.error(f"Distillation failed for cluster '{subject_slug}'")
        return None

    # Ensure frontmatter is present
    if not response.startswith("---"):
        response = f"---\ncompiled_at: {now}\nsource_files: {source_list}\ntags: [distilled, {subject_slug}]\nstatus: experimental\n---\n\n" + response

    out = write_kb_entry(subject_slug, response)
    return out

# ── QUEUE PROCESSOR ───────────────────────────────────────────────────

class VaultQueue:
    def __init__(self):
        self.pending = []
        self._timer = None
        self._last_index = 0

    def add(self, path):
        """Add a new file to the queue, debounce processing."""
        if path not in self.pending:
            self.pending.append(path)
            log.info(f"Queued: {path.name} ({len(self.pending)} pending)")
        self._reset_timer()

    def _reset_timer(self):
        if self._timer:
            self._timer.cancel()
        self._timer = Timer(DEBOUNCE_SECS, self.process)
        self._timer.daemon = True
        self._timer.start()

    def process(self):
        """Process the queue if threshold is met."""
        if not self.pending:
            return

        # Only process files that still exist
        valid = [f for f in self.pending if f.exists()]
        if len(valid) < CLUSTER_THRESHOLD:
            log.info(f"Queue has {len(valid)} files — below threshold ({CLUSTER_THRESHOLD}), waiting.")
            self.pending = valid
            return

        log.info(f"Processing {len(valid)} queued files...")
        self.pending = []

        if not check_ollama():
            log.warning("Ollama is not running — distillation deferred. Files stay in Subconscious/.")
            return

        clusters = cluster_files(valid)
        distilled = []

        for subject, files in clusters.items():
            if len(files) < 1:
                continue
            out = distill_cluster(subject, files)
            if out:
                distilled.append(out)
                archive_files(files, reason=subject)

        if distilled:
            rebuild_index()
            log.info(f"Distillation complete. {len(distilled)} KB entries written.")
        else:
            log.warning("Distillation produced no output.")

    def process_all(self):
        """Force-process everything currently in Subconscious/."""
        if not SUBCONSCIOUS.exists():
            log.warning("Subconscious/ folder not found.")
            return
        files = [f for f in SUBCONSCIOUS.glob("*.md") if f.stat().st_size > 50]
        if not files:
            log.info("Subconscious/ is empty.")
            return
        log.info(f"Force processing {len(files)} files from Subconscious/...")
        self.pending = files
        self._debounce_secs_override = 0
        self.process()


queue = VaultQueue()

# ── WATCHDOG ──────────────────────────────────────────────────────────

def start_watcher():
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        log.error("watchdog not installed. Run: pip3 install watchdog --break-system-packages")
        sys.exit(1)

    class SubconsciousHandler(FileSystemEventHandler):
        def on_created(self, event):
            if not event.is_directory and event.src_path.endswith(".md"):
                p = Path(event.src_path)
                # Wait briefly for file to finish writing
                time.sleep(0.5)
                if p.exists() and p.stat().st_size > 50:
                    queue.add(p)

        def on_modified(self, event):
            if not event.is_directory and event.src_path.endswith(".md"):
                p = Path(event.src_path)
                if p.exists() and p.stat().st_size > 50:
                    queue.add(p)

    SUBCONSCIOUS.mkdir(parents=True, exist_ok=True)

    observer = Observer()
    observer.schedule(SubconsciousHandler(), str(SUBCONSCIOUS), recursive=False)
    observer.start()
    log.info(f"Watching {SUBCONSCIOUS} for new notes...")
    log.info(f"Threshold: {CLUSTER_THRESHOLD} files · Debounce: {DEBOUNCE_SECS}s · Model: {DISTILL_MODEL}")

    # Periodic index refresh
    def refresh_loop():
        while True:
            time.sleep(INDEX_REFRESH_SEC)
            try:
                rebuild_index()
                log.info("Periodic index refresh complete.")
            except Exception as e:
                log.warning(f"Index refresh failed: {e}")

    import threading
    t = threading.Thread(target=refresh_loop, daemon=True)
    t.start()

    def shutdown(sig, frame):
        log.info("Shutting down watcher...")
        observer.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        while observer.is_alive():
            observer.join(timeout=1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

# ── ENTRY POINT ───────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--once" in sys.argv:
        # Process whatever is queued, exit
        files = list(SUBCONSCIOUS.glob("*.md")) if SUBCONSCIOUS.exists() else []
        if files:
            for f in files:
                queue.add(f)
            queue.process()
        else:
            log.info("Nothing in Subconscious/ to process.")
    elif "--force" in sys.argv:
        # Distill everything regardless of threshold
        queue.process_all()
    else:
        # Persistent daemon
        start_watcher()
