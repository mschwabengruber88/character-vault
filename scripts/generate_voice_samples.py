"""One-off: build the voice catalog + a sample clip per voice.

Every voice speaks the same phrase so they can be auditioned side by side.
A rich candidate list (with gender/age/style metadata for filtering) is
attempted; only voices that actually produce audio are kept. The surviving
catalog is written to app/static/voice-samples/catalog.json and committed
alongside the mp3s.

Run from a residential IP — ElevenLabs' free tier blocks datacenter IPs and
gates some voices behind a paid plan (those are dropped automatically).
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

# provider, id, name, gender (female/male/neutral), age (young/adult/mature), style
OPENAI = [
    ("alloy", "Alloy", "neutral", "adult", "balanced"),
    ("ash", "Ash", "male", "adult", "warm"),
    ("ballad", "Ballad", "male", "young", "soft"),
    ("coral", "Coral", "female", "young", "bright"),
    ("echo", "Echo", "male", "adult", "calm"),
    ("fable", "Fable", "neutral", "adult", "storyteller"),
    ("nova", "Nova", "female", "young", "friendly"),
    ("onyx", "Onyx", "male", "mature", "deep"),
    ("sage", "Sage", "female", "adult", "measured"),
    ("shimmer", "Shimmer", "female", "young", "light"),
]

ELEVENLABS = [
    ("9BWtsMINqrJLrRacOk9x", "Aria", "female", "adult", "expressive"),
    ("CwhRBWXzGAHq8TQ4Fs17", "Roger", "male", "adult", "casual"),
    ("EXAVITQu4vr4xnSDxMaL", "Sarah", "female", "young", "soft"),
    ("FGY2WhTYpPnrIDTdsKH5", "Laura", "female", "young", "sassy"),
    ("IKne3meq5aSn9XLyUdCD", "Charlie", "male", "adult", "casual"),
    ("JBFqnCBsd6RMkjVDRZzb", "George", "male", "mature", "warm storyteller"),
    ("N2lVS1w4EtoT3dr4eOWO", "Callum", "male", "adult", "intense"),
    ("SAz9YHcvj6GT2YYXdXww", "River", "neutral", "adult", "calm"),
    ("TX3LPaxmHKxFdv7VOQHJ", "Liam", "male", "young", "articulate"),
    ("XB0fDUnXU5powFXDhCwa", "Charlotte", "female", "young", "gentle"),
    ("Xb7hH8MSUJpSbSDYk0k2", "Alice", "female", "adult", "confident"),
    ("XrExE9yKIg1WjnnlVkGX", "Matilda", "female", "adult", "warm"),
    ("bIHbv24MWmeRgasZH58o", "Will", "male", "young", "friendly"),
    ("cgSgspJ2msm6clMCkdW9", "Jessica", "female", "young", "playful"),
    ("cjVigY5qzO86Huf0OWal", "Eric", "male", "adult", "smooth"),
    ("iP95p4xoKVk53GoZ742B", "Chris", "male", "adult", "casual"),
    ("nPczCjzI2devNBz1zQrb", "Brian", "male", "mature", "deep"),
    ("onwK4e9ZLuTAKqWW03F9", "Daniel", "male", "adult", "news"),
    ("pFZP5JQG7iQjIQuC4Bku", "Lily", "female", "adult", "warm"),
    ("pqHfZKP75CvOlQylNhV4", "Bill", "male", "mature", "trustworthy"),
]


def entry(provider, vid, name, gender, age, style):
    return {"id": vid, "name": name, "provider": provider,
            "gender": gender, "age": age, "style": style}


def gen_openai():
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    kept = []
    raw = {}
    for vid, name, gender, age, style in OPENAI:
        try:
            resp = client.audio.speech.create(model="gpt-4o-mini-tts", voice=vid, input=PHRASE)
            raw[vid] = resp.content
            (OUT / f"openai-{vid}.mp3").write_bytes(resp.content)
            kept.append(entry("openai", vid, name, gender, age, style))
            print("openai", vid, "ok")
        except Exception as e:
            print("openai", vid, "FAILED", str(e)[:100])
    kept += gen_openai_child_variants(raw)
    return kept


# Neither provider ships a genuinely childlike voice on a free plan (see
# app.pipelines._CHILD_VOICE_BASE for why). These pitch an existing base
# clip up a few semitones instead — reuses app.pipelines so the sample
# clips and the live generation path can never drift apart.
def gen_openai_child_variants(raw: dict) -> list:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.pipelines import _CHILD_VOICE_BASE, _pitch_shift

    kept = []
    for label, (base_voice, semitones) in _CHILD_VOICE_BASE.items():
        if base_voice not in raw:
            continue
        try:
            shifted = _pitch_shift(raw[base_voice], semitones)
            (OUT / f"openai-{label}.mp3").write_bytes(shifted)
            base = next(e for e in OPENAI if e[0] == base_voice)
            kept.append(entry("openai", label, f"{base[1]} (Kid)", base[2], "child",
                               f"pitched-up, {base[4]}"))
            print("openai", label, "ok (pitch-shifted from", base_voice, ")")
        except Exception as e:
            print("openai", label, "FAILED", str(e)[:100])
    return kept


def gen_elevenlabs():
    key = os.environ.get("ELEVENLABS_API_KEY")
    kept = []
    if not key:
        return kept
    for vid, name, gender, age, style in ELEVENLABS:
        body = json.dumps({"text": PHRASE, "model_id": "eleven_multilingual_v2"}).encode()
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
            data=body, headers={"xi-api-key": key, "Content-Type": "application/json"},
        )
        try:
            mp3 = urllib.request.urlopen(req, timeout=30).read()
            (OUT / f"elevenlabs-{vid}.mp3").write_bytes(mp3)
            kept.append(entry("elevenlabs", vid, name, gender, age, style))
            print("elevenlabs", name, "ok")
        except Exception as e:
            print("elevenlabs", name, "FAILED", str(e)[:80])
    return kept


if __name__ == "__main__":
    catalog = {"openai": gen_openai(), "elevenlabs": gen_elevenlabs()}
    (OUT / "catalog.json").write_text(json.dumps(catalog, indent=2))
    print(f"\ncatalog: {len(catalog['openai'])} openai + {len(catalog['elevenlabs'])} elevenlabs")
