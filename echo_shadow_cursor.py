#!/usr/bin/env python3
"""
echo_shadow_cursor.py — Echo ghost cursor (XWayland transparent overlay)
Uses X11 transparent window — works freely across driftwm's infinite canvas.
Socket on :59998. Send JSON commands to control it.
"""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
import cairo, socket, threading, json, sys, os, subprocess, time, math

SOCKET_PORT  = 59998
CURSOR_RADIUS = 18
CURSOR_COLOR  = (0.48, 0.42, 0.97, 0.85)
LABEL_COLOR   = (0.87, 0.65, 0.1, 1.0)
TRAIL_STEPS   = 8
ANIM_MS       = 16
MOVE_SPEED    = 0.18

class ShadowCursor(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)

        # Fullscreen transparent X11 window
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_accept_focus(False)
        self.set_app_paintable(True)
        self.stick()  # show on all workspaces

        # RGBA visual for transparency
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        # Full monitor size
        display = Gdk.Display.get_default()
        monitor = display.get_monitor(0)
        geo = monitor.get_geometry()
        self.W = geo.width
        self.H = geo.height
        self.move(geo.x, geo.y)
        self.set_default_size(self.W, self.H)
        self.resize(self.W, self.H)

        # Pass all input through
        self.input_shape_combine_region(cairo.Region())

        # State
        self.cur_x = self.W / 2
        self.cur_y = self.H / 2
        self.target_x = self.W / 2
        self.target_y = self.H / 2
        self.label    = ""
        self.visible  = False
        self.trail    = []
        self.hide_timer = None
        self.pulse    = 0.0
        self.follow_mode = False

        # Drawing area
        self.da = Gtk.DrawingArea()
        self.da.connect("draw", self._draw)
        self.da.input_shape_combine_region(cairo.Region())
        self.add(self.da)
        self.show_all()

        # Animation + follow loop
        GLib.timeout_add(ANIM_MS, self._animate)

        # Socket server
        threading.Thread(target=self._socket_server, daemon=True).start()
        print("[shadow] Ghost cursor ready on :59998")

    def _draw(self, widget, cr):
        # Always clear to fully transparent
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()

        if not self.visible:
            return

        cr.set_operator(cairo.OPERATOR_OVER)
        x, y, p = self.cur_x, self.cur_y, self.pulse

        # Trail
        for i, (tx, ty, _) in enumerate(self.trail):
            r = 3 * ((i + 1) / max(len(self.trail), 1))
            cr.arc(tx, ty, max(r, 1), 0, 2 * math.pi)
            cr.set_source_rgba(0.87, 0.65, 0.1, 0.15 * (i / max(len(self.trail), 1)))
            cr.fill()

        # Glow
        for gr in [22, 16]:
            cr.arc(x, y, gr, 0, 2 * math.pi)
            cr.set_source_rgba(0.44, 0.19, 0.82, 0.08)
            cr.fill()

        # Wings
        wscale = 0.65 + 0.35 * abs(math.sin(p * 2 * math.pi * 1.9))
        wyoff  = 2 * math.sin(p * 2 * math.pi * 1.9)
        for side in [-1, 1]:
            cr.save()
            cr.translate(x + side * 2, y + 4 + wyoff)
            cr.scale(wscale * side, 1.0)
            cr.move_to(0, 0)
            cr.line_to(-20, -15)
            cr.line_to(-20, 7)
            cr.close_path()
            cr.set_source_rgba(0.91, 0.63, 0.0, 0.85)
            cr.fill()
            cr.restore()

        # Body
        cr.arc(x, y, 14, 0, 2 * math.pi)
        cr.set_source_rgba(0.027, 0.027, 0.102, 1.0)
        cr.fill()
        cr.arc(x, y, 14, 0, 2 * math.pi)
        cr.set_source_rgba(0.1, 0.09, 0.38, 1.0)
        cr.set_line_width(1.2)
        cr.stroke()

        # Eye
        ep = 0.4 + 0.5 * abs(math.sin(p * 2 * math.pi * 0.33))
        cr.arc(x, y, 10, 0, 2 * math.pi)
        cr.set_source_rgba(0.93, 0.93, 1.0, 1.0)
        cr.fill()
        cr.arc(x, y, 14, 0, 2 * math.pi)
        cr.set_source_rgba(0.63, 0.38, 1.0, ep * 0.2)
        cr.fill()

        # Diamond iris
        cr.save()
        cr.translate(x, y)
        cr.rotate(math.pi / 4)
        cr.rectangle(-6, -6, 12, 12)
        cr.set_source_rgba(0.44, 0.19, 0.82, 1.0)
        cr.fill()
        cr.rectangle(-3, -3, 6, 6)
        cr.set_source_rgba(0.63, 0.38, 1.0, 0.9)
        cr.fill()
        cr.restore()

        # Halo
        hglow = 0.6 + 0.4 * math.sin(p * 2 * math.pi * 0.25)
        cr.arc(x, y - 18, 10, 0, 2 * math.pi)
        cr.set_source_rgba(0.91, 0.63, 0.0, 0.0)
        cr.fill()
        cr.set_line_width(2.5)
        cr.arc(x, y - 18, 11, 0, 2 * math.pi)
        cr.set_source_rgba(0.91, 0.63, 0.0, hglow * 0.85)
        cr.stroke()
        # Halo glow
        cr.arc(x, y - 18, 13, 0, 2 * math.pi)
        cr.set_source_rgba(0.91, 0.63, 0.0, hglow * 0.2)
        cr.stroke()

        # Tail
        bob = 3 * math.sin(p * 2 * math.pi * 0.95)
        cr.save()
        cr.translate(x + 11, y + 8 + bob)
        for side in [-1, 1]:
            cr.move_to(0, 0)
            cr.line_to(side * 8, -5)
            cr.line_to(side * 8, 3)
            cr.close_path()
            cr.set_source_rgba(0.1, 0.38, 0.25, 0.9)
            cr.fill()
        cr.arc(0, 2, 2, 0, 2 * math.pi)
        cr.set_source_rgba(0.0, 0.85, 0.4, 1.0)
        cr.fill()
        cr.restore()

        # Label
        if self.label:
            cr.select_font_face("JetBrains Mono", cairo.FONT_SLANT_NORMAL,
                                cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(11)
            ext = cr.text_extents(self.label)
            pad, lx, ly = 6, x + 22, y - 8
            cr.rectangle(lx - pad, ly - ext.height - pad/2,
                         ext.width + pad*2, ext.height + pad)
            cr.set_source_rgba(0.07, 0.07, 0.12, 0.9)
            cr.fill()
            cr.move_to(lx, ly)
            cr.set_source_rgba(*LABEL_COLOR)
            cr.show_text(self.label)

    def _animate(self):
        if self.follow_mode:
            try:
                r = subprocess.run(
                    ["xdotool", "getmouselocation", "--shell"],
                    capture_output=True, text=True, timeout=0.05
                )
                mx = my = 0
                for line in r.stdout.splitlines():
                    if line.startswith("X="): mx = int(line.split("=")[1])
                    if line.startswith("Y="): my = int(line.split("=")[1])
                self.target_x = mx + 28
                self.target_y = my + 28
                self.visible = True
            except: pass

        dx = self.target_x - self.cur_x
        dy = self.target_y - self.cur_y
        if (dx**2 + dy**2) > 2:
            self.trail.append((self.cur_x, self.cur_y, 1.0))
            if len(self.trail) > TRAIL_STEPS:
                self.trail.pop(0)
            self.cur_x += dx * MOVE_SPEED
            self.cur_y += dy * MOVE_SPEED
        else:
            self.trail = []

        self.pulse = (self.pulse + 0.015) % 1.0
        if self.visible:
            self.da.queue_draw()
        return True

    def move_to(self, x, y, label=""):
        def _do():
            self.target_x = float(x)
            self.target_y = float(y)
            self.label = label
            self.visible = True
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
            time.sleep(0.6)
            subprocess.run(["xdotool", "mousemove", str(int(x)), str(int(y))])
            time.sleep(0.1)
            subprocess.run(["xdotool", "click", "1"])
        threading.Thread(target=_click, daemon=True).start()

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
                self._handle(data)
            except Exception as e:
                print(f"[shadow] socket error: {e}")

    def _handle(self, data):
        try:
            cmd = json.loads(data)
            action = cmd.get("action", "move")
            if action == "follow":
                enabled = cmd.get("enabled", True)
                def _set(e=enabled):
                    self.follow_mode = e
                    if not e: self._hide()
                GLib.idle_add(_set)
            elif action == "hide":
                GLib.idle_add(self._hide)
            elif action == "click":
                self.click_at(cmd.get("x",0), cmd.get("y",0), cmd.get("label",""))
            elif action == "ai":
                threading.Thread(
                    target=self._ai_guide,
                    args=(cmd.get("instruction",""),), daemon=True
                ).start()
            else:
                self.move_to(cmd.get("x",0), cmd.get("y",0), cmd.get("label",""))
        except Exception as e:
            print(f"[shadow] handle error: {e}")

    def _ai_guide(self, instruction):
        try:
            import tempfile, base64, urllib.request, json as _json, re
            tmp = tempfile.mktemp(suffix=".png")
            subprocess.run(["grim", tmp], capture_output=True)
            with open(tmp,"rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            os.unlink(tmp)
            prompt = f"""Screenshot is {self.W}x{self.H}px.
User wants: "{instruction}"
Return ONLY JSON: {{"x":123,"y":456,"label":"name","explanation":"one sentence"}}"""
            payload = _json.dumps({
                "model": "gemini-2.0-flash",
                "messages": [{"role":"user","content":[
                    {"type":"text","text":prompt},
                    {"type":"image_url","image_url":{"url":f"data:image/png;base64,{img_b64}"}}
                ]}]
            }).encode()
            req = urllib.request.Request(
                "http://localhost:3210/v1/chat/completions",
                data=payload, headers={"Content-Type":"application/json"}
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                result = _json.loads(r.read())
                text = result["choices"][0]["message"]["content"].strip()
            m = re.search(r'\{[^}]+\}', text, re.DOTALL)
            if m:
                c = _json.loads(m.group())
                self.move_to(c.get("x",0), c.get("y",0), c.get("label",""))
                subprocess.Popen(["notify-send","Echo Shadow",
                    c.get("explanation",""), "-t","3000"])
        except Exception as e:
            print(f"[shadow] AI error: {e}")


def ai_mode(instruction):
    try:
        s = socket.socket()
        s.connect(("127.0.0.1", SOCKET_PORT))
        s.sendall(json.dumps({"action":"ai","instruction":instruction}).encode())
        s.close()
    except ConnectionRefusedError:
        print("[shadow] daemon not running")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        ai_mode(" ".join(sys.argv[1:]))
    else:
        app = ShadowCursor()
        try:
            Gtk.main()
        except KeyboardInterrupt:
            pass
