# Echo — Full Cursor Context
generated: 2026-06-03 (updated end-of-session)
purpose: Give any AI (Cursor, Claude, GPT) full context to work on Echo autonomously

---

## The Project In One Sentence
Echo is a local-first AI operating system on a ThinkPad T14s — voice, memory, search, vault, automation, multi-surface (desktop/mobile/TV/Discord) — built to get smarter every session because it actually remembers.

---

## Machine
- ThinkPad T14s Gen 1, i7-10610U, 16GB RAM, CPU-only (no GPU)
- Linux Mint 22.3, zsh
- User: jesus999l, home: /home/jesus999l
- IP: 192.168.4.46 (Tailscale also active)
- Python env: `/home/jesus999l/vision_env` (NOT system python, NOT .venv)
- Shell rule: NEVER mix prose and commands. Commands in fenced blocks only.

---

## Canonical Entry Points (The Spine)

| File | Role |
|---|---|
| main.py | Boot orchestrator — starts all daemons, Tk UI, IPC |
| ui.py | Full desktop UI (~3k lines) — chat, calendar, habits, themes |
| ai.py | AI routing — Proxima → Ollama fallback, search + KB injection |
| memory.py | SQLite interface — tasks/habits/journal/calendar/messages |
| config.py | All paths, URLs, model names (`DB_PATH` → memory.db) |
| personality.py | Mood trends, habit streaks, personality context builder |

Everything else is a plugin.

---

## AI Pipeline

```
User types/speaks
    ↓
ask() in ai.py
    ↓
Try Proxima :3210 (ChatGPT/Claude/Gemini/Perplexity via browser sessions)
    ↓ if Connection refused →
_ask_text() with:
  - build_context()        ← memory + KB (Chroma/keyword) + recent messages
  - search_local()         ← SQLite tasks/habits/journal/calendar
  - search_if_needed()     ← SearXNG web search
  - build_system_prompt()  ← personality + calendar + goals + ai_guidelines
    ↓
Ollama :11434 → qwen2.5:0.5b (default) or gemma3n-local:latest
    ↓
parse_and_execute_actions() ← <action> blocks
    ↓
save_message() → memory.db
```

---

## Ollama Models (current)
| Model | Role |
|---|---|
| qwen2.5:0.5b | Default fast chat |
| gemma3n-local:latest | Deep local (4.2GB GGUF) |
| nomic-embed-text | Chroma embeddings (pull if sync fails) |

---

## Services & Ports

| Service | Port | Start |
|---|---|---|
| Ollama | 11434 | auto |
| SearXNG (Docker) | 8081 | docker start searxng |
| Proxima (npm) | 3210 | `cd ~/Proxima && npm start &` |
| echo_proxima_native | 3210/3211 | `python3 echo_proxima_native.py` |
| Echo browser server | 59996 | `nohup python3 echo_browser_server.py ...` |
| Echo REST API | 8765 | `nohup python3 echo_rest.py ...` |
| Echo task manager | 7799 | `nohup python3 echo_task_manager.py ...` |
| Group chat | 8484 | `nohup python3 echo_group_chat_server.py ...` |

Logs: `/tmp/echo_rest.log`, `/tmp/echo_tv.log`, `/tmp/echo_tasks.log`

---

## Vault Structure

```
~/Documents/ObsidianVault/Echo/
├── Subconscious/      ← DROP FILES HERE (watcher distills to KB)
├── Knowledge_Base/    ← canonical truth (never write directly)
├── Cognition/         ← plans, architecture
├── Conversations/     ← exported AI logs
├── Research/          ← SearXNG outputs
└── Archive/           ← processed originals
```

**Rule:** Write to Subconscious/ only. Watcher → Knowledge_Base/.

---

## Database
- **Canonical:** `~/vision_assistant/memory.db` (`config.DB_PATH`)
- **Do not use:** `echo.db` (removed — was accidental import target)
- Calendar: 317 events in memory.db (Google Takeout + Echo auto-entries)

---

## Fixed This Session (2026-06-03)
1. guidelines bug — `build_system_prompt()` loads `ai_guidelines` from settings.json
2. Web + local search wired in `_ask_text()`
3. KB context wired in `build_context()` via `echo_kb_context`
4. Model strings updated (config, browser server, proxima_native, multi_model, ui)
5. echo_rest.py on :8765
6. echo_deploy_package: 698 Subconscious files, 142 calendar via deploy script
7. gemma3n-local + qwen2.5:0.5b in Ollama
8. Phantom echo.db removed; calendar import script at `scripts/import_google_calendar.py`

---

## Known Issues / Next

| # | Item | Notes |
|---|---|---|
| 1 | Chroma sync | Requires `ollama pull nomic-embed-text` then `chroma_adapter.py --sync` |
| 2 | Proxima at boot | Add `cd ~/Proxima && npm start &` to `~/start-echo.sh` |
| 3 | drift_panel wlrctl | Use `wlrctl toplevel focus title:X`; xdotool for XWayland |
| 4 | Subconscious backlog | 698 files need kb-distiller pass |
| 5 | Disk | ~20GB free on / — audit Google_Takeout (7GB) when imports confirmed |

---

## Architecture Constraints
1. Claude is last resort — exhaust Proxima first
2. Always `~/vision_env/bin/python3`
3. No `while True` without SIGTERM + clean shutdown
4. Server pattern: `nohup ... </dev/null >> logfile 2>&1 & disown`
5. Vault writes → Subconscious/ only
6. Research commands → `echo_safety.py`; kill file `~/.echo_kill`

---

## REST API (:8765)
```
GET  /ping, /status, /tasks, /briefing, /kb?q=
POST /chat {"message":"..."}
POST /tasks {"title":"..."}
```

---

## Chroma
```zsh
ollama pull nomic-embed-text
~/vision_env/bin/python3 ~/vision_assistant/chroma_adapter.py --sync
```

---

## Related docs
- `~/Documents/ObsidianVault/main-repo/echo_session_2026-06-03.md`
- `~/.cursorrules` (short rules)
