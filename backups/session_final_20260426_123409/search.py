import subprocess
import os
import urllib.parse
import time


def get_firefox_window():
    result = subprocess.run(
        ["xdotool", "search", "--onlyvisible", "--class", "firefox"],
        capture_output=True, text=True
    )
    ids = [i for i in result.stdout.strip().split("\n") if i.strip()]
    return ids[-1] if ids else None


def focus_firefox():
    wid = get_firefox_window()
    if wid:
        subprocess.run(["xdotool", "windowactivate", "--sync", wid])
        time.sleep(0.3)
    return wid


def reverse_image_search(image_path, ocr_text=""):
    try:
        has_image = os.path.exists(image_path)
        has_text = bool(ocr_text.strip())

        if has_image:
            with open(image_path, "rb") as f:
                image_data = f.read()
            xclip_proc = subprocess.Popen(
                ["xclip", "-selection", "clipboard", "-t", "image/png"],
                stdin=subprocess.PIPE
            )
            xclip_proc.stdin.write(image_data)
            xclip_proc.stdin.close()

            subprocess.Popen(["xdg-open", "https://lens.google.com"])

            for _ in range(20):
                if get_firefox_window():
                    break
                time.sleep(0.5)

            time.sleep(3)
            focus_firefox()
            subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+v"])
            time.sleep(2)

        if has_text:
            query = urllib.parse.quote_plus(ocr_text[:500])
            search_url = f"https://www.google.com/search?q={query}"
            if has_image:
                focus_firefox()
                subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+t"])
                time.sleep(0.8)
                subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+l"])
                time.sleep(0.3)
                subprocess.run(["xdotool", "type", "--clearmodifiers", "--delay", "20", search_url])
                time.sleep(0.2)
                subprocess.run(["xdotool", "key", "--clearmodifiers", "Return"])
            else:
                subprocess.Popen(["xdg-open", search_url])

    except Exception as e:
        print(f"Search error: {e}")
        if ocr_text.strip():
            query = urllib.parse.quote_plus(ocr_text[:500])
            subprocess.Popen(["xdg-open", f"https://www.google.com/search?q={query}"])


def web_search_url(query):
    return f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"


def open_url(url):
    subprocess.Popen(["xdg-open", url])
