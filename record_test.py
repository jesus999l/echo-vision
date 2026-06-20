import sounddevice as sd
import scipy.io.wavfile as wav

fs = 16000  # Sample rate
seconds = 3  # Duration
print("Recording for 3 seconds...")
recording = sd.rec(int(seconds * fs), samplerate=fs, channels=1)
sd.wait()
wav.write('test_audio.wav', fs, recording)
print("Saved as test_audio.wav")
