#!/usr/bin/env python3
"""
vault_organizer.py — Echo Vault Cleaner + Node Connector
Run: python3 ~/vision_assistant/vault_organizer.py

Does:
1. Merges the fragmented Archive/plans_merged_2026-05-20/ (each line = own file → one doc)
2. Connects notes with [[wikilinks]] using AI suggestions
3. Updates INDEX.md with full map of content
4. Moves old 'obsidian Echo brain' notes into Echo/ structure
5. Creates a knowledge graph showing connections
"""
import os, re, json, shutil, urllib.request
from pathlib import Path
from datetime import datetime
from collections import defaultdict

VAULT = Path("/home/jesus999l/Documents/ObsidianVault")
ECHO  = VAULT / "Echo"
ARCHIVE = ECHO / "Archive"
OLD_BRAIN = VAULT / "obsidian Echo brain"
PROXIMA = "http://localhost:3210"

ok  = lambda s: print(f"  \033[32m✓\033[0m  {s}")
wrn = lambda s: print(f"  \033[33m⚠\033[0m  {s}")
hdr = lambda s: print(f"\n\033[34m══ {s} ══\033[0m")

# ── 1. MERGE FRAGMENTED ARCHIVE ───────────────────────────────────────────────
hdr("1. Merging fragmented archive")

frag_dir = ARCHIVE / "plans_merged_2026-05-20"
if frag_dir.exists():
    files = sorted(frag_dir.glob("*.md"))
    if files:
        # Group by timestamp prefix (same minute = same document)
        groups = defaultdict(list)
        for f in files:
            # Extract date-time prefix: 2026-05-20_14-22
            m = re.match(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2})', f.name)
            key = m.group(1) if m else "misc"
            # Strip the timestamp prefix + underscores from content
            content = re.sub(r'^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}_', '', f.stem)
            content = content.replace('-', ' ').replace('_', ' ')
            groups[key].append((f.stem, content))

        # Build merged documents grouped by rough topic
        merged_docs = defaultdict(list)
        for key, items in sorted(groups.items()):
            for stem, content in items:
                merged_docs[key[:10]].append(content)  # group by date

        # Write merged files
        merged_dir = ARCHIVE / "plans_2026-05-20_merged"
        merged_dir.mkdir(exist_ok=True)

        for date_key, lines in merged_docs.items():
            out = merged_dir / f"{date_key}_echo-plan-merged.md"
            # Reconstruct as proper markdown
            text = f"# Echo Plan — {date_key}\n*Merged from {len(lines)} fragments*\n\n"
            # Try to detect structure (headers start with #, code blocks with ```)
            current_section = []
            for line in lines:
                line = line.strip()
                if not line or line == '---': continue
                if re.match(r'^#{1,3}\s', line) or re.match(r'^[A-Z][^a-z]{0,3}[A-Z]', line):
                    if current_section:
                        text += " ".join(current_section) + "\n\n"
                        current_section = []
                    text += f"{line}\n"
                elif line.startswith('*') or line.startswith('-'):
                    if current_section:
                        text += " ".join(current_section) + "\n\n"
                        current_section = []
                    text += f"{line}\n"
                else:
                    current_section.append(line)
            if current_section:
                text += " ".join(current_section) + "\n"

            out.write_text(text)
            ok(f"Merged {len(lines)} fragments → {out.name}")

        # Archive the old fragmented files
        old_frags = ARCHIVE / "plans_fragments_raw"
        old_frags.mkdir(exist_ok=True)
        for f in files:
            shutil.move(str(f), str(old_frags / f.name))
        ok(f"Moved {len(files)} fragments to plans_fragments_raw/")
        try: frag_dir.rmdir()
        except: pass
else:
    wrn("plans_merged_2026-05-20 not found — already cleaned?")

# ── 2. MIGRATE OLD BRAIN NOTES ────────────────────────────────────────────────
hdr("2. Migrating 'obsidian Echo brain' → Echo/Origins/")

if OLD_BRAIN.exists():
    origins = ECHO / "Origins"
    origins.mkdir(exist_ok=True)
    old_files = list(OLD_BRAIN.rglob("*.md"))
    migrated = 0
    for f in old_files:
        # Build relative path under Origins/
        rel = f.relative_to(OLD_BRAIN)
        dest = origins / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(str(f), str(dest))
            migrated += 1
    ok(f"Migrated {migrated} notes from ECHO v1 → Echo/Origins/")
else:
    ok("Old brain already migrated or not found")

# ── 3. BUILD KNOWLEDGE INDEX ──────────────────────────────────────────────────
hdr("3. Building knowledge index")

all_notes = list(ECHO.rglob("*.md"))
all_notes = [n for n in all_notes
             if "plans_fragments_raw" not in str(n)
             and ".trash" not in str(n)]

ok(f"Found {len(all_notes)} notes total")

# Extract titles and key terms from each note
note_data = []
for note in all_notes:
    try:
        content = note.read_text(errors='ignore')
        title = note.stem.replace('-', ' ').replace('_', ' ')
        # Extract first heading if available
        hm = re.search(r'^#{1,3}\s+(.+)$', content, re.MULTILINE)
        if hm: title = hm.group(1)
        # Extract key terms (capitalized words, technical terms)
        terms = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*|echo|proxima|hermes|obsidian|vault|AI|API)\b', content[:500], re.I)
        terms = list(set(t.lower() for t in terms if len(t) > 3))[:10]
        note_data.append({
            "path": note,
            "rel":  str(note.relative_to(VAULT)),
            "title": title,
            "terms": terms,
            "size": len(content),
        })
    except: pass

# ── 4. ADD WIKILINKS TO NOTES ─────────────────────────────────────────────────
hdr("4. Connecting notes with [[wikilinks]]")

def find_related(note_info, all_notes_data, top_n=5):
    """Find related notes by shared terms."""
    scores = {}
    my_terms = set(note_info["terms"])
    for other in all_notes_data:
        if other["path"] == note_info["path"]: continue
        shared = my_terms & set(other["terms"])
        if shared:
            scores[other["title"]] = len(shared)
    return sorted(scores.items(), key=lambda x: -x[1])[:top_n]

linked_count = 0
for nd in note_data:
    if nd["size"] < 100: continue  # skip tiny notes
    try:
        content = nd["path"].read_text(errors='ignore')
        if "## Related" in content or "## See Also" in content:
            continue  # already has links

        related = find_related(nd, note_data)
        if not related: continue

        links = "\n".join(f"- [[{title}]]" for title, score in related)
        footer = f"\n\n---\n## Related\n{links}\n\n*tags: echo auto-linked*\n"

        nd["path"].write_text(content.rstrip() + footer)
        linked_count += 1
    except: pass

ok(f"Added wikilinks to {linked_count} notes")

# ── 5. UPDATE INDEX.md ────────────────────────────────────────────────────────
hdr("5. Updating INDEX.md")

# Group by folder
by_folder = defaultdict(list)
for nd in note_data:
    folder = nd["path"].parent.name
    by_folder[folder].append(nd)

index_content = f"""# Echo Knowledge Base Index
*Auto-generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · {len(note_data)} notes*

## Structure

"""

FOLDER_DESC = {
    "Daily":          "Daily logs and reflections",
    "Conversations":  "AI conversation archives",
    "Knowledge_Base": "Core system knowledge",
    "Plans":          "Project plans and blueprints",
    "Archive":        "Processed historical records",
    "Research":       "Research and exploration",
    "Subconscious":   "Background research loop outputs",
    "Briefings":      "Daily briefings",
    "Cognition":      "Reasoning and cognitive traces",
    "Tasks":          "Task lists",
    "Habits":         "Habit tracking",
    "Origins":        "ECHO v1 foundation notes",
    "Insights":       "Extracted insights from pipeline",
}

for folder, notes in sorted(by_folder.items()):
    desc = FOLDER_DESC.get(folder, "")
    index_content += f"### {folder}\n"
    if desc: index_content += f"*{desc}*\n"
    # Show recent 8 notes
    recent = sorted(notes, key=lambda n: n["path"].stat().st_mtime, reverse=True)[:8]
    for n in recent:
        index_content += f"- [[{n['title']}]]\n"
    if len(notes) > 8:
        index_content += f"- *...and {len(notes)-8} more*\n"
    index_content += "\n"

index_content += f"""## Quick Links
- [[echo-system-state]] — Current system status
- [[echo_project_state]] — Project overview
- [[echo_system_breakdown]] — Architecture

## Pipeline Outputs
- [[Echo/Plans/INDEX]] — All plans
- [[Echo/Insights/]] — AI-generated insights
- [[Echo/Research/]] — Research loop outputs

---
*Generated by vault_organizer.py · [[Echo/Knowledge_Base/echo-system-state]]*
"""

idx = ECHO / "INDEX.md"
idx.write_text(index_content)
ok(f"INDEX.md updated ({len(note_data)} notes indexed)")

# ── 6. USE AI TO SUGGEST DEEPER CONNECTIONS ──────────────────────────────────
hdr("6. AI-powered connection suggestions")

def ask_proxima(message, model="chatgpt"):
    try:
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": message}]
        }).encode()
        req = urllib.request.Request(
            f"{PROXIMA}/v1/chat/completions", data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]
    except Exception as e:
        return f"(unavailable: {e})"

# Summarize vault structure for AI analysis
vault_summary = f"""Obsidian vault for 'Echo' AI assistant project.
Folders: {', '.join(by_folder.keys())}
Total notes: {len(note_data)}
Key topics found: echo system, proxima bridge, hermes agent, obsidian integration,
android app, vision assistant, AI pipeline, research loop, vault watcher.

Recent notes:
""" + "\n".join(f"- {nd['title']}" for nd in
    sorted(note_data, key=lambda n: n['path'].stat().st_mtime, reverse=True)[:15])

prompt = f"""Given this Obsidian vault structure for an AI assistant project:

{vault_summary}

Suggest:
1. The 5 most important missing connections between existing notes
2. 3 new notes that should be created to bridge gaps
3. How to reorganize for better knowledge flow

Be specific with note titles. Use [[wikilink]] format."""

wrn("Asking AI for connection suggestions (this may take 30s)...")
suggestions = ask_proxima(prompt, model="chatgpt")

# Save suggestions as a new note
suggestions_note = ECHO / "Knowledge_Base" / f"vault-connections-{datetime.now().strftime('%Y-%m-%d')}.md"
suggestions_note.write_text(f"""# Vault Connection Suggestions
*{datetime.now().strftime('%Y-%m-%d %H:%M')} · Generated by vault_organizer.py*

## AI Analysis (ChatGPT)

{suggestions}

---
## Related
- [[echo-system-state]]
- [[INDEX]]

tags: echo vault-organization auto-generated
""")
ok(f"AI suggestions saved → {suggestions_note.name}")

# ── SUMMARY ───────────────────────────────────────────────────────────────────
hdr("Done")
print(f"""
  Notes indexed:    {len(note_data)}
  Notes linked:     {linked_count}
  INDEX.md updated: ✓
  Old brain migrated: ✓
  AI suggestions: Echo/Knowledge_Base/vault-connections-*.md

  Open Obsidian → Graph View to see all connections
""")
