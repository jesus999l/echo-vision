"""
Patch: multi-user voice profiles in settings UI + wake_word routing.
Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_voice_profiles.py
"""
import subprocess

UI = "/home/jesus999l/vision_assistant/ui.py"
WW = "/home/jesus999l/vision_assistant/wake_word.py"
PROFILES_DIR = "/home/jesus999l/vision_assistant/voice_profiles"

# ─────────────────────────────────────────────────────────────────────────────
# PART 1 — ui.py: add VOICE PROFILES section before SAVE SETTINGS button
# ─────────────────────────────────────────────────────────────────────────────
ui_src = open(UI).read()

OLD_SAVE = '        sbtn(inner,"SAVE SETTINGS",save_s,bg=ACCENT).pack(anchor="e",padx=14,pady=12)'

NEW_SECTION = '''        # VOICE PROFILES
        section("VOICE PROFILES", ACCENT2)
        vp_frame = tk.Frame(inner, bg=BG3, padx=14, pady=12)
        vp_frame.pack(fill="x", padx=10, pady=(0,6))

        import os as _os
        PROFILES_DIR = _os.path.expanduser("~/vision_assistant/voice_profiles")

        def _list_profiles():
            if not _os.path.exists(PROFILES_DIR): return []
            files = [f for f in _os.listdir(PROFILES_DIR) if f.endswith(".npy")]
            profiles = []
            for f in sorted(files):
                name = f[:-4]
                label = "👤 Main User" if name == "main" else f"👥 {name.replace('guest_','')}"
                profiles.append((name, label, _os.path.join(PROFILES_DIR, f)))
            return profiles

        def _refresh_profiles():
            for w in prof_list.winfo_children(): w.destroy()
            profiles = _list_profiles()
            if not profiles:
                tk.Label(prof_list, text="No voice profiles enrolled.",
                         bg=BG3, fg=TEXT3, font=FONT_TINY).pack(anchor="w", pady=4)
                return
            for name, label, path in profiles:
                row = tk.Frame(prof_list, bg=BG4, padx=8, pady=4)
                row.pack(fill="x", pady=2)
                tk.Label(row, text=label, bg=BG4, fg=TEXT, font=FONT_SMALL).pack(side="left")
                def _del(p=path):
                    try: _os.unlink(p)
                    except: pass
                    _refresh_profiles()
                sbtn(row, "✕ Remove", _del, bg=DANGER, fg=WHITE, px=6, py=1).pack(side="right")

        prof_list = tk.Frame(vp_frame, bg=BG3)
        prof_list.pack(fill="x", pady=(0,8))
        _refresh_profiles()

        tk.Label(vp_frame, text="Enroll via voice command or button below:",
                 bg=BG3, fg=TEXT3, font=FONT_TINY).pack(anchor="w", pady=(0,4))

        # Enroll main user
        def _enroll_main():
            try:
                from wake_word import enroll_voice, _pa_instance
                if _pa_instance:
                    import threading
                    def _do():
                        enroll_voice(_pa_instance, label="main")
                        vp_frame.after(500, _refresh_profiles)
                    threading.Thread(target=_do, daemon=True).start()
                    self.show_toast("Recording... speak naturally for 4 seconds", color=ACCENT2)
                else:
                    self.show_toast("Wake word detector not running", color=DANGER)
            except Exception as e:
                self.show_toast(f"Error: {e}", color=DANGER)

        sbtn(vp_frame, "🎙 Enroll Main User", _enroll_main,
             bg=ACCENT2, fg=BG, px=10, py=4).pack(anchor="w", pady=(0,6))

        # Enroll guest
        guest_row = tk.Frame(vp_frame, bg=BG3); guest_row.pack(fill="x")
        tk.Label(guest_row, text="Guest name:", bg=BG3, fg=TEXT3, font=FONT_TINY).pack(side="left")
        guest_var = tk.StringVar()
        tk.Entry(guest_row, textvariable=guest_var, bg=BG2, fg=TEXT,
                 insertbackground=ACCENT, relief="flat", font=FONT_SMALL, width=14,
                 highlightthickness=1, highlightbackground=BORDER).pack(side="left", padx=6, ipady=3)

        def _enroll_guest():
            name = guest_var.get().strip().lower().replace(" ","_")
            if not name:
                self.show_toast("Enter a name first", color=WARN); return
            try:
                from wake_word import enroll_voice, _pa_instance
                if _pa_instance:
                    import threading
                    def _do():
                        enroll_voice(_pa_instance, label=f"guest_{name}")
                        vp_frame.after(500, _refresh_profiles)
                    threading.Thread(target=_do, daemon=True).start()
                    self.show_toast(f"Recording {name}... speak naturally for 4 seconds", color=ACCENT2)
                else:
                    self.show_toast("Wake word detector not running", color=DANGER)
            except Exception as e:
                self.show_toast(f"Error: {e}", color=DANGER)

        sbtn(guest_row, "🎙 Enroll Guest", _enroll_guest,
             bg=BG4, fg=TEXT2, px=10, py=4).pack(side="left")

        voice_check_var = tk.BooleanVar(value=SETTINGS.get("voice_id_enabled", False))
        tk.Checkbutton(vp_frame, text="Reject unrecognized voices",
                       variable=voice_check_var, bg=BG3, fg=TEXT,
                       selectcolor=BG2, activebackground=BG3,
                       font=FONT_SMALL, highlightthickness=0).pack(anchor="w", pady=(8,0))

        sbtn(inner,"SAVE SETTINGS",save_s,bg=ACCENT).pack(anchor="e",padx=14,pady=12)'''

if OLD_SAVE in ui_src:
    ui_src = ui_src.replace(OLD_SAVE, NEW_SECTION)
    print("OK: voice profiles UI section")
else:
    print("FAIL: save settings button not found")

# Also update save_s to save voice_id_enabled
OLD_SAVE_S = '            save_settings(SETTINGS)\n            self._apply_theme(th_var.get(), acc_var.get())'
NEW_SAVE_S = '            SETTINGS["voice_id_enabled"] = voice_check_var.get()\n            save_settings(SETTINGS)\n            self._apply_theme(th_var.get(), acc_var.get())'
if OLD_SAVE_S in ui_src:
    ui_src = ui_src.replace(OLD_SAVE_S, NEW_SAVE_S)
    print("OK: save voice_id_enabled")
else:
    print("FAIL: save_s not found")

open(UI, "w").write(ui_src)

# ─────────────────────────────────────────────────────────────────────────────
# PART 2 — wake_word.py: multi-profile voice system
# ─────────────────────────────────────────────────────────────────────────────
ww_src = open(WW).read()

PROFILES_DIR_PY = "os.path.expanduser('~/vision_assistant/voice_profiles')"

# Replace single-profile system with multi-profile
OLD_PROFILE = '''# ── VOICE FINGERPRINT ─────────────────────────────────────────────────────────
VOICE_PROFILE_PATH = os.path.expanduser("~/vision_assistant/voice_profile.npy")

def _extract_voice_features(audio_bytes):
    """Return simple energy-band fingerprint from raw PCM bytes."""
    try:
        import numpy as np
        samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
        if len(samples) < 1600: return None
        # Split into 8 frequency bins via chunked RMS
        chunk = len(samples) // 8
        return np.array([
            np.sqrt(np.mean(samples[i*chunk:(i+1)*chunk]**2))
            for i in range(8)
        ])
    except: return None

def enroll_voice(pa, seconds=4):
    """Record user voice for 4s and save fingerprint."""
    import pyaudio, audioop
    print("[voice] Enrolling — speak naturally for 4 seconds...")
    speak("Recording your voice now. Please speak naturally.")
    frames = []
    stream = _make_stream(pa)
    stream.start_stream()
    for _ in range(int(16000 / 2048 * seconds)):
        data = stream.read(2048, exception_on_overflow=False)
        frames.append(data)
    stream.stop_stream(); stream.close()
    raw = b"".join(frames)
    feat = _extract_voice_features(raw)
    if feat is not None:
        import numpy as np
        np.save(VOICE_PROFILE_PATH, feat)
        global _voice_profile
        _voice_profile = feat
        print("[voice] Profile saved.")
        speak("Voice enrolled. I'll recognize you from now on.")
    else:
        print("[voice] Enrollment failed — no audio.")

def _load_voice_profile():
    global _voice_profile
    if _voice_profile is None and os.path.exists(VOICE_PROFILE_PATH):
        import numpy as np
        _voice_profile = np.load(VOICE_PROFILE_PATH)
    return _voice_profile

def _voice_matches(audio_bytes, threshold=0.75):
    """Return True if audio matches enrolled voice (or no profile set)."""
    profile = _load_voice_profile()
    if profile is None: return True  # no enrollment — open to all
    feat = _extract_voice_features(audio_bytes)
    if feat is None: return True
    try:
        import numpy as np
        # Cosine similarity
        sim = np.dot(feat, profile) / (np.linalg.norm(feat) * np.linalg.norm(profile) + 1e-9)
        print(f"[voice] similarity: {sim:.2f}")
        return float(sim) > threshold
    except: return True'''

NEW_PROFILE = '''# ── VOICE FINGERPRINT (multi-user) ───────────────────────────────────────────
VOICE_PROFILES_DIR = os.path.expanduser("~/vision_assistant/voice_profiles")
# Legacy single-profile path (kept for migration)
VOICE_PROFILE_PATH = os.path.expanduser("~/vision_assistant/voice_profile.npy")

def _extract_voice_features(audio_bytes):
    """Return energy-band fingerprint from raw PCM bytes."""
    try:
        import numpy as np
        samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
        if len(samples) < 1600: return None
        chunk = len(samples) // 8
        return np.array([
            np.sqrt(np.mean(samples[i*chunk:(i+1)*chunk]**2))
            for i in range(8)
        ])
    except: return None

def enroll_voice(pa, seconds=4, label="main"):
    """Record voice for 4s and save as label (main or guest_name)."""
    os.makedirs(VOICE_PROFILES_DIR, exist_ok=True)
    name = "Main User" if label == "main" else label.replace("guest_","").title()
    print(f"[voice] Enrolling {name}...")
    speak(f"Recording {name}. Please speak naturally.")
    frames = []
    stream = _make_stream(pa)
    stream.start_stream()
    for _ in range(int(16000 / 2048 * seconds)):
        data = stream.read(2048, exception_on_overflow=False)
        frames.append(data)
    stream.stop_stream(); stream.close()
    raw = b"".join(frames)
    feat = _extract_voice_features(raw)
    if feat is not None:
        import numpy as np
        path = os.path.join(VOICE_PROFILES_DIR, f"{label}.npy")
        np.save(path, feat)
        print(f"[voice] Profile saved: {label}")
        speak(f"{name} enrolled.")
    else:
        print("[voice] Enrollment failed.")
        speak("Enrollment failed, please try again.")

def _load_all_profiles():
    """Load all enrolled voice profiles. Returns list of numpy arrays."""
    import numpy as np
    profiles = []
    # Load from profiles dir
    if os.path.exists(VOICE_PROFILES_DIR):
        for f in os.listdir(VOICE_PROFILES_DIR):
            if f.endswith(".npy"):
                try:
                    profiles.append(np.load(os.path.join(VOICE_PROFILES_DIR, f)))
                except: pass
    # Migrate legacy single profile
    if not profiles and os.path.exists(VOICE_PROFILE_PATH):
        try:
            feat = np.load(VOICE_PROFILE_PATH)
            os.makedirs(VOICE_PROFILES_DIR, exist_ok=True)
            np.save(os.path.join(VOICE_PROFILES_DIR, "main.npy"), feat)
            profiles.append(feat)
        except: pass
    return profiles

def _voice_matches(audio_bytes, threshold=0.72):
    """Return True if audio matches any enrolled profile (or none enrolled)."""
    from config import SETTINGS as _cfg
    try:
        import json
        s = json.load(open(os.path.expanduser("~/vision_assistant/settings.json")))
        if not s.get("voice_id_enabled", False):
            return True  # feature disabled
    except: return True
    profiles = _load_all_profiles()
    if not profiles: return True
    feat = _extract_voice_features(audio_bytes)
    if feat is None: return True
    try:
        import numpy as np
        for profile in profiles:
            sim = np.dot(feat, profile) / (np.linalg.norm(feat) * np.linalg.norm(profile) + 1e-9)
            print(f"[voice] similarity: {sim:.2f}")
            if float(sim) > threshold:
                return True
        return False
    except: return True'''

if OLD_PROFILE in ww_src:
    ww_src = ww_src.replace(OLD_PROFILE, NEW_PROFILE)
    print("OK: multi-profile voice system")
else:
    print("FAIL: voice profile block not found")

# Update enroll route to pass label
OLD_ENROLL_ROUTE = '''    # Voice enrollment
    if any(x in t for x in ["enroll my voice","enroll voice","train my voice","remember my voice"]):
        if _pa_instance:
            threading.Thread(target=enroll_voice, args=(_pa_instance,), daemon=True).start()
        else:
            speak("Microphone not ready yet.")
        return
    if any(x in t for x in ["forget my voice","reset voice","clear voice profile"]):
        global _voice_profile
        _voice_profile = None
        if os.path.exists(VOICE_PROFILE_PATH):
            os.unlink(VOICE_PROFILE_PATH)
        speak("Voice profile cleared.")
        return'''

NEW_ENROLL_ROUTE = '''    # Voice enrollment
    if any(x in t for x in ["enroll my voice","enroll voice","train my voice","remember my voice"]):
        if _pa_instance:
            threading.Thread(target=enroll_voice, args=(_pa_instance,), kwargs={"label":"main"}, daemon=True).start()
        else:
            speak("Microphone not ready yet.")
        return
    m = re.search(r"enroll\s+(?:guest\s+)?(\w+)(?:'s|s)?\s+voice", t)
    if m:
        name = m.group(1).lower()
        if _pa_instance:
            threading.Thread(target=enroll_voice, args=(_pa_instance,),
                             kwargs={"label": f"guest_{name}"}, daemon=True).start()
        else:
            speak("Microphone not ready yet.")
        return
    if any(x in t for x in ["forget my voice","reset voice","clear voice profile","clear all voices"]):
        import shutil
        if os.path.exists(VOICE_PROFILES_DIR):
            shutil.rmtree(VOICE_PROFILES_DIR)
            os.makedirs(VOICE_PROFILES_DIR)
        if os.path.exists(VOICE_PROFILE_PATH):
            os.unlink(VOICE_PROFILE_PATH)
        speak("All voice profiles cleared.")
        return
    m2 = re.search(r"(?:forget|remove|delete)\s+(?:guest\s+)?(\w+)(?:'s|s)?\s+voice", t)
    if m2:
        name = m2.group(1).lower()
        path = os.path.join(VOICE_PROFILES_DIR, f"guest_{name}.npy")
        if os.path.exists(path):
            os.unlink(path)
            speak(f"Removed {name}'s voice profile.")
        else:
            speak(f"No profile found for {name}.")
        return'''

if OLD_ENROLL_ROUTE in ww_src:
    ww_src = ww_src.replace(OLD_ENROLL_ROUTE, NEW_ENROLL_ROUTE)
    print("OK: enroll route updated")
else:
    print("FAIL: enroll route not found")

open(WW, "w").write(ww_src)

# Check syntax
for label, path in [("ui.py", UI), ("wake_word.py", WW)]:
    r = subprocess.run(
        ["/home/jesus999l/vision_env/bin/python3", "-m", "py_compile", path],
        capture_output=True, text=True
    )
    print(f"{'OK' if r.returncode==0 else 'ERR'}: {label}")
    if r.returncode != 0: print(r.stderr)
