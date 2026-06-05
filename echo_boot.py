#!/usr/bin/env python3
"""
echo_boot.py - Session Primer Generator
Reads Knowledge_Base/, builds a dense context block for pasting into new AI sessions.
Usage:
  python3 echo_boot.py           # generate primer
  python3 echo_boot.py --distill # run distiller first, then generate
"""
import os
import subprocess
from pathlib import Path

KB_DIR    = Path.home() / "Documents/ObsidianVault/Echo/Knowledge_Base"
DISTILLER = Path.home() / "vision_assistant/kb_distiller.py"


def run_distiller():
    print("Running KB Distiller...")
    result = subprocess.run(["python3", str(DISTILLER)], capture_output=True, text=True)
    print(result.stdout.strip())


def build_primer() -> str:
    if not KB_DIR.exists():
        return "[No Knowledge Base found]"

    files = sorted(KB_DIR.glob("*.md"), key=os.path.getmtime, reverse=True)[:6]
    if not files:
        return "[Knowledge Base is empty — run kb_distiller.py first]"

    primer = (
        "ECHO SESSION CONTEXT\n"
        "===================\n"
        "You are continuing work on Echo — a local-first AI cognitive OS on a ThinkPad T14s "
        "(Linux Mint 22.3, i7-10610U, 16GB RAM, Intel UHD iGPU).\n"
        "Apply the following distilled knowledge immediately. "
        "Do not re-explain basics. Work at senior engineer level.\n\n"
    )

    for fpath in files:
        raw = fpath.read_text(encoding="utf-8", errors="ignore")

        # Strip YAML frontmatter
        lines = raw.split("\n")
        body_lines = []
        in_front = False
        front_done = False
        for line in lines:
            if line.strip() == "---" and not front_done:
                in_front = not in_front
                if not in_front:
                    front_done = True
                continue
            if not in_front:
                body_lines.append(line)

        body = "\n".join(body_lines).strip()[:1200]
        primer += f"--- {fpath.stem} ---\n{body}\n\n"

    primer += (
        "===================\n"
        "Rules: privacy-first, offline by default, complete rewrites over partial patches, "
        "terminal commands separated from prose."
    )
    return primer


def copy_to_clipboard(text: str):
    try:
        subprocess.run(["xclip", "-selection", "clipboard"],
                       input=text.encode(), check=True)
        print("\n[Copied to clipboard]")
    except FileNotFoundError:
        print("\n[Install xclip for auto-copy: sudo apt install xclip]")
    except Exception:
        pass


if __name__ == "__main__":
    import sys
    if "--distill" in sys.argv:
        run_distiller()

    primer = build_primer()
    print("\n" + "=" * 60)
    print(primer)
    print("=" * 60)
    copy_to_clipboard(primer)
