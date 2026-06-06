import tkinter as tk
import subprocess, os, sys, tempfile, threading, json, socket

sys.path.insert(0, os.path.expanduser("~/vision_assistant"))
from config import IPC_HOST, IPC_PORT, IPC_MAGIC

SEL_COLOR  = "#7c6af7"
SEL_ALPHA  = "gray25"
TOOLBAR_BG = "#1a1a2e"
TOOLBAR_FG = "#e8e8f0"
ACCENT     = "#7c6af7"
ACCENT2    = "#a89cf7"
BTN_HOVER  = "#2e2e4e"

def _grab_desktop():
    tmp = tempfile.mktemp(prefix="vision_desk_", suffix=".png")
    r = subprocess.run(["grim", tmp], capture_output=True)
    if r.returncode == 0 and os.path.exists(tmp):
        return tmp
    r2 = subprocess.run(["import", "-window", "root", tmp], capture_output=True)
    return tmp if r2.returncode == 0 and os.path.exists(tmp) else None

def _crop_and_ocr(src_path, x1, y1, x2, y2):
    x, y = min(x1, x2), min(y1, y2)
    w, h = abs(x2 - x1), abs(y2 - y1)
    if w < 4 or h < 4:
        return "", None
    tmp = tempfile.mktemp(prefix="vision_sel_", suffix=".png")
    r = subprocess.run(["convert", src_path, "-crop", f"{w}x{h}+{x}+{y}", "+repage", tmp], capture_output=True)
    if r.returncode != 0 or not os.path.exists(tmp):
        return "", None
    try:
        import pytesseract
        from PIL import Image
        text = pytesseract.image_to_string(Image.open(tmp)).strip()
        return text, tmp
    except Exception as e:
        return f"[OCR error: {e}]", tmp

def _send_to_echo(screenshot_path, ocr_text):
    try:
        payload = json.dumps({"magic": IPC_MAGIC, "screenshot": screenshot_path or "", "ocr": ocr_text}).encode()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((IPC_HOST, IPC_PORT))
        s.sendall(payload)
        s.close()
        return True
    except:
        return False

def _cleanup(path):
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except: pass

class InlineToolbar(tk.Toplevel):
    def __init__(self, master, text, screenshot_path, sel_x, sel_y, sel_w):
        super().__init__(master)
        self.text = text
        self.screenshot_path = screenshot_path
        self._dismissed = False
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=TOOLBAR_BG)
        self.lift()
        self._build()
        self.update_idletasks()
        tw = self.winfo_reqwidth()
        th = self.winfo_reqheight()
        sw = master.winfo_screenwidth()
        sh = master.winfo_screenheight()
        tx = sel_x + sel_w // 2 - tw // 2
        ty = sel_y - th - 8
        tx = max(4, min(tx, sw - tw - 4))
        ty = max(4, min(ty, sh - th - 4))
        self.geometry(f"{tw}x{th}+{tx}+{ty}")
        self.focus_force()
        self.bind("<FocusOut>", lambda e: self._dismiss())
        self.bind("<Escape>",   lambda e: self._dismiss())

    def _build(self):
        tk.Frame(self, bg=ACCENT, height=2).pack(fill="x")
        frame = tk.Frame(self, bg=TOOLBAR_BG, padx=2, pady=2)
        frame.pack()
        def btn(label, cmd, color=TOOLBAR_FG):
            b = tk.Label(frame, text=label, bg=TOOLBAR_BG, fg=color,
                        font=("Segoe UI", 9, "bold"), padx=8, pady=5, cursor="hand2")
            b.pack(side="left")
            b.bind("<Button-1>", lambda e: cmd())
            b.bind("<Enter>",    lambda e: b.configure(bg=BTN_HOVER))
            b.bind("<Leave>",    lambda e: b.configure(bg=TOOLBAR_BG))
        def sep():
            tk.Frame(frame, bg="#2e2e4e", width=1).pack(side="left", fill="y", padx=1, pady=3)
        btn("Copy", self._copy, ACCENT2)
        sep()
        btn("Ask Echo", self._ask_echo, ACCENT2)
        sep()
        btn("UPPER", self._upper)
        btn("lower", self._lower)
        btn("Title", self._title)
        sep()
        btn("X", self._dismiss, "#555577")
        preview = self.text[:70] + "..." if len(self.text) > 70 else self.text
        if preview:
            tk.Label(self, text=preview, bg="#111122", fg="#7070a0",
                    font=("Segoe UI", 8), padx=10, pady=4,
                    anchor="w", wraplength=420).pack(fill="x")

    def _flash(self, msg):
        for w in self.winfo_children():
            if isinstance(w, tk.Label) and w.cget("bg") == "#111122":
                w.configure(text=msg, fg=ACCENT2)

    def _copy(self):
        self.clipboard_clear(); self.clipboard_append(self.text); self.update()
        self._flash("Copied!"); self.after(1000, self._dismiss)

    def _ask_echo(self):
        sent = _send_to_echo(self.screenshot_path, self.text)
        if not sent:
            subprocess.Popen(["/home/jesus999l/vision_env/bin/python3",
                              "/home/jesus999l/vision_assistant/main.py", "--ui"])
            self.after(1500, lambda: _send_to_echo(self.screenshot_path, self.text))
        self._flash("Sent!"); self.after(1000, self._dismiss)

    def _upper(self):
        self.clipboard_clear(); self.clipboard_append(self.text.upper()); self.update()
        self._flash("UPPER copied!")

    def _lower(self):
        self.clipboard_clear(); self.clipboard_append(self.text.lower()); self.update()
        self._flash("lower copied!")

    def _title(self):
        self.clipboard_clear(); self.clipboard_append(self.text.title()); self.update()
        self._flash("Title copied!")

    def _dismiss(self):
        if not self._dismissed:
            self._dismissed = True
            _cleanup(self.screenshot_path)
            try: self.destroy()
            except: pass

class SelectionOverlay(tk.Toplevel):
    def __init__(self, master, desktop_img_path, sw=1920, sh=1080):
        super().__init__(master)
        self.master = master
        self.desktop_img_path = desktop_img_path
        self.geometry(f"{sw}x{sh}+0+0")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="black")
        self.lift()
        self.canvas = tk.Canvas(self, width=sw, height=sh, bg="#0a0a1a",
                                highlightthickness=0, cursor="crosshair")
        self.canvas.place(x=0, y=0)
        try:
            from PIL import Image, ImageTk, ImageEnhance
            img = Image.open(desktop_img_path).resize((sw, sh), Image.LANCZOS)
            img = ImageEnhance.Brightness(img).enhance(0.78)
            self._bg = ImageTk.PhotoImage(img)
            self.canvas.create_image(0, 0, anchor="nw", image=self._bg)
        except Exception as e:
            print(f"[selector] bg error: {e}")
        self.canvas.create_rectangle(sw//2-175, 18, sw//2+175, 46,
            fill="#000000", outline="", stipple="gray50", tags="hint_bg")
        self.canvas.create_text(sw//2, 32,
            text="Drag to select text  .  Esc to cancel",
            fill="#ffffff", font=("Segoe UI", 11), tags="hint")
        self._sx = self._sy = 0
        self._rect = None
        self.canvas.bind("<ButtonPress-1>",   self._press)
        self.canvas.bind("<B1-Motion>",       self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.bind("<Escape>", lambda e: self._cancel())
        self.focus_force()
        self.update_idletasks()

    def _cancel(self):
        _cleanup(self.desktop_img_path); self.destroy()

    def _press(self, e):
        self._sx, self._sy = e.x, e.y
        self.canvas.delete("hint"); self.canvas.delete("hint_bg")
        if self._rect: self.canvas.delete(self._rect)

    def _drag(self, e):
        if self._rect: self.canvas.delete(self._rect)
        self._rect = self.canvas.create_rectangle(
            self._sx, self._sy, e.x, e.y,
            outline=SEL_COLOR, width=1, fill=SEL_COLOR, stipple=SEL_ALPHA, tags="sel")

    def _release(self, e):
        x1, y1 = self._sx, self._sy
        x2, y2 = e.x, e.y
        desk = self.desktop_img_path
        tx, ty, tw = min(x1,x2), min(y1,y2), abs(x2-x1)
        self.destroy()
        def _process():
            text, crop_path = _crop_and_ocr(desk, x1, y1, x2, y2)
            _cleanup(desk)
            self.master.after(0, lambda: InlineToolbar(self.master, text, crop_path, tx, ty, tw))
        threading.Thread(target=_process, daemon=True).start()

def _start_selector(root):
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    if sw < 100: sw, sh = 1920, 1080
    def _bg():
        path = _grab_desktop()
        if path:
            root.after(0, lambda: SelectionOverlay(root, path, sw, sh))
    threading.Thread(target=_bg, daemon=True).start()

def run_text_selector():
    root = tk.Tk()
    root.withdraw()
    root.update_idletasks()
    root.after(150, lambda: _start_selector(root))
    root.mainloop()

if __name__ == "__main__":
    run_text_selector()
