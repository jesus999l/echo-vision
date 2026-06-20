from tortoise.api import TextToSpeech
from tortoise.utils.audio import load_voice
import torchaudio
import os

print("Initializing local Tortoise TTS engine...")
tts = TextToSpeech()

voice_dir = os.path.expanduser('~/vision_assistant/voices/')
print(f"Loading custom Cyn voice clips from: {voice_dir}")
voice_samples, conditioning_latents = load_voice('cyn', extra_voice_dirs=[voice_dir])

text = "System synchronization complete. Proxima bridge pipeline online."
print(f"Generating audio: '{text}'")

# Updated syntax for version 3.0.0
gen = tts.tts(text, voice_samples=voice_samples, use_deterministic_seed=42)
torchaudio.save('/tmp/cyn_output.wav', gen.squeeze(0).cpu(), 24000)
print("✓ Audio saved cleanly to /tmp/cyn_output.wav!")
