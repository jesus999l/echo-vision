#!/bin/bash
export DISPLAY=:0
export GDK_BACKEND=x11
export WAYLAND_DISPLAY=wayland-1
pkill -f echo_shadow_cursor 2>/dev/null
fuser -k 59998/tcp 2>/dev/null
sleep 1
nohup /home/jesus999l/vision_env/bin/python3 /home/jesus999l/vision_assistant/echo_shadow_cursor.py </dev/null >> /tmp/echo_shadow.log 2>&1 &
sleep 2
echo '{"action":"follow","enabled":true}' | nc -q1 127.0.0.1 59998
