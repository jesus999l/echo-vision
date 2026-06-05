#!/usr/bin/env python3
"""
Echo KB Distiller
Scans Cognition/ (or a specified folder), distills each file via local Ollama,
writes clean KB entries to Knowledge_Base/, archives originals to Archive/.
"""

import os
import sys
import json
import shutil
import datetime
import urllib.request
import urllib.error
from pathlib import Path

# --- CONFIG ---
VAULT = Path.home() / "Documents/ObsidianVault/Echo"
INPUT_DIR  = VAULT / "Cognition"
KB_DIR     = VAULT / "Knowledge_Base"
ARCHIVE_DIR= VAULT / "Archive"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL      = "qwen2.5:0.5b"          # fast, low overhead on Intel iGPU
MIN_WORDS  = 50                   # skip files shorter than this

SYSTEM_PROMPT = """You are Echo's Knowledge Base Distiller.
Convert raw notes into a canonical KB entry. Be concise and factual.

Output ONLY this markdown structure — no preamble, no commentary:

# [Topic Title]

## What Works
- [concrete finding or confirmed fact]

## What Failed
- [what was tried and why it didn't work — omit section if nothing failed]

## Rules
- [behavioral constraint or architectural decision]

## Current Status
[one sentence]

Strip: all greetings, conversational filler, AI pleasantries, repetition, terminal noise.
Keep: decisions made, constraints agreed on, code facts, failures worth remembering."""


# --- OLLAMA ---

def call_ollama(content: str, source_name: str) -> str | None:
    prompt = f"Distill the following raw note into a Knowledge Base entry.\nSource: {source_name}\n\n---\n{content[:6000]}\n---"
    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "system": SYSTEM_PROMPT,
        "stream": False,
        "options": {"temperature": 0.1}
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())
            return data.get("response", "").strip()
    except urllib.error.URLError as e:
        print(f"  [ERROR] Ollama unreachable: {e}")
        return None
    except Exception as e:
        print(f"  [ERROR] LLM call failed: {e}")
        return None


# --- FILE OPS ---

def ensure_dirs():
    for d in [INPUT_DIR, KB_DIR, ARCHIVE_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def kb_path_for(source: Path) -> Path:
    slug = source.stem.lower().replace(" ", "-")
    return KB_DIR / f"{slug}.md"


def write_kb_entry(path: Path, distilled: str, source_name: str):
    header = (
        f"---\n"
        f"compiled_at: {datetime.datetime.now().isoformat()}\n"
        f"source_files: [{source_name}]\n"
        f"tags: [distilled, knowledge_base]\n"
        f"status: stable\n"
        f"---\n\n"
    )
    path.write_text(header + distilled, encoding="utf-8")


def archive(source: Path):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = ARCHIVE_DIR / f"{ts}_{source.name}"
    shutil.move(str(source), str(dest))


# --- PIPELINE ---

def process_file(path: Path) -> bool:
    print(f"\n  Distilling: {path.name}")

    raw = path.read_text(encoding="utf-8", errors="ignore")
    word_count = len(raw.split())

    if word_count < MIN_WORDS:
        print(f"  [SKIP] Under {MIN_WORDS} words ({word_count}). File left in place.")
        return False

    kb = kb_path_for(path)

    # If KB entry already exists, merge
    if kb.exists():
        print(f"  Existing KB entry found — merging...")
        existing = kb.read_text(encoding="utf-8")
        merge_prompt = (
            f"Merge these two KB entries on the same topic into one canonical record. "
            f"No duplicates. Keep highest-signal facts from both.\n\n"
            f"=== EXISTING ===\n{existing[:3000]}\n\n"
            f"=== NEW ===\n{raw[:3000]}"
        )
        distilled = call_ollama(merge_prompt, path.name)
    else:
        distilled = call_ollama(raw, path.name)

    if not distilled:
        print(f"  [ERROR] No output from Ollama. File left in place.")
        return False

    write_kb_entry(kb, distilled, path.name)
    archive(path)
    print(f"  Done -> {kb.name}")
    return True


def run(target_dir: Path = INPUT_DIR):
    ensure_dirs()

    files = sorted(list(target_dir.glob("*.md")) + list(target_dir.glob("*.txt")))

    if not files:
        print(f"No files found in {target_dir}")
        return

    print(f"KB Distiller — {len(files)} file(s) found in {target_dir.name}/")
    print(f"Model: {MODEL}")

    processed = 0
    skipped = 0
    failed = 0

    for f in files:
        result = process_file(f)
        if result is True:
            processed += 1
        elif result is False and len(f.read_text(encoding="utf-8").split()) < MIN_WORDS:
            skipped += 1
        else:
            failed += 1

    print(f"\nDone. Processed: {processed}  Skipped: {skipped}  Failed: {failed}")


# --- ENTRY POINT ---

if __name__ == "__main__":
    # Optional: pass a folder as argument, e.g. python3 kb_distiller.py Research
    if len(sys.argv) > 1:
        folder = VAULT / sys.argv[1]
        if not folder.exists():
            print(f"Folder not found: {folder}")
            sys.exit(1)
        run(folder)
    else:
        run()
