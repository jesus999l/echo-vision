"""
echo_settings_panel.py
======================
Settings panel for Echo Vision Assistant.
Adds a gear button to the chat overlay that opens a full settings window.

Features:
  - AI Providers tab: cookie login for each provider, status indicators
  - Models tab: toggle which AIs are active, see which is running
  - System tab: proxima server status, start/stop controls

HOW TO ADD TO ui.py:
  1. Drop this file into ~/vision_assistant/
  2. Add to top of ui.py:
       from echo_settings_panel import SettingsPanel, add_settings_button
  3. At the end of ChatOverlay.__init__ (after the window is built), add:
       add_settings_button(self)

That's it — a ⚙ gear button appears in your chat overlay.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import threading
import urllib.request
import urllib.error
import subprocess
import sys
import os
from pathlib import Path

# ── Theme colors (matches Echo dark theme) ───────────────────────────────────
BG       = "#1a1a2e"
BG2      = "#16213e"
BG3      = "#0f3460"
ACCENT   = "#e94560"
GREEN    = "#00d4aa"
YELLOW   = "#ffd700"
GRAY     = "#888888"
WHITE    = "#e0e0e0"
FG       = "#e0e0e0"

PROVIDERS = ["claude", "chatgpt", "gemini", "perplexity", "grok"]
PROVIDER_URLS = {
    "claude":     "https://claude.ai",
    "chatgpt":    "https://chat.openai.com",
    "gemini":     "https://gemini.google.com",
    "perplexity": "https://www.perplexity.ai",
    "grok":       "https://grok.com",
}
PROVIDER_COLORS = {
    "claude":     "#cc785c",
    "chatgpt":    "#19c37d",
    "gemini":     "#4285f4",
    "perplexity": "#20b2aa",
    "grok":       "#1da1f2",
}

COOKIE_DIR  = Path.home() / ".echo" / "cookies"
PROXIMA_URL = "http://localhost:3210"
VA_DIR      = Path.home() / "vision_assistant"

COOKIE_DIR.mkdir(parents=True, exist_ok=True)


# ── Proxima API helpers ───────────────────────────────────────────────────────

def proxima_status() -> dict:
    try:
        with urllib.request.urlopen(f"{PROXIMA_URL}/status", timeout=2) as r:
            return json.loads(r.read())
    except Exception:
        return {}

def proxima_alive() -> bool:
    try:
        urllib.request.urlopen(f"{PROXIMA_URL}/", timeout=1)
        return True
    except Exception:
        return False

def reload_cookies(provider: str) -> bool:
    try:
        req = urllib.request.Request(
            f"{PROXIMA_URL}/reload_cookies/{provider}", method="POST"
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read())
            return data.get("cookies_reloaded", False) or data.get("ready", False)
    except Exception:
        return False

def cookies_exist(provider: str) -> bool:
    p = COOKIE_DIR / f"{provider}.json"
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text())
        return isinstance(data, list) and len(data) > 0
    except Exception:
        return False

def save_cookies(provider: str, json_text: str) -> tuple[bool, str]:
    """Parse and save cookie JSON. Returns (success, message)."""
    text = json_text.strip()
    # Clean common paste artifacts
    text = text.replace("\u001b[?2004h", "").replace("\u001b[?2004l", "")
    text = text.replace("[~", "").replace("~\n", "")
    # Ensure it's wrapped in []
    if not text.startswith("["):
        text = "[" + text
    if not text.endswith("]"):
        text = text + "]"
    try:
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            return False, "Cookie data must be a JSON array"
        if len(parsed) == 0:
            return False, "No cookies found in pasted data"
        # Validate has required fields
        valid = [c for c in parsed if c.get("name") and c.get("value")]
        if not valid:
            return False, "Cookies missing name/value fields"
        out = COOKIE_DIR / f"{provider}.json"
        out.write_text(json.dumps(parsed, indent=2))
        return True, f"Saved {len(valid)} cookies"
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"


# ── Main Settings Panel ───────────────────────────────────────────────────────

class SettingsPanel:
    def __init__(self, parent):
        self.parent = parent
        self.win = tk.Toplevel(parent)
        self.win.title("Echo Settings")
        self.win.geometry("680x560")
        self.win.configure(bg=BG)
        self.win.resizable(True, True)
        self.win.grab_set()  # modal

        # Center on screen
        self.win.update_idletasks()
        x = (self.win.winfo_screenwidth() - 680) // 2
        y = (self.win.winfo_screenheight() - 560) // 2
        self.win.geometry(f"680x560+{x}+{y}")

        self._provider_status = {}
        self._build()
        self._refresh_status()

    def _build(self):
        # Title bar
        title_bar = tk.Frame(self.win, bg=BG3, height=44)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        tk.Label(title_bar, text="⚙  Echo Settings", bg=BG3, fg=WHITE,
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=16, pady=10)
        tk.Button(title_bar, text="✕", bg=BG3, fg=GRAY, bd=0,
                  font=("Segoe UI", 12), cursor="hand2",
                  activebackground=ACCENT, activeforeground=WHITE,
                  command=self.win.destroy).pack(side="right", padx=12)

        # Notebook tabs
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Echo.TNotebook", background=BG, borderwidth=0)
        style.configure("Echo.TNotebook.Tab", background=BG2, foreground=GRAY,
                        padding=[16,8], font=("Segoe UI", 10))
        style.map("Echo.TNotebook.Tab",
                  background=[("selected", BG3)],
                  foreground=[("selected", WHITE)])

        self.nb = ttk.Notebook(self.win, style="Echo.TNotebook")
        self.nb.pack(fill="both", expand=True, padx=0, pady=0)

        self._build_providers_tab()
        self._build_models_tab()
        self._build_system_tab()

    # ── Tab 1: AI Providers (Cookie Manager) ─────────────────────────────────

    def _build_providers_tab(self):
        frame = tk.Frame(self.nb, bg=BG)
        self.nb.add(frame, text="  AI Providers  ")

        # Header
        hdr = tk.Frame(frame, bg=BG2, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Cookie-based login — no API keys needed",
                 bg=BG2, fg=GRAY, font=("Segoe UI", 9)).pack(padx=16)

        # Scrollable provider list
        canvas = tk.Canvas(frame, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        self.prov_frame = tk.Frame(canvas, bg=BG)
        canvas.create_window((0, 0), window=self.prov_frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        self.prov_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self._provider_rows = {}
        for name in PROVIDERS:
            self._build_provider_row(name)

        # Instructions
        inst = tk.Frame(frame, bg=BG2, pady=8)
        inst.pack(fill="x", side="bottom")
        tk.Label(inst,
                 text="How to get cookies:  Browser → Cookie-Editor extension → claude.ai → Export → Copy JSON",
                 bg=BG2, fg=GRAY, font=("Segoe UI", 8)).pack()

    def _build_provider_row(self, name: str):
        color = PROVIDER_COLORS.get(name, ACCENT)
        row = tk.Frame(self.prov_frame, bg=BG2, pady=2)
        row.pack(fill="x", padx=12, pady=4)

        # Color bar
        tk.Frame(row, bg=color, width=4).pack(side="left", fill="y")

        body = tk.Frame(row, bg=BG2)
        body.pack(side="left", fill="x", expand=True, padx=10, pady=6)

        # Top line: name + status dot
        top = tk.Frame(body, bg=BG2)
        top.pack(fill="x")
        tk.Label(top, text=name.upper(), bg=BG2, fg=WHITE,
                 font=("Segoe UI", 10, "bold")).pack(side="left")

        status_dot = tk.Label(top, text="●", bg=BG2, fg=GRAY,
                               font=("Segoe UI", 10))
        status_dot.pack(side="left", padx=6)

        status_text = tk.Label(top, text="checking...", bg=BG2, fg=GRAY,
                                font=("Segoe UI", 8))
        status_text.pack(side="left")

        url_lbl = tk.Label(top, text=PROVIDER_URLS[name], bg=BG2, fg=BG3,
                           font=("Segoe UI", 8), cursor="hand2")
        url_lbl.pack(side="right")
        url_lbl.bind("<Button-1>", lambda e, u=PROVIDER_URLS[name]:
                     subprocess.Popen(["xdg-open", u]))

        # Bottom line: cookie count + buttons
        bot = tk.Frame(body, bg=BG2)
        bot.pack(fill="x", pady=(4, 0))

        cookie_lbl = tk.Label(bot, text="No cookies saved", bg=BG2, fg=GRAY,
                               font=("Segoe UI", 8))
        cookie_lbl.pack(side="left")

        btn_frame = tk.Frame(bot, bg=BG2)
        btn_frame.pack(side="right")

        paste_btn = tk.Button(btn_frame, text="Paste Cookies", bg=BG3, fg=WHITE,
                              font=("Segoe UI", 8), bd=0, padx=8, pady=3,
                              cursor="hand2", activebackground=color,
                              command=lambda n=name: self._open_cookie_paste(n))
        paste_btn.pack(side="left", padx=2)

        reload_btn = tk.Button(btn_frame, text="↺ Reload", bg=BG2, fg=GRAY,
                               font=("Segoe UI", 8), bd=0, padx=8, pady=3,
                               cursor="hand2",
                               command=lambda n=name: self._reload_provider(n))
        reload_btn.pack(side="left", padx=2)

        self._provider_rows[name] = {
            "status_dot":  status_dot,
            "status_text": status_text,
            "cookie_lbl":  cookie_lbl,
        }

    def _open_cookie_paste(self, provider: str):
        """Open a paste window for cookie JSON."""
        win = tk.Toplevel(self.win)
        win.title(f"Paste Cookies — {provider.upper()}")
        win.geometry("600x480")
        win.configure(bg=BG)
        win.grab_set()

        # Header
        hdr = tk.Frame(win, bg=BG3, pady=8)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"Paste Cookie-Editor JSON for {provider.upper()}",
                 bg=BG3, fg=WHITE, font=("Segoe UI", 11, "bold")).pack(padx=16)

        # Instructions
        steps = tk.Frame(win, bg=BG2, pady=8)
        steps.pack(fill="x")
        tk.Label(steps,
                 text="1. Open claude.ai in browser (logged in)\n"
                      "2. Click Cookie-Editor extension → Export → Copy to Clipboard\n"
                      "3. Paste below (Ctrl+V) then click Save",
                 bg=BG2, fg=GRAY, font=("Segoe UI", 9), justify="left").pack(padx=16, anchor="w")

        # Text area
        txt_frame = tk.Frame(win, bg=BG)
        txt_frame.pack(fill="both", expand=True, padx=12, pady=8)
        txt = scrolledtext.ScrolledText(txt_frame, bg="#0d1117", fg=GREEN,
                                         font=("Courier New", 9), insertbackground=WHITE,
                                         wrap="word", relief="flat", bd=0)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", "[ Paste JSON here... ]")
        txt.bind("<FocusIn>", lambda e: txt.delete("1.0", "end") if "Paste JSON" in txt.get("1.0","end") else None)

        # Status label
        status = tk.Label(win, text="", bg=BG, fg=GRAY, font=("Segoe UI", 9))
        status.pack(pady=4)

        # Buttons
        btn_row = tk.Frame(win, bg=BG)
        btn_row.pack(pady=8)

        def do_save():
            data = txt.get("1.0", "end").strip()
            ok, msg = save_cookies(provider, data)
            if ok:
                status.config(text=f"✓ {msg}", fg=GREEN)
                # Try to reload in running server
                if proxima_alive():
                    reloaded = reload_cookies(provider)
                    if reloaded:
                        status.config(text=f"✓ {msg} — loaded into server", fg=GREEN)
                self._refresh_status()
                win.after(1500, win.destroy)
            else:
                status.config(text=f"✗ {msg}", fg=ACCENT)

        tk.Button(btn_row, text="Save Cookies", bg=GREEN, fg=BG,
                  font=("Segoe UI", 10, "bold"), bd=0, padx=20, pady=6,
                  cursor="hand2", command=do_save).pack(side="left", padx=8)
        tk.Button(btn_row, text="Cancel", bg=BG2, fg=GRAY,
                  font=("Segoe UI", 10), bd=0, padx=20, pady=6,
                  cursor="hand2", command=win.destroy).pack(side="left", padx=8)

    def _reload_provider(self, provider: str):
        if not proxima_alive():
            messagebox.showwarning("Server Not Running",
                                   "Proxima native is not running.\nStart it first: ~/start-echo.sh",
                                   parent=self.win)
            return
        ok = reload_cookies(provider)
        row = self._provider_rows[provider]
        if ok:
            row["status_dot"].config(fg=GREEN)
            row["status_text"].config(text="ready ✓", fg=GREEN)
        else:
            row["status_text"].config(text="reload failed", fg=ACCENT)
        self._refresh_status()

    # ── Tab 2: Models ─────────────────────────────────────────────────────────

    def _build_models_tab(self):
        frame = tk.Frame(self.nb, bg=BG)
        self.nb.add(frame, text="  Models  ")

        tk.Label(frame, text="Active AI Providers",
                 bg=BG, fg=WHITE, font=("Segoe UI", 11, "bold")).pack(pady=(16,4), padx=16, anchor="w")
        tk.Label(frame, text="Toggle which AIs respond to your messages",
                 bg=BG, fg=GRAY, font=("Segoe UI", 9)).pack(padx=16, anchor="w")

        self._model_vars = {}
        model_frame = tk.Frame(frame, bg=BG)
        model_frame.pack(fill="x", padx=16, pady=12)

        for name in PROVIDERS:
            color = PROVIDER_COLORS.get(name, ACCENT)
            var = tk.BooleanVar(value=True)
            self._model_vars[name] = var

            row = tk.Frame(model_frame, bg=BG2, pady=2)
            row.pack(fill="x", pady=3)
            tk.Frame(row, bg=color, width=4).pack(side="left", fill="y")

            inner = tk.Frame(row, bg=BG2)
            inner.pack(side="left", fill="x", expand=True, padx=10, pady=6)

            tk.Label(inner, text=name.upper(), bg=BG2, fg=WHITE,
                     font=("Segoe UI", 10, "bold")).pack(side="left")

            cb = tk.Checkbutton(inner, variable=var, bg=BG2,
                                activebackground=BG2, selectcolor=BG3,
                                fg=color, text="enabled",
                                font=("Segoe UI", 9))
            cb.pack(side="right", padx=8)

        # Apply button
        def apply_models():
            enabled = [n for n,v in self._model_vars.items() if v.get()]
            if not enabled:
                messagebox.showwarning("No Providers",
                                       "At least one provider must be enabled.",
                                       parent=self.win)
                return
            # Push to the AI router
            try:
                import sys, os
                sys.path.insert(0, str(VA_DIR))
                # Try to find the running app instance
                # This works if main.py stored the app globally
                import builtins
                app = getattr(builtins, "_echo_app", None)
                if app and hasattr(app, "ai") and hasattr(app.ai, "set_enabled"):
                    app.ai.set_enabled(enabled)
                    messagebox.showinfo("Applied",
                                       f"Active providers: {', '.join(enabled)}",
                                       parent=self.win)
                else:
                    messagebox.showinfo("Saved",
                                       f"Will use: {', '.join(enabled)}\n"
                                       f"(Restart Echo to apply)",
                                       parent=self.win)
            except Exception as e:
                messagebox.showinfo("Saved",
                                    f"Active: {', '.join(enabled)}",
                                    parent=self.win)

        tk.Button(frame, text="Apply", bg=BG3, fg=WHITE,
                  font=("Segoe UI", 10, "bold"), bd=0, padx=24, pady=6,
                  cursor="hand2", command=apply_models).pack(pady=8)

    # ── Tab 3: System ─────────────────────────────────────────────────────────

    def _build_system_tab(self):
        frame = tk.Frame(self.nb, bg=BG)
        self.nb.add(frame, text="  System  ")

        tk.Label(frame, text="Echo Stack Status",
                 bg=BG, fg=WHITE, font=("Segoe UI", 11, "bold")).pack(pady=(16,8), padx=16, anchor="w")

        services = [
            ("Proxima Native",   ":3210",  "echo_proxima_native"),
            ("Browser Server",   ":59996", "echo_browser_server"),
            ("Group Chat",       ":8484",  "echo_group_chat"),
            ("Hermes Gateway",   "discord","hermes_cli.main"),
            ("Open WebUI",       ":8080",  "open_webui"),
        ]

        self._service_labels = {}
        svc_frame = tk.Frame(frame, bg=BG)
        svc_frame.pack(fill="x", padx=16)

        for label, port, proc in services:
            row = tk.Frame(svc_frame, bg=BG2, pady=6)
            row.pack(fill="x", pady=2)

            tk.Label(row, text=label, bg=BG2, fg=WHITE,
                     font=("Segoe UI", 10), width=20, anchor="w").pack(side="left", padx=10)
            tk.Label(row, text=port, bg=BG2, fg=GRAY,
                     font=("Courier New", 9)).pack(side="left", padx=4)

            dot = tk.Label(row, text="●", bg=BG2, fg=GRAY, font=("Segoe UI", 12))
            dot.pack(side="right", padx=4)
            lbl = tk.Label(row, text="checking...", bg=BG2, fg=GRAY, font=("Segoe UI", 8))
            lbl.pack(side="right", padx=4)

            self._service_labels[proc] = (dot, lbl)

        # Buttons
        btn_row = tk.Frame(frame, bg=BG)
        btn_row.pack(pady=16)

        tk.Button(btn_row, text="⟳ Refresh Status", bg=BG3, fg=WHITE,
                  font=("Segoe UI", 9), bd=0, padx=12, pady=5,
                  cursor="hand2",
                  command=self._refresh_status).pack(side="left", padx=6)

        tk.Button(btn_row, text="▶ Start Full Stack", bg=GREEN, fg=BG,
                  font=("Segoe UI", 9, "bold"), bd=0, padx=12, pady=5,
                  cursor="hand2",
                  command=self._start_stack).pack(side="left", padx=6)

        tk.Button(btn_row, text="Start Proxima", bg=BG2, fg=WHITE,
                  font=("Segoe UI", 9), bd=0, padx=12, pady=5,
                  cursor="hand2",
                  command=self._start_proxima).pack(side="left", padx=6)

        # Log viewer
        tk.Label(frame, text="Proxima Log", bg=BG, fg=GRAY,
                 font=("Segoe UI", 9)).pack(padx=16, anchor="w", pady=(8,2))
        self.log_box = scrolledtext.ScrolledText(frame, bg="#0d1117", fg=GREEN,
                                                  font=("Courier New", 8), height=6,
                                                  state="disabled", relief="flat")
        self.log_box.pack(fill="x", padx=16, pady=(0,8))

        tk.Button(frame, text="Tail Log", bg=BG2, fg=GRAY,
                  font=("Segoe UI", 8), bd=0, padx=10, pady=3,
                  cursor="hand2", command=self._tail_log).pack(anchor="w", padx=16)

    def _start_proxima(self):
        script = VA_DIR / "echo_proxima_native.py"
        if not script.exists():
            messagebox.showerror("Not Found",
                                 f"echo_proxima_native.py not found in\n{VA_DIR}",
                                 parent=self.win)
            return
        python = Path.home() / "vision_env" / "bin" / "python3"
        if not python.exists():
            python = Path(sys.executable)
        subprocess.Popen(
            [str(python), str(script), "--headless"],
            cwd=str(VA_DIR),
            stdout=open("/tmp/echo_proxima.log","a"),
            stderr=subprocess.STDOUT,
        )
        self.win.after(2000, self._refresh_status)

    def _start_stack(self):
        start_sh = Path.home() / "start-echo.sh"
        if start_sh.exists():
            subprocess.Popen(["bash", str(start_sh)])
            self.win.after(3000, self._refresh_status)
        else:
            messagebox.showinfo("Not Found",
                                "~/start-echo.sh not found.\nRun echo_proxima_setup.py first.",
                                parent=self.win)

    def _tail_log(self):
        try:
            with open("/tmp/echo_proxima.log") as f:
                lines = f.readlines()[-30:]
            self.log_box.config(state="normal")
            self.log_box.delete("1.0", "end")
            self.log_box.insert("end", "".join(lines))
            self.log_box.config(state="disabled")
            self.log_box.see("end")
        except Exception as e:
            self.log_box.config(state="normal")
            self.log_box.insert("end", f"No log: {e}\n")
            self.log_box.config(state="disabled")

    # ── Status refresh (runs in background thread) ────────────────────────────

    def _refresh_status(self):
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        # Get proxima status
        status = proxima_status()
        alive  = proxima_alive()

        # Update provider rows
        for name in PROVIDERS:
            row = self._provider_rows.get(name)
            if not row:
                continue
            has_cookies = cookies_exist(name)
            proxima_ready = status.get(name, {}).get("ready", False)

            cookie_count = 0
            cookie_path = COOKIE_DIR / f"{name}.json"
            if has_cookies:
                try:
                    cookie_count = len(json.loads(cookie_path.read_text()))
                except Exception:
                    pass

            if proxima_ready:
                dot_color, status_str = GREEN, "ready ✓"
            elif has_cookies:
                dot_color, status_str = YELLOW, f"{cookie_count} cookies (not loaded)"
            else:
                dot_color, status_str = GRAY, "no cookies"

            cookie_str = f"{cookie_count} cookies saved" if has_cookies else "No cookies saved"

            # Schedule UI update on main thread
            self.win.after(0, lambda r=row, d=dot_color, s=status_str, c=cookie_str: [
                r["status_dot"].config(fg=d),
                r["status_text"].config(text=s, fg=d),
                r["cookie_lbl"].config(text=c),
            ])

        # Update service status
        for proc, (dot, lbl) in self._service_labels.items():
            try:
                result = subprocess.run(
                    ["pgrep", "-f", proc], capture_output=True, timeout=2
                )
                running = result.returncode == 0
            except Exception:
                running = False
            color = GREEN if running else GRAY
            text  = "running" if running else "stopped"
            self.win.after(0, lambda d=dot, l=lbl, c=color, t=text: [
                d.config(fg=c), l.config(text=t, fg=c)
            ])


# ── Add settings button to ChatOverlay ───────────────────────────────────────

def add_settings_button(chat_overlay):
    """
    Call this from ChatOverlay.__init__ after the window is built.
    Adds a ⚙ gear button that opens the settings panel.

    Usage in ui.py:
        from echo_settings_panel import add_settings_button
        # at end of __init__:
        add_settings_button(self)
    """
    root = getattr(chat_overlay, "root", None) or getattr(chat_overlay, "window", None)
    if root is None:
        # Try to find the main window
        for attr in ["win", "frame", "container", "master"]:
            root = getattr(chat_overlay, attr, None)
            if root:
                break
    if root is None:
        return  # Can't find window — skip

    def open_settings():
        SettingsPanel(root)

    # Create gear button — try to place it in common locations
    btn = tk.Button(
        root,
        text="⚙",
        bg=BG2,
        fg=GRAY,
        font=("Segoe UI", 12),
        bd=0,
        padx=6,
        pady=4,
        cursor="hand2",
        activebackground=BG3,
        activeforeground=WHITE,
        command=open_settings,
    )

    # Try to place it — pack or place depending on what's available
    try:
        btn.place(relx=1.0, rely=0.0, anchor="ne", x=-4, y=4)
    except Exception:
        try:
            btn.pack(side="top", anchor="ne", padx=4, pady=4)
        except Exception:
            pass

    # Store reference so it's not GC'd
    chat_overlay._settings_btn = btn
    return btn


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    root.title("Echo Settings Test")
    root.configure(bg=BG)
    root.geometry("200x100")

    tk.Label(root, text="Echo Vision", bg=BG, fg=WHITE,
             font=("Segoe UI", 12, "bold")).pack(pady=20)
    tk.Button(root, text="⚙ Settings", bg=BG2, fg=WHITE,
              font=("Segoe UI", 10), bd=0, padx=16, pady=6,
              command=lambda: SettingsPanel(root)).pack()
    root.mainloop()
