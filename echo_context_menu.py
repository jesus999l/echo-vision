#!/usr/bin/env python3
"""Echo right-click context menu — zones, grouping, window actions."""
import json, subprocess, sys, os
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk

ZONES_PATH = os.path.expanduser("~/.config/driftwm/zones.json")
CONTEXT_PATH = "/tmp/echo_context.json"

def load_context():
    try:
        return json.loads(open(CONTEXT_PATH).read())
    except:
        return {"selected": [], "zones": []}

def load_zones():
    try:
        return json.loads(open(ZONES_PATH).read()).get("zones", [])
    except:
        return []

def save_zones(zones):
    open(ZONES_PATH, "w").write(json.dumps({"zones": zones}, indent=2))

def wlrctl(args):
    subprocess.Popen(["wlrctl"] + args)

def main():
    ctx = load_context()
    selected = ctx.get("selected", [])
    zones = load_zones()

    menu = Gtk.Menu()

    # Header
    if selected:
        lbl = Gtk.MenuItem(label=f"  {len(selected)} window(s) selected")
        lbl.set_sensitive(False)
        menu.append(lbl)
        menu.append(Gtk.SeparatorMenuItem())

    # Send to zone
    if zones:
        if selected:
            zone_item = Gtk.MenuItem(label="Send to zone →")
            zone_sub = Gtk.Menu()
            for z in zones:
                zi = Gtk.MenuItem(label=z["name"])
                zid = z["id"]
                titles = [w["title"] for w in selected]
                def on_zone(_, zid=zid, titles=titles):
                    # Write zone assignment
                    assignments = {}
                    try:
                        assignments = json.loads(open("/tmp/echo_zone_assignments.json").read())
                    except:
                        pass
                    for t in titles:
                        assignments[t] = zid
                    open("/tmp/echo_zone_assignments.json", "w").write(json.dumps(assignments))
                zi.connect("activate", on_zone)
                zone_sub.append(zi)
            zone_item.set_submenu(zone_sub)
            menu.append(zone_item)

    # Create new zone from selection
    if selected:
        def on_new_zone(_):
            name = f"Zone {len(zones)+1}"
            new_id = f"zone_{len(zones)+1}"
            zones.append({"id": new_id, "name": name, "x": -500.0, "y": -300.0, "w": 2560.0, "h": 1440.0})
            save_zones(zones)
        ni = Gtk.MenuItem(label="Create zone from selection")
        ni.connect("activate", on_new_zone)
        menu.append(ni)
        menu.append(Gtk.SeparatorMenuItem())

    # Window actions (single window)
    if len(selected) == 1:
        w = selected[0]
        title = w.get("title", "")
        def on_close(_):
            subprocess.Popen(["wlrctl", "toplevel", "close", f"title:{title}"])
        ci = Gtk.MenuItem(label="Close window")
        ci.connect("activate", on_close)
        menu.append(ci)

    # Canvas actions
    menu.append(Gtk.SeparatorMenuItem())
    def on_new_zone_here(_):
        name = f"Zone {len(zones)+1}"
        new_id = f"zone_{len(zones)+1}"
        zones.append({"id": new_id, "name": name, "x": -500.0, "y": -300.0, "w": 2560.0, "h": 1440.0})
        save_zones(zones)
    nzi = Gtk.MenuItem(label="New zone here")
    nzi.connect("activate", on_new_zone_here)
    menu.append(nzi)

    menu.show_all()
    menu.connect("deactivate", Gtk.main_quit)

    display = Gdk.Display.get_default()
    seat = display.get_default_seat()
    ptr = seat.get_pointer()
    _, x, y = ptr.get_position()
    menu.popup_at_rect(
        Gdk.Screen.get_default().get_root_window(),
        Gdk.Rectangle(),
        Gdk.Gravity.NORTH_WEST, Gdk.Gravity.NORTH_WEST,
        None
    )
    Gtk.main()

if __name__ == "__main__":
    main()
