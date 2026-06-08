import os
import re
import subprocess
from echo_personality import EchoPersonalityEngine

def execute_echo_speech(input_text):
    model_path = "/home/jesus999l/Echo/AI/Voices/piper/models/en_US-lessac-medium.onnx"
    output_wav = "/tmp/echo_state_output.wav"
    
    persona = EchoPersonalityEngine()
    modulated_output = persona.mold_text(input_text)
    
    print(f"💬 [Echo]: {modulated_output}")
    
    tts_text = re.sub(r"\[([^\]]*)\]", r"\1... ", modulated_output)
    tts_text = re.sub(r"\([^)]*\)", "", tts_text)
    tts_text = re.sub(r":3", "", tts_text)
    tts_text = re.sub(r"\s+", " ", tts_text).strip()
    
    print(f"🗣️ [Sent to Piper]: {tts_text}")

    if not os.path.exists(model_path):
        print(f"[Error] Voice model path missing: {model_path}")
        return

    try:
        piper_bin = "/home/jesus999l/vision_env/bin/piper"
        if not os.path.exists(piper_bin):
            piper_bin = "piper"
            
        piper_cmd = [
            piper_bin, "-m", model_path, "-f", output_wav,
            "--length_scale", "1.05",
            "--noise_scale", "1.10",
            "--noise_w", "1.20",
            "--sentence_silence", "0.6"
        ]
        
        process = subprocess.Popen(piper_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        process.communicate(input=tts_text.encode('utf-8'))
        
        print("🔊 Rendering...")
        subprocess.run(["aplay", output_wav], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if os.path.exists(output_wav):
            os.remove(output_wav)
            
    except Exception as e:
        print(f"[Failure] {e}")

if __name__ == "__main__":
    execute_echo_speech("[Smiles and tilts head] hm... so what was your name?")
