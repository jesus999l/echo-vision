"""
USB Player — Media playback control via ffplay.
Usage: python usb_player.py --play "/path/to/file.mp3"
"""
import subprocess
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("usb_player")

_current_process = None

def play_media(filepath):
    global _current_process
    filepath = os.path.expanduser(filepath)
    if not os.path.exists(filepath):
        return f"Error: {filepath} not found."

    stop_media()

    try:
        # Use ffplay with no visual for audio, or default for video
        cmd = ["ffplay", "-nodisp", "-autoexit", filepath]
        _current_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Playing: {os.path.basename(filepath)}"
    except Exception as e:
        return f"Playback error: {e}"

def stop_media():
    global _current_process
    if _current_process and _current_process.poll() is None:
        _current_process.terminate()
        _current_process = None
        return "Playback stopped."

    # Kill any stray ffplay
    subprocess.run(["pkill", "ffplay"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "No active playback."

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(play_media(sys.argv[1]))
    else:
        print("Usage: python usb_player.py <filepath>")
