# Echo Sync — Mobile Android

Echo has two distinct application surfaces:

- **Vision Assistant** — the laptop/desktop Echo environment. This is the desktop application and is where the ThinkPad-side perception, automation, local services, and desktop workflows live.
- **Echo Sync** — the Android/mobile application for the phone. It is the mobile UI and mobile-side bridge; it is **not** the Vision Assistant desktop UI.

## Current mobile build

- Package: `org.echosync.echosync`
- Version: `0.1` (debug build)
- APK: `mobile/EchoSync/EchoSync-debug.apk`
- Built on: 2026-08-16

## Install from Termux

From a clone of this repository:

```bash
cd ~/Echo
# or wherever this repository is cloned
curl -L -o EchoSync-debug.apk https://github.com/jesus999l/echo-vision/raw/echo-sync-mobile/mobile/EchoSync/EchoSync-debug.apk
adb install -r EchoSync-debug.apk
```

If the APK is already on the phone and you have a local file path, install it with Android's package installer or `adb` as appropriate.

## Important architecture note

GitHub is the distribution point for the **APK**. Tailscale is for reaching Echo services over the network; it is not required just to download/install the APK. The mobile app can therefore be updated while away from the ThinkPad, provided a new APK has been published here.

## Build provenance

This APK corresponds to the Echo Sync Android project under `~/Echo/Projects/EchoSync` on the ThinkPad. The current build was successfully compiled and installed during the 2026-08-16 recovery pass.

The current UI is still an early mobile shell. The conversation/history implementation is not yet the finished persistent, date-separated chat system; do not treat the current sidebar as proof that the full history pipeline is implemented.
