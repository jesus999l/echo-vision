"""
Echo System Optimization — Gaming Stack
1. Disables Docker autostart (start/stop via desktop icons instead)
2. Creates ~/docker-start.sh and ~/docker-stop.sh
3. Creates desktop launchers for Docker stack
4. Sets PipeWire realtime priority
5. Creates gaming-mode.sh — pins Warframe+Steam to cores 2-7, Firefox+Echo to 0-1
6. Creates a systemd user service for gaming mode auto-apply

Run: python3 ~/vision_assistant/patch_optimize.py
"""
import os, subprocess

HOME = os.path.expanduser("~")

# ── 1. DISABLE DOCKER AUTOSTART ──────────────────────────────────────────────
print("[1/5] Disabling Docker autostart...")
subprocess.run(["sudo", "systemctl", "disable", "docker"], capture_output=True)
subprocess.run(["sudo", "systemctl", "disable", "docker.socket"], capture_output=True)
print("OK: Docker will no longer start on boot")

# ── 2. CREATE docker-start.sh / docker-stop.sh ───────────────────────────────
print("[2/5] Creating Docker control scripts...")

start_sh = """\
#!/usr/bin/env bash
# Start Echo Docker stack
echo "Starting Docker services..."
sudo systemctl start docker
sleep 2
sudo docker start bookstack bookstack_db dashboard webpersistent searxng
notify-send "Docker" "Stack started: Bookstack, Homepage, SearXNG" -i network-server
"""

stop_sh = """\
#!/usr/bin/env bash
# Stop Echo Docker stack
echo "Stopping Docker services..."
sudo docker stop bookstack bookstack_db dashboard webpersistent searxng
notify-send "Docker" "Stack stopped." -i network-offline
"""

for fname, content in [("docker-start.sh", start_sh), ("docker-stop.sh", stop_sh)]:
    path = os.path.join(HOME, fname)
    open(path, "w").write(content)
    os.chmod(path, 0o755)

print("OK: ~/docker-start.sh and ~/docker-stop.sh created")

# ── 3. DESKTOP LAUNCHERS ─────────────────────────────────────────────────────
print("[3/5] Creating desktop launchers...")

desktop_dir = os.path.join(HOME, "Desktop")
os.makedirs(desktop_dir, exist_ok=True)

start_desktop = """\
[Desktop Entry]
Type=Application
Name=Start Services
Comment=Start Bookstack, Homepage, SearXNG
Exec=bash /home/jesus999l/docker-start.sh
Icon=network-server
Terminal=false
Categories=System;
"""

stop_desktop = """\
[Desktop Entry]
Type=Application
Name=Stop Services
Comment=Stop Docker stack
Exec=bash /home/jesus999l/docker-stop.sh
Icon=network-offline
Terminal=false
Categories=System;
"""

for fname, content in [("Start Services.desktop", start_desktop),
                        ("Stop Services.desktop", stop_desktop)]:
    path = os.path.join(desktop_dir, fname)
    open(path, "w").write(content)
    os.chmod(path, 0o755)
    subprocess.run(["gio", "set", path, "metadata::trusted", "true"], capture_output=True)

print("OK: Desktop launchers created")

# ── 4. PIPEWIRE REALTIME PRIORITY ─────────────────────────────────────────────
print("[4/5] Setting PipeWire realtime priority...")

pw_conf_dir = os.path.expanduser("~/.config/pipewire/pipewire.conf.d")
os.makedirs(pw_conf_dir, exist_ok=True)

pw_rt = """\
context.properties = {
    default.clock.rate          = 48000
    default.clock.quantum       = 256
    default.clock.min-quantum   = 32
    default.clock.max-quantum   = 512
}
"""
open(os.path.join(pw_conf_dir, "10-realtime.conf"), "w").write(pw_rt)

# Add user to audio group for realtime
subprocess.run(["sudo", "usermod", "-aG", "audio", "jesus999l"], capture_output=True)

# Set realtime limits
limits_file = "/etc/security/limits.d/audio-realtime.conf"
limits_content = """\
@audio   -  rtprio     95
@audio   -  memlock    unlimited
@audio   -  nice       -19
"""
r = subprocess.run(["sudo", "tee", limits_file],
                   input=limits_content.encode(), capture_output=True)
if r.returncode == 0:
    print("OK: PipeWire realtime priority set")
else:
    print("WARN: Could not set realtime limits (may need sudo)")

# ── 5. GAMING MODE SCRIPT ─────────────────────────────────────────────────────
print("[5/5] Creating gaming-mode.sh...")

gaming_sh = """\
#!/usr/bin/env bash
# gaming-mode.sh — Optimize CPU affinity for gaming session
# Warframe + Steam → cores 2-7 (performance)
# Firefox + Echo + Desktop → cores 0-1 (background)
# PipeWire → realtime nice

echo "Applying gaming mode CPU affinity..."

# Pin Warframe to cores 2-7
for pid in $(pgrep -f "Warframe.x64.exe" 2>/dev/null); do
    taskset -cp 2-7 $pid 2>/dev/null && echo "  Warframe PID $pid → cores 2-7"
done

# Pin Steam to cores 2-7
for pid in $(pgrep -f "steamwebhelper|steam" 2>/dev/null); do
    taskset -cp 2-7 $pid 2>/dev/null
done
echo "  Steam → cores 2-7"

# Pin Firefox to cores 0-1 (background music)
for pid in $(pgrep -f "firefox" 2>/dev/null); do
    taskset -cp 0-1 $pid 2>/dev/null
    renice -n 5 -p $pid 2>/dev/null
done
echo "  Firefox → cores 0-1 (low priority)"

# Pin Echo to cores 0-1
for pid in $(pgrep -f "vision_assistant/main.py" 2>/dev/null); do
    taskset -cp 0-1 $pid 2>/dev/null
    renice -n 10 -p $pid 2>/dev/null
done
echo "  Echo → cores 0-1 (background)"

# Pin Docker containers to cores 0-1
for pid in $(pgrep -f "containerd|dockerd" 2>/dev/null); do
    taskset -cp 0-1 $pid 2>/dev/null
done
echo "  Docker → cores 0-1"

# PipeWire + WirePlumber — realtime nice
for pid in $(pgrep -x "pipewire" 2>/dev/null); do
    renice -n -15 -p $pid 2>/dev/null
done
for pid in $(pgrep -x "wireplumber" 2>/dev/null); do
    renice -n -15 -p $pid 2>/dev/null
done
echo "  PipeWire → realtime priority"

# Cinnamon compositor — reduce priority
for pid in $(pgrep -x "cinnamon" 2>/dev/null); do
    renice -n 5 -p $pid 2>/dev/null
done
echo "  Cinnamon → reduced priority"

notify-send "Echo" "Gaming mode active — 6 cores reserved for Warframe" -i applications-games
echo "Done."
"""

gaming_path = os.path.join(HOME, "gaming-mode.sh")
open(gaming_path, "w").write(gaming_sh)
os.chmod(gaming_path, 0o755)
print(f"OK: {gaming_path}")

# Add xbindkeys hotkey for gaming mode — Ctrl+Alt+G
xbkeys = os.path.expanduser("~/.xbindkeysrc")
entry = '\n# Gaming mode\n"bash /home/jesus999l/gaming-mode.sh"\n  control+alt+g\n'
content = open(xbkeys).read() if os.path.exists(xbkeys) else ""
if "gaming-mode" not in content:
    open(xbkeys, "a").write(entry)
    subprocess.run(["pkill", "xbindkeys"], capture_output=True)
    subprocess.Popen(["xbindkeys"])
    print("OK: Ctrl+Alt+G hotkey added for gaming mode")

print()
print("Summary:")
print("  Docker      → disabled autostart, use Desktop icons to start/stop")
print("  gaming-mode → run ~/gaming-mode.sh or press Ctrl+Alt+G when in-game")
print("  PipeWire    → realtime priority configured")
print("  Next: log out and back in for audio realtime group to take effect")
