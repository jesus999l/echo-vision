#!/usr/bin/env bash

set -e

GAME_ID=22380
STEAM_DIR="$HOME/.steam/steam"
GAME_DIR="$STEAM_DIR/steamapps/common/Fallout New Vegas"
PFX_DIR="$STEAM_DIR/steamapps/compatdata/$GAME_ID"

echo "[+] Killing any running Steam processes..."
pkill steam || true

echo "[+] Removing broken Proton prefix..."
rm -rf "$PFX_DIR"

echo "[+] Restarting Steam..."
steam &

echo "[*] WAIT: Steam is launching."
echo "    When it's open, press ENTER to continue..."
read

echo "[+] Launching New Vegas once to rebuild prefix..."
steam -applaunch $GAME_ID

echo "[*] WAIT: Let the game reach the main menu, then close it."
echo "    Press ENTER after closing the game..."
read

echo "[+] Checking game directory..."
if [ ! -d "$GAME_DIR" ]; then
    echo "[-] Game directory not found!"
    exit 1
fi

echo "[+] Creating mod staging folders..."
mkdir -p "$HOME/FNV_MODS/core"
mkdir -p "$HOME/FNV_MODS/gameplay"
mkdir -p "$HOME/FNV_MODS/visuals"

echo "[+] DONE."
echo ""
echo "NEXT STEPS:"
echo "1. Install NVSE manually into:"
echo "   $GAME_DIR"
echo ""
echo "2. In Steam -> New Vegas -> Properties -> Launch Options:"
echo "   nvse_loader.exe"
echo ""
echo "3. Never use wine for this game again. Proton runs everything."
