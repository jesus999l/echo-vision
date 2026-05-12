import subprocess
import os
import pytesseract
from PIL import Image
from config import SCREENSHOT_PATH


def capture_area():
    if os.path.exists(SCREENSHOT_PATH):
        os.remove(SCREENSHOT_PATH)
    subprocess.run(["gnome-screenshot", "-a", "-f", SCREENSHOT_PATH])
    return SCREENSHOT_PATH if os.path.exists(SCREENSHOT_PATH) else None


def ocr_image(image_path):
    try:
        return pytesseract.image_to_string(Image.open(image_path))
    except Exception as e:
        print(f"OCR failed: {e}")
        return ""


def cleanup_stale_processes():
    import os as _os
    my_pid = str(_os.getpid())
    result = subprocess.run(["pgrep", "-f", "gnome-screenshot"], capture_output=True, text=True)
    for pid in result.stdout.strip().split("\n"):
        if pid.strip() and pid.strip() != my_pid:
            subprocess.run(["kill", pid.strip()], capture_output=True)
