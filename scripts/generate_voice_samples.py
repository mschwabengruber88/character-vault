"""One-off: build the voice catalog + a sample clip per voice.

Every voice speaks the same phrase so they can be auditioned side by side.
A rich candidate list (with gender/age/style metadata for filtering) is
attempted; only voices that actually produce audio are kept. The surviving
catalog is written to app/static/voice-samples/catalog.json and committed
alongside the mp3s.

OpenAI voices are generated locally via OPENAI_API_KEY. GMI voices go
through the deployed app's own /audio endpoint on production instead of
calling GMI directly — GMI_API_KEY lives only in Railway, not in the local
.env, and this reuses the already-verified generation path rather than
duplicating it. Each sample clip is created as a throwaway audio asset in a
scratch workspace on prod, downloaded, then deleted again so it doesn't
clutter the real gallery.
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PHRASE = "Hi! I'm your character. This is what my voice sounds like."

# A German voice reading an English sentence tells you nothing about how it
# will sound in use, so each language previews in its own words.
PHRASES = {
    "en": PHRASE,
    "de": "Hallo! Ich bin deine Figur. So klingt meine Stimme.",
    "fr": "Bonjour ! Je suis ton personnage. Voici à quoi ressemble ma voix.",
    "es": "¡Hola! Soy tu personaje. Así suena mi voz.",
    "it": "Ciao! Sono il tuo personaggio. Ecco come suona la mia voce.",
    "pt": "Olá! Eu sou o seu personagem. É assim que a minha voz soa.",
    "nl": "Hallo! Ik ben jouw personage. Zo klinkt mijn stem.",
    "pl": "Cześć! Jestem twoją postacią. Tak brzmi mój głos.",
    "ru": "Привет! Я твой персонаж. Вот так звучит мой голос.",
    "zh": "你好！我是你的角色。这就是我的声音。",
    "ja": "こんにちは！私はあなたのキャラクターです。これが私の声です。",
    "ko": "안녕하세요! 저는 당신의 캐릭터입니다. 제 목소리는 이렇습니다.",
    "hi": "नमस्ते! मैं आपका किरदार हूँ। मेरी आवाज़ ऐसी लगती है।",
    "he": "שלום! אני הדמות שלך. כך נשמע הקול שלי.",
    "ar": "مرحباً! أنا شخصيتك. هكذا يبدو صوتي.",
}
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
    # Added later by OpenAI. marin and cedar are the two the docs single out for
    # quality-focused use, so they belong in the picker rather than being left
    # out because the list was written before they existed.
    ("verse", "Verse", "male", "adult", "expressive"),
    ("marin", "Marin", "female", "adult", "natural, high quality"),
    ("cedar", "Cedar", "male", "adult", "natural, high quality"),
]

# Single source of truth: the roster lives in app.pipelines, which is also what
# the server validates a chosen voice against. Keeping a second copy here is
# exactly what let the two drift apart — and what made a new voice unusable
# until it had already been recorded.
import sys as _sys  # noqa: E402

_sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.pipelines import GMI_VOICE_ROSTER as GMI  # noqa: E402


def entry(provider, vid, name, gender, age, style, language):
    return {"id": vid, "name": name, "provider": provider,
            "gender": gender, "age": age, "style": style, "language": language}


# OpenAI's voices are not tied to one language — the same voice reads German,
# French or Japanese acceptably — so they are tagged "multi" and stay visible
# whichever language is being filtered for.
OPENAI_LANGUAGE = "multi"


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
            kept.append(entry("openai", vid, name, gender, age, style, OPENAI_LANGUAGE))
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
                               f"pitched-up, {base[4]}", OPENAI_LANGUAGE))
            print("openai", label, "ok (pitch-shifted from", base_voice, ")")
        except Exception as e:
            print("openai", label, "FAILED", str(e)[:100])
    return kept


# Samples are generated through a running deployment rather than by calling GMI
# directly: the GMI key lives on the server, never in a local .env. Point this
# at whichever instance is live — the Railway host it used to name is gone.
GMI_PROD_URL = os.environ.get("SAMPLE_SOURCE_URL", "https://loomina.duckdns.org")


def gen_gmi():
    kept = []

    # Owner bypass: if GENERATE_API_KEY is set locally, send it so calls skip
    # the shared free-tier rate limit entirely instead of competing with real
    # traffic for the daily budget.
    owner_key = os.environ.get("GENERATE_API_KEY", "")
    base_headers = {"Content-Type": "application/json"}
    if owner_key:
        base_headers["X-API-Key"] = owner_key

    ws_req = urllib.request.Request(
        f"{GMI_PROD_URL}/workspaces",
        data=json.dumps({"name": "voice-sample-gen"}).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    workspace_id = json.loads(urllib.request.urlopen(ws_req, timeout=30).read())["id"]

    created_ids = []
    for vid, gender, age, style, language in GMI:
        body = json.dumps({"text": PHRASES.get(language, PHRASE),
                           "voice_provider": "gmi", "voice_id": vid}).encode()
        req = urllib.request.Request(
            f"{GMI_PROD_URL}/audio", data=body,
            headers={**base_headers, "X-Workspace-Id": workspace_id},
            method="POST",
        )
        try:
            clip = json.loads(urllib.request.urlopen(req, timeout=180).read())
            created_ids.append(clip["id"])
            mp3 = urllib.request.urlopen(clip["signed_url"], timeout=60).read()
            (OUT / f"gmi-{vid}.mp3").write_bytes(mp3)
            kept.append(entry("gmi", vid, vid, gender, age, style, language))
            print("gmi", vid, "ok")
        except urllib.error.HTTPError as e:
            print("gmi", vid, "FAILED", e.code, e.read()[:300])
        except Exception as e:
            print("gmi", vid, "FAILED", str(e)[:150])

    for clip_id in created_ids:
        try:
            del_req = urllib.request.Request(
                f"{GMI_PROD_URL}/audio/{clip_id}",
                headers={"X-Workspace-Id": workspace_id}, method="DELETE",
            )
            urllib.request.urlopen(del_req, timeout=30)
        except Exception as e:
            print("cleanup FAILED for clip", clip_id, str(e)[:100])

    return kept


if __name__ == "__main__":
    catalog = {"openai": gen_openai(), "gmi": gen_gmi()}
    (OUT / "catalog.json").write_text(json.dumps(catalog, indent=2))
    print(f"\ncatalog: {len(catalog['openai'])} openai + {len(catalog['gmi'])} gmi")
