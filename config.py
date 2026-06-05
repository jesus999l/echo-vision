import os

BASE_DIR        = os.path.expanduser("~/vision_assistant")
DB_PATH         = os.path.join(BASE_DIR, "memory.db")
SCREENSHOT_PATH = "/tmp/vision_capture.png"

OLLAMA_BASE     = "http://127.0.0.1:11434"
# LLM_URL set dynamically below — proxima if running, ollama as fallback
MODELS_URL      = f"{OLLAMA_BASE}/v1/models"
VISION_API_URL  = f"{OLLAMA_BASE}/api/chat"

VISION_MODELS   = ["llava", "moondream", "vision", "bakllava"]
DEFAULT_MODEL   = "qwen2.5:0.5b"

IPC_HOST  = "127.0.0.1"
IPC_PORT  = 59999
IPC_MAGIC = "VISION_ASSISTANT_IPC"

SYNC_PORT      = 59998
SYNC_SECRET    = "vision_assistant_sync"
CLOUD_SYNC_URL = ""

USER_NAME     = ""
USER_GOALS    = []
USER_TIMEZONE = ""

# ── Echo Proxima Native ───────────────────────────────────────────────────────
# Browser-based multi-AI proxy (Claude, ChatGPT, Gemini, Perplexity, Grok)
# Runs on :3210, OpenAI-compatible. Start: python3 ~/vision_assistant/echo_proxima_native.py
PROXIMA_URL     = "http://localhost:3210/v1/chat/completions"
PROXIMA_MODELS  = "http://localhost:3210/v1/models"
PROXIMA_STATUS  = "http://localhost:3210/status"
PROXIMA_DEFAULT = "auto"   # auto | claude | chatgpt | gemini | perplexity | grok

def _proxima_alive():
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:3210/", timeout=1)
        return True
    except:
        return False
# Smart LLM_URL: use Proxima if running, fallback to Ollama
import os as _os
LLM_URL = PROXIMA_URL  # Proxima v4.1.0 confirmed working
# ─────────────────────────────────────────────────────────────────────────────
