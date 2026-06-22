#!/usr/bin/env python3
"""Echo right-click context menu — zones, grouping, window actions."""
import json, subprocess, os
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk

ZONES_PATH = os.path.expanduser("~/.config/driftwm/zones.json")
CONTEXT_PATH = "/tmp/echo_context.json"

ZONE_COLORS = [
    ("#7c6af7", "Purple"),
    ("#20b0e0", "Cyan"),
    ("#20e080", "Green"),
    ("#e08020", "Orange"),
    ("#e04060", "Red"),
    ("#e0c020", "Gold"),
]

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
    os.makedirs(os.path.dirname(ZONES_PATH), exist_ok=True)
    open(ZONES_PATH, "w").write(json.dumps({"zones": zones}, indent=2))

def show_zone_dialog(parent_title="New Zone"):
    dialog = Gtk.Dialog(title=parent_title)
    dialog.set_default_size(320, 200)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Create", Gtk.ResponseType.OK)

    box = dialog.get_content_area()
    box.set_spacing(8)
    box.set_margin_start(16)
    box.set_margin_end(16)
    box.set_margin_top(16)
    box.set_margin_bottom(16)

    # Name
    name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    name_box.pack_start(Gtk.Label(label="Name:"), False, False, 0)
    name_entry = Gtk.Entry()
    name_entry.set_text("Zone 1")
    name_box.pack_start(name_entry, True, True, 0)
    box.pack_start(name_box, False, False, 0)

    # Color picker
    color_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    color_box.pack_start(Gtk.Label(label="Color:"), False, False, 0)
    selected_color = [ZONE_COLORS[0][0]]
    buttons = []
    for hex_color, name in ZONE_COLORS:
        btn = Gtk.Button(label=name)
        rgba = Gdk.RGBA()
        rgba.parse(hex_color)
        btn.override_background_color(Gtk.StateFlags.NORMAL, rgba)
        def on_color(b, hc=hex_color, btns=buttons, sc=selected_color):
            sc[0] = hc
            for bb in btns:
                bb.set_relief(Gtk.ReliefStyle.NONE)
            b.set_relief(Gtk.ReliefStyle.NORMAL)
        btn.connect("clicked", on_color)
        btn.set_relief(Gtk.ReliefStyle.NONE)
        buttons.append(btn)
        color_box.pack_start(btn, False, False, 0)
    buttons[0].set_relief(Gtk.ReliefStyle.NORMAL)
    box.pack_start(color_box, False, False, 0)

    box.show_all()
    response = dialog.run()
    name = name_entry.get_text().strip() or "Zone"
    color = selected_color[0]
    dialog.destroy()
    return (name, color) if response == Gtk.ResponseType.OK else None

def main():
    ctx = load_context()
    selected = ctx.get("selected", [])
    zones = load_zones()

    menu = Gtk.Menu()
    menu.set_name("echo-context-menu")

    # Style
    css = Gtk.CssProvider()
    css.load_from_data(b"""
        #echo-context-menu { background: #1a1a2e; border: 1px solid #7c6af7; }
        #echo-context-menu menuitem { color: #e0e0ff; padding: 6px 16px; }
        #echo-context-menu menuitem:hover { background: #7c6af7; }
        #echo-context-menu separator { background: #333355; margin: 2px 8px; }
    """)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), css,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

    if selected:
        lbl = Gtk.MenuItem(label=f"  {len(selected)} selected")
        lbl.set_sensitive(False)
        menu.append(lbl)
        menu.append(Gtk.SeparatorMenuItem())

        # Send to existing zone
        if zones:
            zone_item = Gtk.MenuItem(label="Send to zone →")
            zone_sub = Gtk.Menu()
            for z in zones:
                zi = Gtk.MenuItem(label=z["name"])
                def on_zone(_, zid=z["id"], titles=[w["title"] for w in selected]):
                    asn = {}
                    try: asn = json.loads(open("/tmp/echo_zone_assignments.json").read())
                    except: pass
                    for t in titles: asn[t] = zid
                    open("/tmp/echo_zone_assignments.json","w").write(json.dumps(asn))
                zi.connect("activate", on_zone)
                zone_sub.append(zi)
            zone_item.set_submenu(zone_sub)
            menu.append(zone_item)

        # Create zone from selection
        def on_new_from_sel(_):
            result = show_zone_dialog("New Zone from Selection")
            if result:
                name, color = result
                new_id = name.lower().replace(" ", "_")
                zones.append({"id": new_id, "name": name, "color": color,
                              "x": -500.0, "y": -300.0, "w": 2560.0, "h": 1440.0})
                save_zones(zones)
        ni = Gtk.MenuItem(label="Create zone from selection")
        ni.connect("activate", on_new_from_sel)
        menu.append(ni)

        menu.append(Gtk.SeparatorMenuItem())

        # Close window
        if len(selected) == 1:
            title = selected[0].get("title","")
            def on_close(_):
                subprocess.Popen(["wlrctl","toplevel","close",f"title:{title}"])
            ci = Gtk.MenuItem(label="Close window")
            ci.connect("activate", on_close)
            menu.append(ci)

    # New zone here
    menu.append(Gtk.SeparatorMenuItem())
    def on_new_zone(_):
        result = show_zone_dialog("New Zone")
        if result:
            name, color = result
            new_id = name.lower().replace(" ", "_")
            zones.append({"id": new_id, "name": name, "color": color,
                          "x": -500.0, "y": -300.0, "w": 2560.0, "h": 1440.0})
            save_zones(zones)
    nzi = Gtk.MenuItem(label="New zone...")
    nzi.connect("activate", on_new_zone)
    menu.append(nzi)

    menu.show_all()
    menu.connect("deactivate", Gtk.main_quit)
    menu.popup_at_pointer(None)
    Gtk.main()

if __name__ == "__main__":
    main()
