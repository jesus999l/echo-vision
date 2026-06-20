#!/usr/bin/env python3
"""
echo_repos_bar.py — Waybar module showing cloned repos
Click cycles focus or launches a repo picker
"""
import subprocess, json, sys, os
from pathlib import Path

REPOS_DIR = Path.home() / "repos"

REPO_ICONS = {
    "turbovec": "⚡", "mcpify": "🔌", "iptv": "📺",
    "VibeVoice": "🎙", "StoryGen-Atelier": "🎬",
    "ObserverAI": "👁", "OpenCut": "✂", "Wan2GP": "🎥",
    "dexter": "📈", "tiny-world-builder": "🌍",
    "docker-android": "🤖", "waybar-src": "📊",
    "cultivation-world-simulator": "🌱", "modly": "🧊",
    "LongLive": "🎞", "default": "📦",
}

STATE_FILE = "/tmp/echo_repos_state.json"

def get_repos():
    if not REPOS_DIR.exists():
        return []
    repos = []
    for d in sorted(REPOS_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            repos.append(d.name)
    return repos

def get_icon(name):
    for k, v in REPO_ICONS.items():
        if k.lower() in name.lower():
            return v
    return REPO_ICONS["default"]

def load_state():
    try: return json.load(open(STATE_FILE))
    except: return {"idx": 0}

def save_state(s):
    try: json.dump(s, open(STATE_FILE, "w"))
    except: pass

if len(sys.argv) > 1 and sys.argv[1] == "click":
    repos = get_repos()
    if not repos:
        sys.exit(0)
    s = load_state()
    idx = s.get("idx", 0) % len(repos)
    repo = repos[idx]
    repo_path = REPOS_DIR / repo
    # Open file manager at repo path
    subprocess.Popen(["nemo", str(repo_path)], start_new_session=True)
    s["idx"] = (idx + 1) % len(repos)
    save_state(s)
    sys.exit(0)

repos = get_repos()
if not repos:
    print(json.dumps({"text": "", "tooltip": "No repos"}))
    sys.exit(0)

count = len(repos)
# Show first 3 icons
icons = [get_icon(r) for r in repos[:3]]
text = "".join(icons) + (f"<sup>+{count-3}</sup>" if count > 3 else "")

tip_lines = [f"📦 Repos ({count}) — click to browse"]
for r in repos:
    icon = get_icon(r)
    tip_lines.append(f"  {icon} {r}")

print(json.dumps({
    "text": text,
    "tooltip": "\n".join(tip_lines)
}))
sys.exit(0)
