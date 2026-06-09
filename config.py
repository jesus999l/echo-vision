import os

BASE_DIR        = os.path.expanduser("~/vision_assistant")
DB_PATH         = os.path.join(BASE_DIR, "memory.db")
SCREENSHOT_PATH = "/tmp/vision_capture.png"

OLLAMA_BASE     = "http://127.0.0.1:11434"
LLM_URL         = "http://127.0.0.1:3210/v1/chat/completions"
MODELS_URL      = f"{OLLAMA_BASE}/v1/models"
VISION_API_URL  = f"{OLLAMA_BASE}/api/chat"

VISION_MODELS   = ["llava", "moondream", "vision", "bakllava"]
DEFAULT_MODEL   = "perplexity"

IPC_HOST  = "127.0.0.1"
IPC_PORT  = 59999
IPC_MAGIC = "VISION_ASSISTANT_IPC"

SYNC_PORT      = 59998
SYNC_SECRET    = "vision_assistant_sync"
CLOUD_SYNC_URL = ""

USER_NAME     = ""
USER_GOALS    = []
USER_TIMEZONE = ""
