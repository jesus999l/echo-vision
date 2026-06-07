#!/usr/bin/env python3
"""
drift_panel.py — driftwm side panel v2
Working kill buttons, edge selector, wlrctl wired, grouping by app.
"""
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, GLib, Gdk, GtkLayerShell
import subprocess, os, time

PANEL_WIDTH    = 230
COLLAPSED_W    = 6
KILL_CLICKS    = 5
POLL_MS        = 2500
EDGE           = "left"   # left | right | top | bottom

CSS = """
* { font-family: "JetBrains Mono", "Fira Code", "DejaVu Sans Mono", monospace;
    font-size: 11px; }
window { background-color: #0d0d0f; border-right: 1px solid #1e1e28; }
#header { background-color: #111116; padding: 10px 10px 8px 10px;
          border-bottom: 1px solid #1e1e28; }
#title  { color: #a78bfa; font-weight: bold; letter-spacing: 2px; font-size: 10px; }
#wcount { color: #44445a; font-size: 10px; }
.sec    { color: #44445a; font-size: 9px; letter-spacing: 1px;
          padding: 8px 10px 3px 10px; }
.app-group { background-color: #0f0f14; border-radius: 6px;
             margin: 3px 6px 1px 6px; padding: 2px; }
.win-btn  { background: transparent; border: none; border-radius: 5px;
            padding: 5px 8px; }
.win-btn:hover  { background-color: #1a1a24; }
.win-title { color: #e2e2ea; }
.win-app   { color: #44445a; font-size: 9px; }
.kill-btn  { background: transparent; border: none; border-radius: 4px;
             color: #44445a; font-size: 10px; padding: 4px 6px; min-width: 28px; }
.kill-btn:hover { background-color: #2a1a1a; color: #f97316; }
.kill-1 { color: #94a3b8; }
.kill-2 { color: #fbbf24; }
.kill-3 { color: #f97316; font-weight: bold; }
.kill-4 { color: #ef4444; font-weight: bold; }
.kill-confirm { background-color: #ef4444; color: white;
                font-weight: bold; border-radius: 4px; }
.edge-btn { background-color: #1a1a24; border: none; color: #6b6b80;
            font-size: 9px; padding: 3px 5px; border-radius: 3px; margin: 1px; }
.edge-btn:hover { background-color: #7c6af7; color: white; }
.edge-active { background-color: #7c6af7; color: white; }
.echo-section { background-color: #0a0a0e; border-top: 1px solid #1e1e28;
               padding: 8px 6px 6px 6px; }
.echo-label { color: #a78bfa; font-size: 9px; letter-spacing: 1px; padding: 0 4px 4px 4px; }
.echo-response { background-color: #0f0f14; color: #c4c4d4; border-radius: 5px;
                 padding: 6px; font-size: 10px; min-height: 60px; }
.echo-entry { background-color: #1a1a24; color: #e2e2ea; border: 1px solid #2a2a38;
              border-radius: 5px; padding: 4px 8px; font-size: 11px; }
.echo-send { background-color: #7c6af7; color: white; border: none; border-radius: 5px;
             padding: 4px 10px; font-size: 10px; font-weight: bold; }
.echo-send:hover { background-color: #9d8fff; }

#toggle { background-color: #1e1e28; border: none; color: #6b6b80;
          min-width: 6px; padding: 0 2px; border-radius: 0; }
#toggle:hover { background-color: #7c6af7; color: white; }
"""

def wlr_list():
    try:
        out = subprocess.check_output(
            ["wlrctl", "toplevel", "list"], stderr=subprocess.DEVNULL, timeout=2
        ).decode().strip()
        wins = []
        for line in out.splitlines():
            if not line.strip():
                continue
            if ": " in line:
                app, title = line.split(": ", 1)
                app = app.strip().rstrip(":")
            else:
                app, title = "app", line.strip()
            wid = f"{app}:{title}"
            wins.append({"id": wid, "app_id": app, "title": title, "raw": line})
        return wins
    except Exception:
        return []

XWAYLAND_APPS = {"firefox", "discord", "steam", "chromium", "chrome"}

def wlr_focus(win):
    title  = win.get("title", "")[:60]
    app_id = win.get("app_id", "").lower()
    try:
        if any(x in app_id for x in XWAYLAND_APPS):
            ids = subprocess.check_output(
                ["xdotool", "search", "--name", title],
                stderr=subprocess.DEVNULL, timeout=2
            ).decode().strip().splitlines()
            if ids:
                subprocess.Popen(["wlrctl", "toplevel", "focus", f"id:{ids[0]}"],
                                 stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(
                ["wlrctl", "toplevel", "focus", f"title:{title}"],
                stderr=subprocess.DEVNULL
            )
    except Exception:
        pass


def wlr_close(win):
    title  = win.get("title", "")[:60]
    app_id = win.get("app_id", "").lower()
    try:
        if any(x in app_id for x in XWAYLAND_APPS):
            ids = subprocess.check_output(
                ["xdotool", "search", "--name", title],
                stderr=subprocess.DEVNULL, timeout=2
            ).decode().strip().splitlines()
            if ids:
                subprocess.Popen(["wlrctl", "toplevel", "close", f"id:{ids[0]}"],
                                 stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(
                ["wlrctl", "toplevel", "close", f"title:{title}"],
                stderr=subprocess.DEVNULL
            )
    except Exception:
        pass


class DriftPanel:
    def __init__(self):
        self.expanded    = True
        self.edge        = EDGE
        self.kills       = {}   # id → click count
        self.ktimes      = {}   # id → last click time
        self.windows     = []
        self._build()

    def _build(self):
        self.win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.win.set_title("drift-panel")
        self.win.connect("destroy", Gtk.main_quit)

        GtkLayerShell.init_for_window(self.win)
        GtkLayerShell.set_layer(self.win, GtkLayerShell.Layer.TOP)
        GtkLayerShell.set_keyboard_mode(self.win, GtkLayerShell.KeyboardMode.ON_DEMAND)
        GtkLayerShell.set_namespace(self.win, "drift-panel")
        self._set_edge(self.edge, init=True)

        css = Gtk.CssProvider()
        css.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.win.add(self.outer)

        # Toggle strip
        self.toggle = Gtk.Button(label="◀")
        self.toggle.set_name("toggle")
        self.toggle.connect("clicked", self._on_toggle)

        # Panel body
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.body.set_size_request(PANEL_WIDTH, -1)

        # Header
        hdr = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hdr.set_name("header")
        row1 = Gtk.Box()
        self.title_l = Gtk.Label(label="DRIFT")
        self.title_l.set_name("title")
        self.title_l.set_halign(Gtk.Align.START)
        self.count_l = Gtk.Label(label="")
        self.count_l.set_name("wcount")
        self.count_l.set_halign(Gtk.Align.END)
        row1.pack_start(self.title_l, True, True, 0)
        row1.pack_end(self.count_l, False, False, 0)
        hdr.pack_start(row1, False, False, 0)

        # Edge selector
        edge_row = Gtk.Box(spacing=2)
        edge_row.set_margin_top(6)
        for e, lbl in [("left","◧"),("right","◨"),("top","⬒"),("bottom","⬓")]:
            b = Gtk.Button(label=lbl)
            b.get_style_context().add_class("edge-btn")
            if e == self.edge:
                b.get_style_context().add_class("edge-active")
            b.connect("clicked", self._on_edge, e)
            setattr(self, f"edge_btn_{e}", b)
            edge_row.pack_start(b, True, True, 0)
        hdr.pack_start(edge_row, False, False, 0)
        self.body.pack_start(hdr, False, False, 0)

        # Section label
        sec = Gtk.Label(label="WINDOWS")
        sec.get_style_context().add_class("sec")
        sec.set_halign(Gtk.Align.START)
        self.body.pack_start(sec, False, False, 0)

        # Scrollable list
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scroll.add(self.list_box)
        self.body.pack_start(scroll, True, True, 0)
        self.body.pack_start(EchoChatWidget(), False, False, 0)

        self.outer.pack_start(self.body, True, True, 0)
        self.outer.pack_end(self.toggle, False, False, 0)

        self.win.show_all()
        self._refresh()
        GLib.timeout_add(POLL_MS, self._refresh)

    def _set_edge(self, edge, init=False):
        edges = {
            "left":   [GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM],
            "right":  [GtkLayerShell.Edge.RIGHT, GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM],
            "top":    [GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT],
            "bottom": [GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT],
        }
        # Clear all anchors first
        for e in [GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT,
                  GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM]:
            GtkLayerShell.set_anchor(self.win, e, False)
        for e in edges.get(edge, edges["left"]):
            GtkLayerShell.set_anchor(self.win, e, True)
        GtkLayerShell.set_exclusive_zone(self.win, PANEL_WIDTH)
        GtkLayerShell.set_margin(self.win, GtkLayerShell.Edge.BOTTOM, 32)
        self.edge = edge
        if not init:
            self.toggle.set_label("◀" if edge == "left" else
                                  "▶" if edge == "right" else
                                  "▲" if edge == "bottom" else "▼")

    def _on_edge(self, btn, edge):
        # Update button styles
        for e in ["left","right","top","bottom"]:
            b = getattr(self, f"edge_btn_{e}", None)
            if b:
                b.get_style_context().remove_class("edge-active")
        btn.get_style_context().add_class("edge-active")
        self._set_edge(edge)

    def _on_toggle(self, btn):
        self.expanded = not self.expanded
        if self.expanded:
            self.body.show()
            GtkLayerShell.set_exclusive_zone(self.win, PANEL_WIDTH)
            self.toggle.set_label("◀")
        else:
            self.body.hide()
            GtkLayerShell.set_exclusive_zone(self.win, COLLAPSED_W)
            self.toggle.set_label("▶")

    def _refresh(self):
        self.windows = wlr_list()
        self.count_l.set_text(f"{len(self.windows)}")
        for c in self.list_box.get_children():
            self.list_box.remove(c)

        # Group by app_id
        groups = {}
        for w in self.windows:
            groups.setdefault(w["app_id"], []).append(w)

        for app_id, wins in groups.items():
            grp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            grp.get_style_context().add_class("app-group")
            for w in wins:
                grp.pack_start(self._make_row(w), False, False, 0)
            self.list_box.pack_start(grp, False, False, 2)

        self.list_box.show_all()
        return True

    def _make_row(self, win):
        wid    = win["id"]
        clicks = self.kills.get(wid, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        # Main window button
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.get_style_context().add_class("win-btn")
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        t = win["title"]
        tl = Gtk.Label(label=(t[:26]+"…" if len(t)>26 else t))
        tl.get_style_context().add_class("win-title")
        tl.set_halign(Gtk.Align.START)
        tl.set_xalign(0)
        al = Gtk.Label(label=win["app_id"])
        al.get_style_context().add_class("win-app")
        al.set_halign(Gtk.Align.START)
        al.set_xalign(0)
        inner.pack_start(tl, False, False, 0)
        inner.pack_start(al, False, False, 0)
        btn.add(inner)
        btn.connect("clicked", self._on_focus, win)
        btn.connect("button-press-event", self._on_rclick, win)

        # Kill button — separate, always clickable
        kill_btn = Gtk.Button()
        kill_btn.set_relief(Gtk.ReliefStyle.NONE)
        kill_btn.get_style_context().add_class("kill-btn")
        kill_btn.set_valign(Gtk.Align.CENTER)

        if clicks == 0:
            kill_btn.set_label("✕")
        elif clicks < KILL_CLICKS - 1:
            kill_btn.set_label(f"✕{clicks}")
            kill_btn.get_style_context().add_class(f"kill-{clicks}")
        else:
            kill_btn.set_label("☠ KILL")
            kill_btn.get_style_context().add_class("kill-confirm")

        kill_btn.connect("clicked", self._on_kill, win)

        row.pack_start(btn,      True,  True,  0)
        row.pack_end(kill_btn,   False, False, 0)
        return row

    def _on_focus(self, btn, win):
        # Reset kill counter on focus click
        self.kills.pop(win["id"], None)
        self.ktimes.pop(win["id"], None)
        wlr_focus(win)
        GLib.timeout_add(200, self._refresh)

    def _on_kill(self, btn, win):
        wlr_close(win)
        GLib.timeout_add(150, self._refresh)

    def _on_rclick(self, widget, event, win):
        if event.button != 3:
            return False
        menu = Gtk.Menu()
        for label, fn in [
            ("⬛  Jump to window",  lambda _: wlr_focus(win)),
            ("✕  Close window",    lambda _: (wlr_close(win), GLib.timeout_add(150, self._refresh))),
            ("💀  Force Kill",     lambda _: (wlr_close(win), GLib.timeout_add(150, self._refresh))),
        ]:
            item = Gtk.MenuItem(label=label)
            item.connect("activate", fn)
            menu.append(item)
        menu.show_all()
        menu.popup_at_pointer(event)
        return True



class EchoChatWidget(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.get_style_context().add_class("echo-section")

        lbl = Gtk.Label(label="◈ ECHO")
        lbl.get_style_context().add_class("echo-label")
        lbl.set_halign(Gtk.Align.START)
        self.pack_start(lbl, False, False, 0)

        # Response area
        self.resp_buf = Gtk.TextBuffer()
        self.resp_buf.set_text("Ask Echo anything...")
        self.resp_view = Gtk.TextView(buffer=self.resp_buf)
        self.resp_view.set_editable(False)
        self.resp_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.resp_view.get_style_context().add_class("echo-response")
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(80)
        scroll.set_max_content_height(160)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.resp_view)
        self.pack_start(scroll, False, False, 0)

        # Input row
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.entry = Gtk.Entry()
        self.entry.get_style_context().add_class("echo-entry")
        self.entry.set_placeholder_text("Ask Echo...")
        self.entry.set_can_focus(True)
        self.entry.connect("activate", self._send)
        self.entry.connect("button-press-event", self._grab_focus)
        send_btn = Gtk.Button(label="▶")
        send_btn.get_style_context().add_class("echo-send")
        send_btn.connect("clicked", self._send)
        mic_btn = Gtk.Button(label="🎤")
        mic_btn.get_style_context().add_class("echo-send")
        mic_btn.connect("clicked", self._mic)
        row.pack_start(self.entry, True, True, 0)
        row.pack_end(send_btn, False, False, 0)
        row.pack_end(mic_btn, False, False, 0)
        self.pack_start(row, False, False, 0)

    def _send(self, *_):
        msg = self.entry.get_text().strip()
        if not msg:
            return
        self.entry.set_text("")
        self.resp_buf.set_text("⏳ thinking...")
        import threading, urllib.request, json
        def ask():
            try:
                data = json.dumps({"message": msg}).encode()
                req = urllib.request.Request(
                    "http://localhost:8765/chat",
                    data=data,
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    result = json.loads(r.read())
                    text = result.get("response", "no response")
                    # strip provider prefix like [🔍 PERPLEXITY]
                    import re
                    text = re.sub(r'^\[.*?\]\s*', '', text).strip()
            except Exception as e:
                text = f"error: {e}"
            def update():
                self.resp_buf.set_text(text)
                # scroll to end
                end = self.resp_buf.get_end_iter()
                self.resp_view.scroll_to_iter(end, 0, False, 0, 0)
            GLib.idle_add(update)
        threading.Thread(target=ask, daemon=True).start()

    def _grab_focus(self, widget, event):
        widget.grab_focus()
        return False

    def _mic(self, *_):
        self.resp_buf.set_text("🎤 listening...")
        import threading, subprocess, tempfile, os
        def record():
            try:
                tmp = "/tmp/echo_panel_mic.wav"
                subprocess.run([
                    "arecord", "-d", "4", "-D", "hw:0,0", "-f", "S16_LE", "-r", "16000",
                    "-c", "1", tmp
                ], capture_output=True)
                from faster_whisper import WhisperModel
                m = WhisperModel("small.en", device="cpu", compute_type="int8")
                segs, _ = m.transcribe(tmp)
                text = " ".join(s.text for s in segs).strip()
                os.unlink(tmp)
                if text:
                    GLib.idle_add(self.entry.set_text, text)
                    GLib.idle_add(self._send)
                else:
                    GLib.idle_add(self.resp_buf.set_text, "nothing heard")
            except Exception as e:
                GLib.idle_add(self.resp_buf.set_text, f"mic error: {e}")
        threading.Thread(target=record, daemon=True).start()


def main():
    if not os.environ.get("WAYLAND_DISPLAY"):
        print("[drift-panel] No WAYLAND_DISPLAY, exiting.")
        return
    DriftPanel()
    try:
        Gtk.main()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
