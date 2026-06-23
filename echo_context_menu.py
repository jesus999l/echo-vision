#!/usr/bin/env python3
import json, subprocess, os, uuid
from pathlib import Path
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

ZONES_FILE = os.path.expanduser("~/.config/driftwm/zones.json")
CTX_FILE = "/tmp/echo_ctx_menu.json"
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

def run_action(action, ctx_data):
    zones = load_zones()
    zone_id = ctx_data.get("zone_id","")
    cx = ctx_data.get("x",0)
    cy = ctx_data.get("y",0)

    if action == "new_zone":
        # Name dialog
        d = Gtk.Dialog(title="New Zone",flags=0)
        d.set_keep_above(True)
        d.set_default_size(300,100)
        b = d.get_content_area()
        b.set_margin_top(12);b.set_margin_bottom(12)
        b.set_margin_start(12);b.set_margin_end(12);b.set_spacing(8)
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
        # Color dialog
        d2 = Gtk.Dialog(title="Color",flags=0)
        d2.set_keep_above(True)
        b2 = d2.get_content_area()
        b2.set_margin_top(12);b2.set_margin_bottom(12)
        b2.set_margin_start(12);b2.set_margin_end(12);b2.set_spacing(8)
        b2.add(Gtk.Label(label="Pick color:"))
        chosen = ["#3050FF"]
        flow = Gtk.FlowBox()
        flow.set_max_children_per_line(3)
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        for n,hc in COLORS.items():
            btn = Gtk.Button(label=n)
            css = Gtk.CssProvider()
            css.load_from_data("button{{background:{};color:white;min-width:80px;min-height:36px;}}".format(hc).encode())
            btn.get_style_context().add_provider(css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            def clk(w,h=hc): chosen[0]=h; d2.response(Gtk.ResponseType.OK)
            btn.connect("clicked",clk)
            flow.add(btn)
        b2.add(flow)
        d2.add_button("Skip",Gtk.ResponseType.CANCEL)
        d2.show_all()
        d2.run()
        color = chosen[0]
        d2.destroy()
        zones.append({"id":str(uuid.uuid4())[:8],"name":name,
            "x":cx-640,"y":cy-360,"w":2560,"h":1440,"color":color})
        save_zones(zones)
        notify("Zone '{}' created".format(name))

    elif action == "delete":
        zone = next((z for z in zones if z["id"]==zone_id),None)
        if not zone: return
        save_zones([z for z in zones if z["id"]!=zone_id])
        notify("Zone '{}' deleted".format(zone["name"]))

    elif action == "rename":
        zone = next((z for z in zones if z["id"]==zone_id),None)
        if not zone: return
        d = Gtk.Dialog(title="Rename",flags=0)
        d.set_keep_above(True)
        b = d.get_content_area()
        b.set_margin_top(12);b.set_margin_bottom(12)
        b.set_margin_start(12);b.set_margin_end(12);b.set_spacing(8)
        b.add(Gtk.Label(label="New name:"))
        e = Gtk.Entry(); e.set_text(zone["name"])
        e.set_activates_default(True)
        b.add(e)
        d.add_button("Cancel",Gtk.ResponseType.CANCEL)
        d.add_button("OK",Gtk.ResponseType.OK)
        d.set_default_response(Gtk.ResponseType.OK)
        d.show_all()
        resp = d.run()
        name = e.get_text().strip()
        d.destroy()
        if resp == Gtk.ResponseType.OK and name:
            zone["name"] = name
            save_zones(zones)
            notify("Renamed to {}".format(name))

    elif action == "recolor":
        zone = next((z for z in zones if z["id"]==zone_id),None)
        if not zone: return
        d2 = Gtk.Dialog(title="Color",flags=0)
        d2.set_keep_above(True)
        b2 = d2.get_content_area()
        b2.set_margin_top(12);b2.set_margin_bottom(12)
        b2.set_margin_start(12);b2.set_margin_end(12);b2.set_spacing(8)
        b2.add(Gtk.Label(label="Pick color:"))
        chosen = [zone.get("color","#3050FF")]
        flow = Gtk.FlowBox()
        flow.set_max_children_per_line(3)
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        for n,hc in COLORS.items():
            btn = Gtk.Button(label=n)
            css = Gtk.CssProvider()
            css.load_from_data("button{{background:{};color:white;min-width:80px;min-height:36px;}}".format(hc).encode())
            btn.get_style_context().add_provider(css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            def clk(w,h=hc): chosen[0]=h; d2.response(Gtk.ResponseType.OK)
            btn.connect("clicked",clk)
            flow.add(btn)
        b2.add(flow)
        d2.add_button("Cancel",Gtk.ResponseType.CANCEL)
        d2.show_all()
        d2.run()
        zone["color"] = chosen[0]
        d2.destroy()
        save_zones(zones)
        notify("Color updated")

def main():
    try: ctx_data = json.loads(Path(CTX_FILE).read_text())
    except: ctx_data = {"context":"canvas","x":0,"y":0}

    ctx = ctx_data.get("context","canvas")
    zone_id = ctx_data.get("zone_id","")
    sel = ctx_data.get("selected_count",0)
    zones = load_zones()

    # Build items list
    items = []
    if ctx == "zone":
        zone = next((z for z in zones if z["id"]==zone_id),None)
        zname = zone["name"] if zone else zone_id
        items = [
            ("✏  Rename zone", "rename"),
            ("🎨  Change color", "recolor"),
            ("🗑  Delete zone", "delete"),
        ]
        title = "Zone: {}".format(zname)
    else:
        items = [("＋  New zone here", "new_zone")]
        if sel > 1:
            items.append(("⬡  Group {} into zone".format(sel), "new_zone"))
        title = "Echo Menu"

    # Show as simple dialog with listbox
    d = Gtk.Dialog(title=title, flags=0)
    d.set_keep_above(True)
    d.set_default_size(250, 50 + len(items)*44)
    box = d.get_content_area()
    box.set_spacing(0)

    chosen_action = [None]

    for label, key in items:
        btn = Gtk.Button(label=label)
        btn.set_relief(Gtk.ReliefStyle.NONE)
        def click(w, k=key):
            chosen_action[0] = k
            d.response(Gtk.ResponseType.OK)
        btn.connect("clicked", click)
        box.pack_start(btn, False, False, 0)

    d.show_all()

    # Position near cursor
    mx = int(ctx_data.get("screen_x",0))
    my = int(ctx_data.get("screen_y",0))
    if mx==0 and my==0:
        display = Gdk.Display.get_default()
        seat = display.get_default_seat()
        ptr = seat.get_pointer()
        screen,mx,my = ptr.get_position()
    d.move(mx, my)

    d.run()
    d.destroy()

    if chosen_action[0]:
        run_action(chosen_action[0], ctx_data)

if __name__ == "__main__":
    main()
