"""One-off: generate a short sample clip per voice for the UI preview.

Every voice speaks the same phrase so they can be auditioned side by side.
OpenAI TTS is generated via the OpenAI SDK; ElevenLabs via its REST API
(run this from a residential IP — ElevenLabs' free tier blocks datacenter
IPs). Output lands in app/static/voice-samples/ and is committed.
"""

import json
import os
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PHRASE = "Hi! I'm your character. This is what my voice sounds like."
OUT = Path(__file__).resolve().parent.parent / "app" / "static" / "voice-samples"
OUT.mkdir(parents=True, exist_ok=True)

OPENAI_VOICES = ["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer"]
ELEVENLABS_VOICES = [
    "JBFqnCBsd6RMkjVDRZzb", "nPczCjzI2devNBz1zQrb", "21m00Tcm4TlvDq8ikWAM",
    "EXAVITQu4vr4xnSDxMaL", "pFZP5JQG7iQjIQuC4Bku", "TX3LPaxmHKxFdv7VOQHJ",
]


def gen_openai():
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    for v in OPENAI_VOICES:
        path = OUT / f"openai-{v}.mp3"
        resp = client.audio.speech.create(model="gpt-4o-mini-tts", voice=v, input=PHRASE)
        path.write_bytes(resp.content)
        print("openai", v, path.stat().st_size, "bytes")


def gen_elevenlabs():
    key = os.environ["ELEVENLABS_API_KEY"]
    for vid in ELEVENLABS_VOICES:
        path = OUT / f"elevenlabs-{vid}.mp3"
        body = json.dumps({"text": PHRASE, "model_id": "eleven_multilingual_v2"}).encode()
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
            data=body,
            headers={"xi-api-key": key, "Content-Type": "application/json"},
        )
        try:
            mp3 = urllib.request.urlopen(req, timeout=30).read()
            path.write_bytes(mp3)
            print("elevenlabs", vid, path.stat().st_size, "bytes")
        except Exception as e:
            print("elevenlabs", vid, "FAILED", str(e)[:120])


if __name__ == "__main__":
    gen_openai()
    gen_elevenlabs()
