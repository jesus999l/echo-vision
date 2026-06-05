#!/usr/bin/env python3
"""
scribe.py — Universal Conversation Importer
Place in: ~/vision_assistant/tools/scribe.py

Converts exported conversation history from ChatGPT, Claude, and Gemini
into Obsidian Markdown notes tagged for Echo's memory system.

Each conversation becomes a note in:
  ~/Documents/ObsidianVault/Echo/Conversations/

Tagged with #echo-memory so Echo's obsidian_bridge picks them up automatically.

Usage:
    python3 tools/scribe.py --source chatgpt --file ~/Downloads/conversations.json
    python3 tools/scribe.py --source claude  --file ~/Downloads/claude_export.json
    python3 tools/scribe.py --source gemini  --file ~/Downloads/Takeout/Gemini/...

Export instructions:
    ChatGPT: chatgpt.com → Settings → Data Controls → Export Data → conversations.json
    Claude:  claude.ai → Settings → Data & Privacy → Export → conversations.json
    Gemini:  takeout.google.com → Select "Gemini Apps Activity" → Download
"""

import json
import re
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger("echo.scribe")

# ── Config ────────────────────────────────────────────────────────────────────

VAULT_ROOT = Path.home() / "Documents" / "ObsidianVault"
CONV_FOLDER = VAULT_ROOT / "Echo" / "Conversations"

# Fallback if primary vault path not found
ALT_VAULT_ROOT = Path.home() / "Documents" / "EchoVault"
ALT_CONV_FOLDER = ALT_VAULT_ROOT / "Echo" / "Conversations"


def get_conv_folder() -> Path:
    if VAULT_ROOT.exists():
        CONV_FOLDER.mkdir(parents=True, exist_ok=True)
        return CONV_FOLDER
    if ALT_VAULT_ROOT.exists():
        ALT_CONV_FOLDER.mkdir(parents=True, exist_ok=True)
        return ALT_CONV_FOLDER
    # Create primary
    CONV_FOLDER.mkdir(parents=True, exist_ok=True)
    return CONV_FOLDER


# ── Filename utils ────────────────────────────────────────────────────────────

def safe_filename(title: str, max_len: int = 80) -> str:
    title = re.sub(r'[^\w\s\-]', '', title).strip()
    title = re.sub(r'\s+', '_', title)
    return title[:max_len] or "Untitled"


def unique_path(folder: Path, stem: str, ext: str = ".md") -> Path:
    p = folder / f"{stem}{ext}"
    if not p.exists():
        return p
    i = 2
    while (folder / f"{stem}_{i}{ext}").exists():
        i += 1
    return folder / f"{stem}_{i}{ext}"


# ── Frontmatter builder ───────────────────────────────────────────────────────

def frontmatter(title: str, source: str, date_str: str,
                extra_tags: list = None) -> str:
    tags = ["echo-memory", "imported", f"source-{source}"]
    if extra_tags:
        tags += extra_tags
    tag_str = ", ".join(tags)
    return (
        f"---\n"
        f"title: \"{title}\"\n"
        f"source: {source}\n"
        f"date: {date_str}\n"
        f"tags: [{tag_str}]\n"
        f"imported: {datetime.now().date()}\n"
        f"---\n\n"
    )


# ── ChatGPT parser ────────────────────────────────────────────────────────────

def parse_chatgpt(data: list) -> list:
    """
    ChatGPT export: list of conversation objects, each with a 'mapping' dict.
    mapping[id].message.content.parts[0] = message text
    """
    conversations = []

    for chat in data:
        title = chat.get("title") or "Untitled ChatGPT Chat"
        create_ts = chat.get("create_time") or 0
        date_str = datetime.fromtimestamp(create_ts).strftime("%Y-%m-%d") if create_ts else str(datetime.now().date())

        messages = []
        mapping = chat.get("mapping", {})

        # Build ordered message list by traversing parent → child chain
        # Find root (no parent or parent not in mapping)
        id_to_node = {nid: node for nid, node in mapping.items()}
        children_of = {}
        for nid, node in id_to_node.items():
            parent = node.get("parent")
            if parent:
                children_of.setdefault(parent, []).append(nid)

        roots = [nid for nid, node in id_to_node.items()
                 if not node.get("parent") or node.get("parent") not in id_to_node]

        def walk(nid, depth=0):
            node = id_to_node.get(nid)
            if not node:
                return
            msg = node.get("message")
            if msg:
                role = msg.get("author", {}).get("role", "unknown")
                content = msg.get("content", {})
                parts = content.get("parts", [])
                text = ""
                for part in parts:
                    if isinstance(part, str):
                        text += part
                    elif isinstance(part, dict) and part.get("type") == "text":
                        text += part.get("text", "")
                if text.strip() and role not in ("system", "tool"):
                    messages.append((role, text.strip()))
            for child in children_of.get(nid, []):
                walk(child, depth + 1)

        for root in roots:
            walk(root)

        if messages:
            conversations.append({
                "title": title,
                "date": date_str,
                "source": "chatgpt",
                "messages": messages,
            })

    return conversations


# ── Claude parser ─────────────────────────────────────────────────────────────

def parse_claude(data) -> list:
    """
    Claude export: list of conversation objects.
    Each has 'name' and 'chat_messages' list with 'sender' and 'text'.
    """
    conversations = []

    if isinstance(data, dict):
        # Single conversation export
        data = [data]

    for chat in data:
        title = chat.get("name") or chat.get("title") or "Untitled Claude Chat"

        # Date from first message or created_at
        created = chat.get("created_at") or ""
        if created:
            try:
                date_str = created[:10]
            except Exception:
                date_str = str(datetime.now().date())
        else:
            date_str = str(datetime.now().date())

        messages = []
        for msg in chat.get("chat_messages", []):
            sender = msg.get("sender", "unknown")
            # Claude exports: sender = "human" or "assistant"
            role = "user" if sender == "human" else "assistant"
            text = msg.get("text", "")
            if not text:
                # Some exports nest content
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text += block.get("text", "")
                elif isinstance(content, str):
                    text = content
            if text.strip():
                messages.append((role, text.strip()))

        if messages:
            conversations.append({
                "title": title,
                "date": date_str,
                "source": "claude",
                "messages": messages,
            })

    return conversations


# ── Gemini parser ─────────────────────────────────────────────────────────────

def parse_gemini(data) -> list:
    """
    Gemini (Google Takeout) export.
    Format varies — handles both the modern conversations array and
    the older activity-log style.
    """
    conversations = []

    if isinstance(data, dict):
        # Modern format: {"conversations": [...]}
        items = data.get("conversations", data.get("messages", [data]))
    elif isinstance(data, list):
        items = data
    else:
        items = [data]

    for i, chat in enumerate(items):
        title = chat.get("title") or chat.get("name") or f"Gemini Chat {i+1}"
        date_str = (chat.get("create_time") or chat.get("date") or
                    str(datetime.now().date()))[:10]

        messages = []

        # Modern Gemini format
        for msg in chat.get("messages", []):
            author = msg.get("author", {})
            role = "user" if author.get("role") == "user" else "assistant"
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    p.get("text", "") for p in content
                    if isinstance(p, dict)
                )
            if content.strip():
                messages.append((role, content.strip()))

        # Older activity-log style (just user queries)
        for activity in chat.get("userActivity", []):
            query = activity.get("query", "")
            response = activity.get("modelResponse", "")
            if query:
                messages.append(("user", query.strip()))
            if response:
                messages.append(("assistant", response.strip()))

        if messages:
            conversations.append({
                "title": title,
                "date": date_str,
                "source": "gemini",
                "messages": messages,
            })

    return conversations


# ── Markdown renderer ─────────────────────────────────────────────────────────

def render_markdown(conv: dict) -> str:
    fm = frontmatter(conv["title"], conv["source"], conv["date"])
    lines = [fm, f"# {conv['title']}\n"]

    for role, text in conv["messages"]:
        label = "USER" if role == "user" else "ECHO" if role == "assistant" else role.upper()
        # Truncate very long messages to keep notes readable
        if len(text) > 3000:
            text = text[:3000] + "\n\n*[truncated — full text in original export]*"
        lines.append(f"## {label}\n\n{text}\n")

    lines.append("\n---\n\n*Imported by Echo Scribe*\n")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def run_scribe(source: str, file_path: str):
    fp = Path(file_path).expanduser()
    if not fp.exists():
        logger.error(f"File not found: {fp}")
        sys.exit(1)

    logger.info(f"Loading {fp} ...")
    with open(fp, "r", encoding="utf-8") as f:
        data = json.load(f)

    logger.info(f"Parsing as {source} ...")
    parsers = {
        "chatgpt": parse_chatgpt,
        "claude":  parse_claude,
        "gemini":  parse_gemini,
    }
    if source not in parsers:
        logger.error(f"Unknown source '{source}'. Use: chatgpt, claude, gemini")
        sys.exit(1)

    conversations = parsers[source](data)
    logger.info(f"Found {len(conversations)} conversations.")

    if not conversations:
        logger.warning("No conversations parsed. Check the file format.")
        return

    folder = get_conv_folder()
    logger.info(f"Writing to: {folder}")

    written = 0
    skipped = 0
    for conv in conversations:
        stem = f"{conv['date']}_{safe_filename(conv['title'])}"
        out_path = unique_path(folder, stem)
        try:
            out_path.write_text(render_markdown(conv), encoding="utf-8")
            written += 1
        except Exception as e:
            logger.warning(f"Failed to write {stem}: {e}")
            skipped += 1

    print(f"\n✅ Done: {written} conversations imported → {folder}")
    if skipped:
        print(f"⚠️  {skipped} skipped (write errors)")
    print(f"\nEcho will ingest these on next startup via obsidian_bridge (#echo-memory tag).")
    print("Or trigger manually: restart Echo desktop app.")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import conversation history into Echo's Obsidian vault"
    )
    parser.add_argument(
        "--source",
        choices=["chatgpt", "claude", "gemini"],
        required=True,
        help="Export format",
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to exported JSON file",
    )
    args = parser.parse_args()
    run_scribe(args.source, args.file)
