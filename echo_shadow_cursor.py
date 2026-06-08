#!/usr/bin/env python3
"""
echo_shadow_cursor.py — Echo's ghost cursor overlay
A transparent fullscreen window that renders a colored ghost cursor.
Receives coordinates via socket on :59998 and animates the cursor there.
Also accepts AI instructions: takes screenshot, asks Gemini Vision, moves to result.

Usage:
    python3 echo_shadow_cursor.py          # start overlay daemon
    python3 echo_shadow_cursor.py "click the settings button"  # AI mode
    echo '{"x": 500, "y": 300, "label": "Settings"}' | nc localhost 59998
"""

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, Gdk, GLib, GtkLayerShell
import cairo, socket, threading, json, sys, os, subprocess, time

SOCKET_PORT = 59998
CURSOR_RADIUS = 18
CURSOR_COLOR = (0.48, 0.42, 0.97, 0.85)   # #7c6af7 purple
LABEL_COLOR  = (0.88, 0.88, 0.94, 0.95)
TRAIL_STEPS  = 8
ANIM_MS      = 16   # ~60fps
MOVE_SPEED   = 0.18 # lerp factor per frame


class ShadowCursor(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)

        # Layer shell setup — overlay on top of everything
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)
        GtkLayerShell.set_exclusive_zone(self, -1)  # don't push other windows

        # Transparent window
        self.set_app_paintable(True)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        # Pass through all input events — ghost cursor doesn't block clicks
        self.input_shape_combine_region(cairo.Region())

        self.set_decorated(False)
        self.set_accept_focus(False)

        # State
        self.cur_x = -100.0
        self.cur_y = -100.0
        self.target_x = -100.0
        self.target_y = -100.0
        self.label = ""
        self.visible = False
        self.trail = []          # list of (x, y, alpha)
        self.hide_timer = None
        self.pulse = 0.0

        # Drawing area
        self.da = Gtk.DrawingArea()
        self.da.connect("draw", self._draw)
        self.add(self.da)
        self.show_all()

        # Animation loop
        GLib.timeout_add(ANIM_MS, self._animate)

        # Socket server
        threading.Thread(target=self._socket_server, daemon=True).start()

        print("[shadow] Ghost cursor ready on :59998")

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _draw(self, widget, cr):
        if not self.visible:
            return

        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        # Draw trail
        for i, (tx, ty, alpha) in enumerate(self.trail):
            r = CURSOR_RADIUS * 0.4 * (i / len(self.trail))
            cr.arc(tx, ty, max(r, 2), 0, 2 * 3.14159)
            cr.set_source_rgba(*CURSOR_COLOR[:3], alpha * 0.3)
            cr.fill()

        # Pulse ring
        pulse_r = CURSOR_RADIUS + 8 * abs(self.pulse - 0.5) * 2
        cr.arc(self.cur_x, self.cur_y, pulse_r, 0, 2 * 3.14159)
        cr.set_source_rgba(*CURSOR_COLOR[:3], 0.25 * (1 - abs(self.pulse - 0.5) * 2))
        cr.fill()

        # Main cursor circle
        cr.arc(self.cur_x, self.cur_y, CURSOR_RADIUS, 0, 2 * 3.14159)
        cr.set_source_rgba(*CURSOR_COLOR)
        cr.fill()

        # Inner dot
        cr.arc(self.cur_x, self.cur_y, 4, 0, 2 * 3.14159)
        cr.set_source_rgba(1, 1, 1, 0.9)
        cr.fill()

        # Label
        if self.label:
            cr.select_font_face("JetBrains Mono", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(13)
            extents = cr.text_extents(self.label)
            pad = 8
            lx = self.cur_x + CURSOR_RADIUS + 10
            ly = self.cur_y - 6
            # Background pill
            cr.rectangle(lx - pad, ly - extents.height - pad/2,
                         extents.width + pad*2, extents.height + pad)
            cr.set_source_rgba(0.07, 0.07, 0.12, 0.88)
            cr.fill()
            # Text
            cr.move_to(lx, ly)
            cr.set_source_rgba(*LABEL_COLOR)
            cr.show_text(self.label)

    # ── Animation ─────────────────────────────────────────────────────────────

    def _animate(self):
        if not self.visible:
            return True

        # Lerp toward target
        dx = self.target_x - self.cur_x
        dy = self.target_y - self.cur_y
        dist = (dx**2 + dy**2) ** 0.5

        if dist > 1.5:
            self.trail.append((self.cur_x, self.cur_y,
                                CURSOR_COLOR[3] * (len(self.trail) + 1) / TRAIL_STEPS))
            if len(self.trail) > TRAIL_STEPS:
                self.trail.pop(0)
            self.cur_x += dx * MOVE_SPEED
            self.cur_y += dy * MOVE_SPEED
        else:
            self.cur_x = self.target_x
            self.cur_y = self.target_y
            self.trail = []

        # Pulse
        self.pulse = (self.pulse + 0.02) % 1.0

        self.da.queue_draw()
        return True

    # ── Commands ──────────────────────────────────────────────────────────────

    def move_to(self, x, y, label=""):
        def _do():
            self.target_x = float(x)
            self.target_y = float(y)
            self.label = label
            self.visible = True
            # Auto-hide after 4s
            if self.hide_timer:
                GLib.source_remove(self.hide_timer)
            self.hide_timer = GLib.timeout_add(4000, self._hide)
        GLib.idle_add(_do)

    def _hide(self):
        self.visible = False
        self.label = ""
        self.trail = []
        self.da.queue_draw()
        self.hide_timer = None
        return False

    def click_at(self, x, y, label=""):
        self.move_to(x, y, label)
        def _click():
            time.sleep(0.6)  # wait for cursor to arrive
            subprocess.run(["xdotool", "mousemove", str(int(x)), str(int(y))])
            time.sleep(0.1)
            subprocess.run(["xdotool", "click", "1"])
        threading.Thread(target=_click, daemon=True).start()

    # ── Socket server ─────────────────────────────────────────────────────────

    def _socket_server(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", SOCKET_PORT))
        s.listen(5)
        while True:
            try:
                conn, _ = s.accept()
                data = conn.recv(4096).decode().strip()
                conn.close()
                self._handle_command(data)
            except Exception as e:
                print(f"[shadow] socket error: {e}")

    def _handle_command(self, data):
        try:
            cmd = json.loads(data)
            action = cmd.get("action", "move")
            x = cmd.get("x", 0)
            y = cmd.get("y", 0)
            label = cmd.get("label", "")

            if action == "click":
                self.click_at(x, y, label)
            elif action == "hide":
                GLib.idle_add(self._hide)
            elif action == "ai":
                # AI mode: take screenshot, ask Gemini Vision, move cursor
                instruction = cmd.get("instruction", "")
                threading.Thread(
                    target=self._ai_guide, args=(instruction,), daemon=True
                ).start()
            else:
                self.move_to(x, y, label)
        except Exception as e:
            print(f"[shadow] command error: {e}")

    def _ai_guide(self, instruction):
        """Take screenshot, ask Gemini Vision where to look, move ghost cursor there."""
        try:
            import tempfile, base64, urllib.request, json as _json, re

            # Screenshot
            tmp = tempfile.mktemp(suffix=".png")
            subprocess.run(["grim", tmp], capture_output=True)
            if not os.path.exists(tmp):
                print("[shadow] screenshot failed")
                return

            with open(tmp, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            os.unlink(tmp)

            # Get screen dimensions for context
            display = Gdk.Display.get_default()
            monitor = display.get_monitor(0)
            geo = monitor.get_geometry()
            w, h = geo.width, geo.height

            prompt = f"""This is a {w}x{h} screenshot.
The user wants to: "{instruction}"
Find the most relevant UI element and return ONLY a JSON object:
{{"x": 123, "y": 456, "label": "element name", "explanation": "one sentence"}}
x and y are pixel coordinates. No other text."""

            payload = _json.dumps({
                "model": "gemini-2.0-flash",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/png;base64,{img_b64}"
                        }}
                    ]
                }]
            }).encode()

            req = urllib.request.Request(
                "http://localhost:3210/v1/chat/completions",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                result = _json.loads(r.read())
                text = result["choices"][0]["message"]["content"].strip()

            # Parse coordinates
            m = re.search(r'\{[^}]+\}', text, re.DOTALL)
            if m:
                coords = _json.loads(m.group())
                x = coords.get("x", 0)
                y = coords.get("y", 0)
                label = coords.get("label", instruction[:20])
                explanation = coords.get("explanation", "")
                print(f"[shadow] AI: {explanation}")
                self.move_to(x, y, label)
                # Notify
                subprocess.Popen([
                    "notify-send", "Echo Shadow",
                    explanation or f"→ {label}",
                    "-t", "3000"
                ])
            else:
                print(f"[shadow] AI returned no coords: {text}")

        except Exception as e:
            print(f"[shadow] AI guide error: {e}")


def ai_mode(instruction):
    """CLI mode: send instruction to running daemon via socket."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("127.0.0.1", SOCKET_PORT))
        s.sendall(json.dumps({"action": "ai", "instruction": instruction}).encode())
        s.close()
        print(f"[shadow] sent: {instruction}")
    except ConnectionRefusedError:
        print("[shadow] daemon not running — start echo_shadow_cursor.py first")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # CLI mode — send to running daemon
        ai_mode(" ".join(sys.argv[1:]))
    else:
        # Daemon mode
        if not os.environ.get("WAYLAND_DISPLAY"):
            print("[shadow] needs Wayland — run inside driftwm")
            sys.exit(1)
        app = ShadowCursor()
        try:
            Gtk.main()
        except KeyboardInterrupt:
            pass
