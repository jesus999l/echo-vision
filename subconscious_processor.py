#!/usr/bin/env python3
"""
subconscious_processor.py — Subconscious Mind Engine
Processes raw interactions, sorts entries, and organizes Obsidian files using local Ollama.
"""
import json, urllib.request, pathlib, datetime

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
LOCAL_MODEL = "qwen3:4b"
VAULT_DIR = pathlib.Path("~/Documents/ObsidianVault/Echo/Subconscious").expanduser()

def query_local_brain(prompt_text):
    payload = json.dumps({
        "model": LOCAL_MODEL,
        "prompt": prompt_text,
        "stream": False,
        "options": {"temperature": 0.3}
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw_response = json.loads(r.read().decode('utf-8'))
            return raw_response.get("response", "").strip()
    except Exception as e:
        print(f"[Subconscious Error] Local brain cycle failed: {e}")
        return None

def process_vault_maintenance():
    print("[Subconscious] Initiating data cleanup and context structuring cycle...")
    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    active_log = VAULT_DIR / f"{date_str}-voice.md"
    if not active_log.exists():
        print("[Subconscious] Vault clear. No raw data packets to process right now.")
        return
    raw_text = active_log.read_text()
    cleanup_prompt = f"""You are the subconscious data manager of the Echo AI architecture.
Analyze the following raw transaction notes from today's interactions. Clean up any broken lines, organize formatting, group ideas together logically, and extract active links or design references into clear sections.

Raw Data:
{raw_text}"""
    refined_output = query_local_brain(cleanup_prompt)
    if refined_output:
        structured_file = VAULT_DIR / f"{date_str}-structured_memory.md"
        structured_file.parent.mkdir(parents=True, exist_ok=True)
        structured_file.write_text(refined_output)
        print(f"✓ [Subconscious] Memory consolidated successfully into: {structured_file.name}")

if __name__ == "__main__":
    process_vault_maintenance()
