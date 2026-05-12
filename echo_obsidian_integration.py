"""
echo_obsidian_integration.py
────────────────────────────────────────────────────────────────────────
This file is NOT a standalone script.
It shows the EXACT lines to add to your main Echo desktop application.

Search for the anchor comments (e.g. "# [ANCHOR: IMPORTS]") in your
existing file, then insert the blocks marked INSERT BELOW / INSERT ABOVE.

The file likely lives at:
  ~/vision_assistant/vision_assistant.py   (or similar main file)
────────────────────────────────────────────────────────────────────────
"""


# ============================================================================
# BLOCK 1 — Add near the top with your other imports
# ============================================================================

# [ANCHOR: IMPORTS]  ← find your existing imports section
# INSERT BELOW ↓
from obsidian_bridge import ObsidianBridge, ObsidianNote
# INSERT ABOVE ↑


# ============================================================================
# BLOCK 2 — Add inside your EchoApp __init__ (or wherever Echo initialises)
# ============================================================================

# [ANCHOR: __init__ / startup]
# Find the line where you set up your database, AI client, etc. Add BELOW it:

# INSERT BELOW ↓
        # ── Obsidian bridge ──────────────────────────────────────────────
        self.obsidian = ObsidianBridge(
            config_path      = "obsidian_config.json",
            on_note_ingested = self._on_vault_note_ingested,
            on_daily_summary = self._on_daily_summary_time,
        )
        self.obsidian.start()
# INSERT ABOVE ↑


# ============================================================================
# BLOCK 3 — Vault note ingestion callback
#
# Add this as a METHOD of your EchoApp class (or whatever your main class is).
# It fires whenever a user saves a tagged note in Obsidian.
# ============================================================================

    def _on_vault_note_ingested(self, note: ObsidianNote):
        """Called when the vault watcher detects a new/updated tagged note."""

        # --- #echo-task → import as Echo task --------------------------------
        if note.has_tag("echo-task"):
            title    = note.title
            priority = note.frontmatter.get("priority", "normal")
            # Use your existing task-creation method here:
            # self.db_add_task(title=title, priority=priority)
            # self.refresh_task_list()
            self.speak(f"New task imported from Obsidian: {title}")

        # --- #echo-journal → import as journal entry -------------------------
        if note.has_tag("echo-journal"):
            entry = note.excerpt(600)
            # self.db_add_journal_entry(text=entry, source="obsidian")
            self.speak("Obsidian journal entry synced.")

        # --- #jules-task → log it (Jules pipeline step 5 will auto-dispatch) -
        if note.has_tag("jules-task"):
            self.speak(f"Jules task noted: {note.title}")

        # --- Refresh AI context regardless of tag ----------------------------
        # The bridge already added the note to its pool.
        # Nothing extra needed — get_context_for_query() will pick it up.


# ============================================================================
# BLOCK 4 — Daily summary callback
#
# Add this as a METHOD of your EchoApp class.
# Fires at the time set in obsidian_config.json (default 23:30).
# ============================================================================

    def _on_daily_summary_time(self):
        """
        Triggered by the ObsidianBridge scheduler at daily_summary_time.
        Pulls today's completed tasks and habits from Echo's DB, asks the
        AI to summarise the day, then writes it all to the vault.
        """
        import threading
        threading.Thread(target=self._write_daily_summary_async, daemon=True).start()

    def _write_daily_summary_async(self):
        # --- Pull today's data from Echo's existing DB -----------------------
        # Replace these with your real DB calls:
        # tasks_done = self.db_get_tasks_completed_today()       → list of str
        # habit_map  = self.db_get_habit_status_today()          → dict{name: bool}
        # journal    = self.db_get_journal_entries_today()        → list of str
        tasks_done = []   # TODO: wire to your DB
        habit_map  = {}   # TODO: wire to your DB
        journal    = []   # TODO: wire to your DB

        # --- Build an AI summary via your existing streaming call ------------
        prompt = (
            "Write a concise end-of-day summary for my Obsidian vault. "
            "Today's completed tasks: " + (", ".join(tasks_done) or "none") + ". "
            "Journal entries: " + (" | ".join(journal[:3]) or "none") + ". "
            "Keep it under 150 words. Plain text, no markdown headers."
        )
        # Use your existing AI call — this is a sketch, adapt to your streaming API:
        # summary = self.ai_complete(prompt)
        summary = f"Day summary generated at {__import__('datetime').datetime.now().strftime('%H:%M')}."

        # --- Write to vault --------------------------------------------------
        self.obsidian.log_daily_summary(
            summary    = summary,
            tasks_done = tasks_done,
            habits     = habit_map,
        )

        # Also snapshot Echo's system status for the Neocities publisher later
        self.obsidian.log_status_snapshot({
            "tasks completed today": len(tasks_done),
            "habits logged":         len(habit_map),
            "AI model":              "ollama/gemma3",
            "uptime":                "ok",
        })


# ============================================================================
# BLOCK 5 — Inject vault context into AI system prompt
#
# Find wherever you BUILD your AI system prompt (the guidelines injection
# you already have). Add vault context right after your existing guidelines.
# ============================================================================

# EXISTING CODE (reference — find this pattern in your file):
#
#   system_prompt = self.ai_guidelines   # or however you build it
#   response = ollama.chat(model=..., messages=[{"role":"system", "content": system_prompt}, ...])
#
# CHANGE TO:

        # ── Vault context injection ──────────────────────────────────────
        vault_ctx = self.obsidian.get_context_for_query(user_message)
        if vault_ctx:
            system_prompt = self.ai_guidelines + "\n\n" + vault_ctx
        else:
            system_prompt = self.ai_guidelines
        # ── end vault context ────────────────────────────────────────────

        # Then pass system_prompt to your existing Ollama / Claude call as normal.


# ============================================================================
# BLOCK 6 — Hook habit completion
#
# Find wherever you mark a habit as complete (your existing habit logic).
# Add ONE LINE after your DB update:
# ============================================================================

        # After your existing habit completion code:
        self.obsidian.log_habit(
            name      = habit_name,     # str — use your variable
            completed = True,
            streak    = habit_streak,   # int — use your variable
        )


# ============================================================================
# BLOCK 7 — Hook task completion
#
# Find wherever you mark a task as done. Add ONE LINE:
# ============================================================================

        # After your existing task completion code:
        self.obsidian.log_task(
            title    = task_title,      # str — use your variable
            status   = "done",
            priority = task_priority,   # str — use your variable
        )


# ============================================================================
# BLOCK 8 — Hook morning briefing
#
# Find your existing morning_briefing() method.
# After you generate and speak the briefing text, add:
# ============================================================================

        # Pull recent user notes to enrich the briefing context
        recent = self.obsidian.get_recent_user_notes(days=1)
        if recent:
            titles = ", ".join(n.title for n in recent[:4])
            briefing_text += f"\n\nYou updated these notes in Obsidian yesterday: {titles}."

        # After generating briefing_text, write it to vault:
        self.obsidian.log_morning_briefing(briefing_text)


# ============================================================================
# BLOCK 9 — Shutdown hook
#
# Find wherever Echo shuts down (window close / on_closing / cleanup).
# Add:
# ============================================================================

        self.obsidian.stop()


# ============================================================================
# BLOCK 10 — Voice command: "queue Jules task"
#
# Add to your intent/command dispatcher — wherever you parse user speech
# for actions like "add task", "set timer", etc.
# ============================================================================

        # Example intent match (adapt to however you detect commands):
        if "jules task" in user_message.lower() or "queue task for jules" in user_message.lower():
            # Extract task description from the rest of the utterance,
            # or ask Echo to prompt for a description
            title = user_message.replace("jules task", "").replace("queue task for jules", "").strip()
            if title:
                self.obsidian.queue_jules_task(
                    title       = title,
                    description = f"Requested via Echo voice command: {user_message}",
                )
                self.speak(f"Jules task queued: {title}")
            else:
                self.speak("What should the Jules task be?")


# ============================================================================
# QUICK SMOKE TEST  (run standalone to verify the bridge finds your vault)
#
#   cd ~/vision_assistant
#   python echo_obsidian_integration.py
# ============================================================================

if __name__ == "__main__":
    import logging, time
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)s  %(message)s")

    from obsidian_bridge import ObsidianBridge
    b = ObsidianBridge()
    b.start()
    time.sleep(3)   # let initial scan finish
    print("\nStatus:", b.status())
    print("\nContext pool (first 300 chars):")
    ctx = b.get_context_for_query("goals habits morning")
    print(ctx[:300] or "  (empty — tag some notes #echo-memory in Obsidian first)")
    b.stop()
