import requests
url = "http://127.0.0.1:3210/transcribe"
files = {'file': open('test_audio.wav', 'rb')}
response = requests.post(url, files=files)
print(response.json())
