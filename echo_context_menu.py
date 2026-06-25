#!/usr/bin/env python3
import json, subprocess, os, uuid, fcntl, sys
from pathlib import Path
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

_lock_fh = open("/tmp/echo_ctx_menu.lock", "w")
try:
    fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
except:
    sys.exit(0)

ZONES_FILE = os.path.expanduser("~/.config/driftwm/zones.json")
CTX_FILE = "/tmp/echo_ctx_menu.json"
ECHO_MODE_FILE = "/tmp/echo_mode.json"
COLORS = {"Blue":"#3050FF","Green":"#20C040","Red":"#FF4020",
          "Orange":"#FFA020","Purple":"#A020FF","Cyan":"#20FFC0"}

def load_zones():
    try: return json.loads(Path(ZONES_FILE).read_text()).get("zones",[])
    except: return []

def save_zones(z):
    Path(ZONES_FILE).write_text(json.dumps({"zones":z},indent=2))

def notify(msg):
    subprocess.Popen(["notify-send","-t","2000","Echo",msg],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def reload_zones_in_driftwm():
    try: Path(ZONES_FILE).touch()
    except: pass

def pick_color(current="#3050FF"):
    d = Gtk.Dialog(title="Pick color", flags=0)
    d.set_keep_above(True)
    b = d.get_content_area()
    b.set_margin_top(12); b.set_margin_bottom(12)
    b.set_margin_start(12); b.set_margin_end(12); b.set_spacing(8)
    b.add(Gtk.Label(label="Pick color:"))
    chosen = [current]
    flow = Gtk.FlowBox()
    flow.set_max_children_per_line(3)
    flow.set_selection_mode(Gtk.SelectionMode.NONE)
    for n, hc in COLORS.items():
        btn = Gtk.Button(label=n)
        css = Gtk.CssProvider()
        css.load_from_data(
            "button{{background:{};color:white;min-width:80px;min-height:36px;}}".format(hc).encode())
        btn.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        def clk(w, h=hc): chosen[0] = h; d.response(Gtk.ResponseType.OK)
        btn.connect("clicked", clk)
        flow.add(btn)
    b.add(flow)
    d.add_button("Skip", Gtk.ResponseType.CANCEL)
    d.show_all()
    d.run()
    d.destroy()
    return chosen[0]

def run_action(action, ctx_data):
    zones = load_zones()
    zone_id = ctx_data.get("zone_id", "")
    cx = ctx_data.get("x", 0)
    cy = ctx_data.get("y", 0)

    if action == "new_zone":
        d = Gtk.Dialog(title="New Zone", flags=0)
        d.set_keep_above(True)
        d.set_default_size(300, 100)
        b = d.get_content_area()
        b.set_margin_top(12); b.set_margin_bottom(12)
        b.set_margin_start(12); b.set_margin_end(12); b.set_spacing(8)
        b.add(Gtk.Label(label="Zone name:"))
        e = Gtk.Entry(); e.set_text("Zone {}".format(len(zones)+1))
        e.set_activates_default(True)
        b.add(e)
        d.add_button("Cancel", Gtk.ResponseType.CANCEL)
        d.add_button("OK", Gtk.ResponseType.OK)
        d.set_default_response(Gtk.ResponseType.OK)
        d.show_all()
        resp = d.run()
        name = e.get_text().strip()
        d.destroy()
        if resp != Gtk.ResponseType.OK or not name:
            return
        color = pick_color(current="#3050FF")
        zones.append({"id": str(__import__("uuid").uuid4())[:8], "name": name,
            "x": cx-640, "y": cy-360, "w": 2560, "h": 1440, "color": color})
        save_zones(zones)
        reload_zones_in_driftwm()
        notify("Zone '{}' created".format(name))

    elif action == "goto_zone":
        target_id = ctx_data.get("goto_zone_id", "")
        zone = next((z for z in zones if z["id"] == target_id), None)
        if not zone: return
        nav = {"action": "goto_zone", "zone_id": target_id,
               "x": zone["x"], "y": zone["y"], "w": zone["w"], "h": zone["h"]}
        Path("/tmp/echo_nav.json").write_text(__import__("json").dumps(nav))
        notify("-> {}".format(zone["name"]))

    elif action == "delete":
        zone = next((z for z in zones if z["id"] == zone_id), None)
        if not zone: return
        save_zones([z for z in zones if z["id"] != zone_id])
        reload_zones_in_driftwm()
        notify("Zone '{}' deleted".format(zone["name"]))

    elif action == "rename":
        zone = next((z for z in zones if z["id"] == zone_id), None)
        if not zone: return
        d = Gtk.Dialog(title="Rename", flags=0)
        d.set_keep_above(True)
        b = d.get_content_area()
        b.set_margin_top(12); b.set_margin_bottom(12)
        b.set_margin_start(12); b.set_margin_end(12); b.set_spacing(8)
        b.add(Gtk.Label(label="New name:"))
        e = Gtk.Entry(); e.set_text(zone["name"])
        e.set_activates_default(True)
        b.add(e)
        d.add_button("Cancel", Gtk.ResponseType.CANCEL)
        d.add_button("OK", Gtk.ResponseType.OK)
        d.set_default_response(Gtk.ResponseType.OK)
        d.show_all()
        resp = d.run()
        name = e.get_text().strip()
        d.destroy()
        if resp == Gtk.ResponseType.OK and name:
            zone["name"] = name
            save_zones(zones)
            reload_zones_in_driftwm()
            notify("Renamed to {}".format(name))

    elif action == "add_selected":
        target_id = ctx_data.get("add_zone_id", "")
        selected_ids = ctx_data.get("selected_app_ids", [])
        if not target_id or not selected_ids: return
        zone = next((z for z in zones if z["id"] == target_id), None)
        if not zone: return
        members = zone.get("members", [])
        added = []
        for app_id in selected_ids:
            if app_id not in members:
                members.append(app_id)
                added.append(app_id)
        zone["members"] = members
        save_zones(zones)
        reload_zones_in_driftwm()
        # Snap all added windows into zone with offsets
        import json as _json
        for i, app_id in enumerate(added):
            snap = {"action": "snap_to_zone", "app_id": app_id,
                    "zone_x": zone["x"] + i * 40, "zone_y": zone["y"] + i * 40,
                    "zone_w": zone["w"], "zone_h": zone["h"]}
            Path("/tmp/echo_snap.json").write_text(_json.dumps(snap))
            import time; time.sleep(0.25)
        notify("{} windows -> {}".format(len(added), zone["name"]))

    elif action == "add_to_zone":
        target_id = ctx_data.get("add_zone_id", "")
        app_id = ctx_data.get("window_app_id", "")
        if not target_id or not app_id: return
        zone = next((z for z in zones if z["id"] == target_id), None)
        if not zone: return
        members = zone.get("members", [])
        if app_id not in members:
            members.append(app_id)
            zone["members"] = members
            save_zones(zones)
            reload_zones_in_driftwm()
            # Snap window into zone
            import json as _json
            snap = {"action": "snap_to_zone", "app_id": app_id,
                    "zone_x": zone["x"], "zone_y": zone["y"],
                    "zone_w": zone["w"], "zone_h": zone["h"]}
            Path("/tmp/echo_snap.json").write_text(_json.dumps(snap))
            notify("'{}' -> {}".format(app_id, zone["name"]))

    elif action == "remove_from_zone":
        app_id = ctx_data.get("window_app_id", "")
        if not app_id: return
        changed = False
        for z in zones:
            if app_id in z.get("members", []):
                z["members"] = [m for m in z["members"] if m != app_id]
                changed = True
        if changed:
            save_zones(zones)
            reload_zones_in_driftwm()
            notify("'{}' removed from zone".format(app_id))

    elif action == "recolor":
        zone = next((z for z in zones if z["id"] == zone_id), None)
        if not zone: return
        color = pick_color(current=zone.get("color", "#3050FF"))
        zone["color"] = color
        save_zones(zones)
        reload_zones_in_driftwm()
        notify("Color updated")

    elif action == "echo_idle":
        import json as _j
        # Read current cursor canvas pos from echo_pos.json if available
        try:
            pos = _j.loads(Path("/tmp/echo_pos.json").read_text())
            fx, fy = pos.get("canvas_x", 0.0), pos.get("canvas_y", 0.0)
        except:
            fx, fy = 0.0, 0.0
        Path(ECHO_MODE_FILE).write_text(_j.dumps({
            "mode": "idle", "orbit": True,
            "frozen_x": fx, "frozen_y": fy
        }))
        notify("Echo: Idle — zones orbit")

    elif action == "echo_free_roam":
        import json as _j
        Path(ECHO_MODE_FILE).write_text(_j.dumps({"mode": "free_roam", "orbit": False}))
        notify("Echo: Free Roam")

    elif action == "echo_follow":
        import json as _j
        Path(ECHO_MODE_FILE).write_text(_j.dumps({"mode": "follow_cursor", "orbit": False}))
        notify("Echo: Following cursor")

    elif action == "talk_to_echo":
        import shutil
        # Ensure wake_word.py is running
        result = subprocess.run(["pgrep", "-f", "wake_word.py"], capture_output=True)
        if result.returncode != 0:
            subprocess.Popen(
                ["/home/jesus999l/vision_env/bin/python3",
                 "/home/jesus999l/vision_assistant/wake_word.py"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            notify("Echo: Wake word started — listening")
        else:
            notify("Echo: Listening (wake word active)")
        Path("/tmp/echo_wake_trigger").touch()

def main():
    try: ctx_data = __import__("json").loads(Path(CTX_FILE).read_text())
    except: ctx_data = {"context": "canvas", "x": 0, "y": 0}

    ctx = ctx_data.get("context", "canvas")
    zone_id = ctx_data.get("zone_id", "")
    sel = ctx_data.get("selected_count", 0)
    zones = load_zones()

    items = []

    if ctx == "window":
        app_id = ctx_data.get("window_app_id", "")
        win_title = ctx_data.get("window_title", "") or app_id or "Window"
        title = win_title[:30]
        # Find which zone this window already belongs to
        current_zone = next((z for z in zones if app_id and app_id in z.get("members",[])), None)
        if current_zone:
            items.append(("  In: {}".format(current_zone["name"]), None, current_zone.get("color","#888")))
            items.append(("", None, None))
            items.append(("  Remove from zone", "remove_from_zone", None))
        else:
            items.append(("  Add to zone:", None, None))
            for z in zones:
                items.append(("    {}".format(z["name"]), "add_to_zone:{}".format(z["id"]), z.get("color","#888")))
        if zones:
            items.append(("", None, None))
        items.append(("  New zone here", "new_zone", None))
    elif ctx == "zone":
        zone = next((z for z in zones if z["id"] == zone_id), None)
        zname = zone["name"] if zone else zone_id
        title = "Zone: {}".format(zname)
        items = [
            ("  Rename zone", "rename", None),
            ("  Change color", "recolor", None),
            ("  Delete zone", "delete", None),
        ]
    else:
        title = "Echo"
        selected_ids = ctx_data.get("selected_app_ids", [])
        if selected_ids and zones:
            # Has selection — show "add to zone" for each zone
            items.append(("  Add {} selected to:".format(len(selected_ids)), None, None))
            for z in zones:
                items.append(("    {}".format(z["name"]), "add_selected:{}".format(z["id"]), z.get("color","#888")))
            items.append(("", None, None))
        else:
            for z in zones:
                items.append(("  {}".format(z["name"]), "goto_zone:{}".format(z["id"]), z.get("color","#888")))
            if zones:
                items.append(("", None, None))
        items.append(("  New zone here", "new_zone", None))
        if sel > 1 and not selected_ids:
            items.append(("  Group {} windows into zone".format(sel), "new_zone", None))
        items.append(("", None, None))
        items.append(("  ── Echo ──", None, None))
        items.append(("  Echo Idle", "echo_idle", "#A020FF"))
        items.append(("  Echo Free Roam", "echo_free_roam", "#20C0FF"))
        items.append(("  Echo Follow Cursor", "echo_follow", "#20FFC0"))
        items.append(("  Talk to Echo", "talk_to_echo", "#FF80FF"))

    d = Gtk.Dialog(title=title, flags=0)
    d.set_keep_above(True)
    real_count = sum(1 for item in items if item[1] is not None)
    d.set_default_size(260, 56 + real_count * 44)
    box = d.get_content_area()
    box.set_spacing(0)

    css_prov = Gtk.CssProvider()
    css_prov.load_from_data(b"""
        dialog { background: #12121e; }
        .menu-btn { background: transparent; color: #d0d0f0;
                    border: none; padding: 10px 18px; font-size: 13px; }
        .menu-btn:hover { background: #22224a; }
        .sep-lbl { color: #444; font-size: 10px; padding: 2px 18px; }
    """)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), css_prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    chosen_action = [None]

    for item in items:
        label, key, color = item
        if key is None:
            sep = Gtk.Label(label="---")
            sep.get_style_context().add_class("sep-lbl")
            sep.set_halign(Gtk.Align.START)
            box.pack_start(sep, False, False, 0)
            continue

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.set_margin_start(4)

        if color:
            dot = Gtk.Label(label="●")
            dot_css = Gtk.CssProvider()
            dot_css.load_from_data("label {{ color: {}; font-size: 14px; }}".format(color).encode())
            dot.get_style_context().add_provider(dot_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            row.pack_start(dot, False, False, 0)

        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        row.pack_start(lbl, True, True, 0)

        btn = Gtk.Button()
        btn.add(row)
        btn.get_style_context().add_class("menu-btn")
        btn.set_relief(Gtk.ReliefStyle.NONE)
        def click(w, k=key):
            chosen_action[0] = k
            d.response(Gtk.ResponseType.OK)
        btn.connect("clicked", click)
        box.pack_start(btn, False, False, 0)

    d.show_all()

    mx = int(ctx_data.get("screen_x", 0))
    my = int(ctx_data.get("screen_y", 0))
    if mx == 0 and my == 0:
        display = Gdk.Display.get_default()
        seat = display.get_default_seat()
        ptr = seat.get_pointer()
        _screen, mx, my = ptr.get_position()
    d.move(mx, my)
    d.run()
    d.destroy()

    if chosen_action[0]:
        act = chosen_action[0]
        if act.startswith("goto_zone:"):
            ctx_data["goto_zone_id"] = act.split(":", 1)[1]
            run_action("goto_zone", ctx_data)
        elif act.startswith("add_to_zone:"):
            ctx_data["add_zone_id"] = act.split(":", 1)[1]
            run_action("add_to_zone", ctx_data)
        elif act.startswith("add_selected:"):
            ctx_data["add_zone_id"] = act.split(":", 1)[1]
            run_action("add_selected", ctx_data)
        elif act in ("echo_idle", "echo_free_roam", "echo_follow", "talk_to_echo"):
            run_action(act, ctx_data)
        else:
            run_action(act, ctx_data)

if __name__ == "__main__":
    main()
