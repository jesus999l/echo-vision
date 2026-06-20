#!/usr/bin/env python3
import os, json, re, asyncio, uvicorn, logging
import httpx
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("echo-proxima")
engine = os.environ.get("WHISPER_ENGINE", "openai")
model = None
LOCAL_MODEL = "qwen3:4b"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    log.info(f"Initializing whisper: {engine.upper()}...")
    try:
        if engine == "faster":
            from faster_whisper import WhisperModel
            model = WhisperModel("/home/jesus999l/vision_assistant/model_fixed/whisper-base-ct2", device="cpu", compute_type="int8")
        else:
            import whisper
            model = whisper.load_model("base", device="cpu", download_root="/home/jesus999l/vision_assistant/model_fixed/")
        log.info("Whisper ready.")
    except Exception as e:
        log.error(f"Whisper init failed: {e}")
    yield
    model = None

app = FastAPI(lifespan=lifespan)

@app.get("/")
def read_root():
    return {"status": f"Whisper server active using {engine}"}

@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    temp_path = "temp_audio.wav"
    with open(temp_path, "wb") as buffer:
        buffer.write(await file.read())
    if engine == "faster":
        segments, _ = model.transcribe(temp_path)
        text = " ".join([s.text for s in segments])
    else:
        result = model.transcribe(temp_path)
        text = result["text"]
    return {"text": text}

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    prompt = "\n".join(f"{m.get('role','user').upper()}: {m.get('content','')}" for m in messages)
    payload = {
        "model": LOCAL_MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "num_predict": 80,
        "keep_alive": -1,
        "options": {"temperature": 0.7}
    }
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(OLLAMA_URL, json=payload)
            data = r.json()
            raw = data.get("response", "")
            raw = raw.replace("\u003c/think\u003e", "</think>").replace("\u003cthink\u003e", "<think>")
            if "</think>" in raw:
                raw = raw.split("</think>")[-1].strip()
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            text = raw if raw else "No response."
    except Exception as e:
        log.error(f"Ollama error: {e}")
        text = "Local model unavailable."
    return JSONResponse({
        "id": "echo-local",
        "model": LOCAL_MODEL,
        "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "proxima": {"provider": "ollama_local", "responseTimeMs": 0}
    })

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=3210)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port)
