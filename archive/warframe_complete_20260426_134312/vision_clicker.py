"""
Vision-based UI clicker.
Takes a screenshot, sends to moondream/llava, gets click coordinates, clicks.
"""
import subprocess, time, tempfile, os, json, re

def _run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def take_screenshot(path=None):
    if not path:
        path = tempfile.mktemp(suffix=".png")
    _run(f"import -window root {path}")  # ImageMagick
    if not os.path.exists(path) or os.path.getsize(path) < 100:
        _run(f"scrot {path}")  # fallback
    return path

def get_click_coords(screenshot_path, target_description, model="moondream"):
    """Ask AI where to click for a target element."""
    import sys
    sys.path.insert(0, os.path.expanduser("~/vision_assistant"))
    
    try:
        import ollama
        with open(screenshot_path, "rb") as f:
            img = f.read()
        import base64
        img_b64 = base64.b64encode(img).decode()
        
        prompt = f"""Look at this screenshot. Find the UI element: "{target_description}"
Return ONLY a JSON object with the pixel coordinates to click:
{{"x": 123, "y": 456}}
No other text."""
        
        resp = ollama.chat(
            model=model,
            messages=[{
                "role": "user",
                "content": prompt,
                "images": [img_b64]
            }]
        )
        text = resp["message"]["content"].strip()
        # Parse JSON from response
        m = re.search(r'\{[^}]+\}', text)
        if m:
            coords = json.loads(m.group())
            return coords.get("x"), coords.get("y")
    except Exception as e:
        print(f"vision error: {e}")
    return None, None

def vision_click(target_description, model="moondream"):
    """Screenshot, find element, click it."""
    print(f"Looking for: {target_description}")
    screenshot = take_screenshot()
    x, y = get_click_coords(screenshot, target_description, model)
    if x and y:
        print(f"Clicking at {x},{y}")
        _run(f"xdotool mousemove {x} {y}")
        time.sleep(0.2)
        _run("xdotool click 1")
        return True, f"Clicked {target_description} at {x},{y}"
    return False, f"Could not find: {target_description}"

def vision_action(instruction, model="moondream"):
    """
    Full vision-based action pipeline.
    instruction: natural language like "click the play button on YouTube Music"
    """
    screenshot = take_screenshot()
    x, y = get_click_coords(screenshot, instruction, model)
    if x and y:
        _run(f"xdotool mousemove {x} {y}")
        time.sleep(0.2)
        _run("xdotool click 1")
        os.unlink(screenshot)
        return f"Done: clicked at {x},{y}"
    os.unlink(screenshot)
    return f"Couldn't find element: {instruction}"
