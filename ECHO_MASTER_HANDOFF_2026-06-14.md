# Echo Session Handoff — June 14 2026

## What We Built Today

### Voice Pipeline
- Piper TTS + sox: pitch 250, rate 18000, overdrive 2, vol 0.6
- Pipeline: wake_word -> echo_proxima_bridge -> voice.speak() -> piper | sox | aplay
- XTTS v2 Cyn voice clone tested on Colab, saved to ~/Echo/AI/Voices/cyn_clone_test.wav
- XTTS can't run locally (no GPU, Python 3.12) — use Colab for batch generation

### Proxima Routing Fixed
- echo_proxima_bridge.py PROXIMA_URL = http://localhost:3211
- Proxima Electron runs at :3211, echo_proxima_native holds :3210
- Start: cd ~/Proxima && nohup ./node_modules/.bin/electron . </dev/null >> /tmp/proxima_electron.log 2>&1 &
- Full pipeline: wake word -> ChatGPT via Proxima cookies WORKS

### CPU Cleanup
- Disabled hyperspace + openclaw-gateway systemd user services (were eating 50%+ CPU)
- Commands used: systemctl --user disable hyperspace hyperspace-updater openclaw-gateway

## Port Map
- :3210 echo_proxima_native (Ollama, offline fallback ONLY)
- :3211 Proxima Electron (ChatGPT/Gemini/Perplexity cookies)
- :8080 Open WebUI (disable to save CPU)
- :8484 echo_group_chat_server
- :8765 echo_rest FastAPI
- :7799 echo_task_manager
- :59996 Proxima browser server

## Key Files Changed
- ~/vision_assistant/voice.py sox pipeline tuned
- ~/vision_assistant/echo_proxima_bridge.py PROXIMA_URL fixed to :3211

## Next Session
1. Build echo_brainbridge.py parallel ChatGPT+Gemini+Perplexity synthesized
2. Add Grok + Copilot to Proxima engines
3. Wire wake_word to echo_brainbridge
4. Build echo_vault.py Obsidian replacement port 8767
5. Batch generate Cyn voice lines on Colab
6. Add pactl mic setup to start-echo.sh
7. Disable open_webui autostart

## Boot Sequence
bash ~/vision_assistant/start-echo.sh
cd ~/Proxima && nohup ./node_modules/.bin/electron . </dev/null >> /tmp/proxima_electron.log 2>&1 &
pactl set-default-source bluez_input.98_67_2E_E3_7F_5D.0

## Cyn Voice Settings
- Piper model: ~/Echo/AI/Voices/piper/models/en_US-lessac-medium.onnx
- Sox: pitch 250 rate 18000 overdrive 2 vol 0.6
- XTTS ref: ~/Echo/AI/Voices/cyn_clone_test.wav

## SSD Health
- Media_Wearout_Indicator 7/100 CRITICAL
- Avoid large writes, move ROMs to external drive ASAP

## echo_ai_hub.py STATUS (June 14 end of session)
- Perplexity: WORKING
- ChatGPT + Claude: brotli encoding error (fix: ClientSession Accept-Encoding gzip)
- Gemini: no response (token extraction needs debugging)
- wake_word still on echo_brainbridge (Proxima :3211) — switch to echo_ai_hub once all providers work
- Next: fix brotli, parse perplexity JSON properly, wire into wake_word

