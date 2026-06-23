#!/usr/bin/env python3
import json, subprocess, sys, os, gi, uuid
from pathlib import Path
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk

ZONES_FILE = os.path.expanduser("~/.config/driftwm/zones.json")
WINDOW_ZONES_FILE = os.path.expanduser("~/.config/driftwm/window_zones.json")

def load_window_zones():
    try:
        return json.loads(Path(WINDOW_ZONES_FILE).read_text()).get("assignments", {})
    except:
        return {}

def save_window_zones(assignments):
    Path(WINDOW_ZONES_FILE).write_text(json.dumps({"assignments": assignments}, indent=2))

def assign_window_to_zone(app_id, zone_id):
    a = load_window_zones()
    if zone_id:
        a[app_id] = zone_id
    else:
        a.pop(app_id, None)
    save_window_zones(a)
CTX_FILE   = "/tmp/echo_ctx_menu.json"
COLORS = ["#3050FF","#20C040","#FF4020","#FFA020","#A020FF","#20FFC0"]
COLOR_NAMES = ["Blue","Green","Red","Orange","Purple","Cyan"]

def load_zones():
    try:
        d = json.loads(Path(ZONES_FILE).read_text())
        return d.get("zones", [])
    except:
        return []

def save_zones(zones):
    Path(ZONES_FILE).write_text(json.dumps({"zones": zones}, indent=2))

def notify(msg):
    subprocess.Popen(["notify-send", "-t", "2000", "Echo", msg],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def ask_text(prompt, default=""):
    dialog = Gtk.Dialog(title="Echo", flags=0)
    dialog.set_keep_above(True)
    dialog.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK,
                       Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
    box = dialog.get_content_area()
    box.set_spacing(8)
    box.set_margin_top(12); box.set_margin_bottom(12)
    box.set_margin_start(16); box.set_margin_end(16)
    label = Gtk.Label(label=prompt)
    label.set_halign(Gtk.Align.START)
    entry = Gtk.Entry()
    entry.set_text(default)
    entry.set_activates_default(True)
    box.add(label)
    box.add(entry)
    dialog.set_default_response(Gtk.ResponseType.OK)
    dialog.show_all()
    resp = dialog.run()
    text = entry.get_text().strip()
    dialog.destroy()
    return text if resp == Gtk.ResponseType.OK else None

def pick_color_dialog(current=None):
    dialog = Gtk.Dialog(title="Zone Color", flags=0)
    dialog.set_keep_above(True)
    dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
    box = dialog.get_content_area()
    box.set_spacing(8)
    box.set_margin_top(12); box.set_margin_bottom(12)
    box.set_margin_start(16); box.set_margin_end(16)
    box.add(Gtk.Label(label="Pick a color:"))
    chosen = [current]
    flow = Gtk.FlowBox()
    flow.set_max_children_per_line(6)
    flow.set_selection_mode(Gtk.SelectionMode.NONE)
    for hex_color, name in zip(COLORS, COLOR_NAMES):
        btn = Gtk.Button(label=name)
        css = Gtk.CssProvider()
        css.load_from_data(("button { background: " + hex_color + "; color: white; font-weight: bold; min-width: 70px; min-height: 36px; }").encode())
        btn.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        def on_click(w, hc=hex_color):
            chosen[0] = hc
            dialog.response(Gtk.ResponseType.OK)
        btn.connect("clicked", on_click)
        flow.add(btn)
    box.add(flow)
    box.add(Gtk.Label(label="— or custom —"))
    custom_btn = Gtk.ColorButton()
    if current:
        rgba = Gdk.RGBA()
        rgba.parse(current)
        custom_btn.set_rgba(rgba)
    box.add(custom_btn)
    ok_btn = Gtk.Button(label="Use custom color")
    def use_custom(w):
        rgba = custom_btn.get_rgba()
        chosen[0] = "#{:02X}{:02X}{:02X}".format(int(rgba.red*255), int(rgba.green*255), int(rgba.blue*255))
        dialog.response(Gtk.ResponseType.OK)
    ok_btn.connect("clicked", use_custom)
    box.add(ok_btn)
    dialog.show_all()
    dialog.run()
    dialog.destroy()
    return chosen[0]

def create_zone(cx, cy, zones):
    name = ask_text("Zone name:", "Zone {}".format(len(zones)+1))
    if not name:
        return
    color = pick_color_dialog()
    new_zone = {
        "id":    str(uuid.uuid4())[:8],
        "name":  name,
        "x":     cx - 640,
        "y":     cy - 360,
        "w":     2560,
        "h":     1440,
        "color": color,
    }
    zones.append(new_zone)
    save_zones(zones)
    notify("Zone '{}' created — restart DriftWM to see it".format(name))

def make_menu(ctx_data):
    menu = Gtk.Menu()
    menu.set_reserve_toggle_size(False)
    context = ctx_data.get("context", "canvas")
    zone_id = ctx_data.get("zone_id", "")
    sel     = ctx_data.get("selected_count", 0)
    cx      = ctx_data.get("x", 0)
    cy      = ctx_data.get("y", 0)
    zones   = load_zones()

    def sep():
        menu.append(Gtk.SeparatorMenuItem())

    def item(label, cb):
        it = Gtk.MenuItem(label=label)
        it.connect("activate", lambda w: cb())
        menu.append(it)

    if context == "zone":
        zone = next((z for z in zones if z["id"] == zone_id), None)
        zname = zone["name"] if zone else zone_id
        title = Gtk.MenuItem(label="Zone: {}".format(zname))
        title.set_sensitive(False)
        menu.append(title)
        sep()
        def rename_zone():
            new_name = ask_text("New zone name:", zname)
            if new_name:
                for z in zones:
                    if z["id"] == zone_id:
                        z["name"] = new_name
                save_zones(zones)
                notify("Zone renamed to {}".format(new_name))
        item("  Rename zone", rename_zone)
        def recolor_zone():
            current = zone.get("color") if zone else None
            new_color = pick_color_dialog(current)
            if new_color:
                for z in zones:
                    if z["id"] == zone_id:
                        z["color"] = new_color
                save_zones(zones)
                notify("Zone color updated")
        item("  Change color", recolor_zone)
        sep()
        def delete_zone():
            zlist = [z for z in zones if z["id"] != zone_id]
            save_zones(zlist)
            notify("Zone '{}' deleted".format(zname))
        item("  Delete zone", delete_zone)

    else:  # canvas
        item("+ New zone here", lambda: create_zone(cx, cy, zones))
        if sel > 1:
            item("  Group {} windows into zone".format(sel), lambda: create_zone(cx, cy, zones))
        sep()
        if zones:
            for z in zones:
                zid = z["id"]
                item("  " + z["name"], lambda zid=zid: notify("Jump to zone: use mod+alt+left/right"))
            sep()

    menu.show_all()
    return menu

def main():
    try:
        ctx_data = json.loads(Path(CTX_FILE).read_text())
    except:
        ctx_data = {"context": "canvas", "x": 0, "y": 0}

    css = Gtk.CssProvider()
    css.load_from_data(b"""
        menu, menuitem {
            background-color: #1a1a2e;
            color: #e0e0ff;
            font-family: monospace;
            font-size: 13px;
            padding: 4px 12px;
        }
        menuitem:hover { background-color: #2a2a5e; color: #ffffff; }
        separator { background-color: #333366; margin: 2px 0; }
    """)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    menu = make_menu(ctx_data)

    def on_deactivate(m):
        Gtk.main_quit()
    menu.connect("deactivate", on_deactivate)

    mx = int(ctx_data.get("screen_x", 0))
    my = int(ctx_data.get("screen_y", 0))
    if mx == 0 and my == 0:
        display = Gdk.Display.get_default()
        seat = display.get_default_seat()
        pointer = seat.get_pointer()
        screen, mx, my = pointer.get_position()
    menu.popup(None, None, lambda m, x, y, data: (mx, my, True), None, 3, 0)
    Gtk.main()

if __name__ == "__main__":
    main()
