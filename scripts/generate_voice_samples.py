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

# GMI's Inworld TTS voices (id doubles as display name — GMI doesn't expose
# separate ids, see app/pipelines.py GMI_TTS_MODEL). Gender/age/style are
# transcribed from GMI's public docs (docs.gmicloud.ai), which is the only
# place this catalog is documented.
GMI = [
    ("Alex", "male", "adult", "energetic, mid-range"),
    ("Ashley", "female", "adult", "warm, natural"),
    ("Blake", "male", "adult", "rich, intimate"),
    ("Carter", "male", "mature", "radio announcer"),
    ("Clive", "male", "adult", "British, calm"),
    ("Craig", "male", "mature", "older British, refined"),
    ("Deborah", "female", "mature", "gentle, elegant"),
    ("Dennis", "male", "adult", "smooth, calm"),
    ("Dominus", "male", "adult", "robotic, deep"),
    ("Edward", "male", "adult", "fast-talking, emphatic"),
    ("Elizabeth", "female", "adult", "professional"),
    ("Hades", "male", "mature", "commanding, gruff"),
    ("Hana", "female", "young", "bright, expressive"),
    ("Julia", "female", "young", "quirky, high-pitched"),
    ("Luna", "female", "adult", "calm, relaxing"),
    ("Mark", "male", "adult", "energetic, rapid-fire"),
    ("Olivia", "female", "young", "British, upbeat"),
    ("Pixie", "female", "child", "childlike"),
    ("Priya", "female", "adult", "Indian accent"),
    ("Ronald", "male", "mature", "British, deep"),
    ("Sarah", "female", "young", "young adult, natural"),
    ("Shaun", "male", "adult", "friendly, dynamic"),
    ("Theodore", "male", "mature", "gravelly, elderly"),
    ("Timothy", "male", "young", "lively American"),
    ("Wendy", "female", "adult", "British, posh"),
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


GMI_PROD_URL = "https://character-vault-production-7da6.up.railway.app"


def gen_gmi():
    kept = []

    ws_req = urllib.request.Request(
        f"{GMI_PROD_URL}/workspaces",
        data=json.dumps({"name": "voice-sample-gen"}).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    workspace_id = json.loads(urllib.request.urlopen(ws_req, timeout=30).read())["id"]

    created_ids = []
    for vid, gender, age, style in GMI:
        body = json.dumps({"text": PHRASE, "voice_provider": "gmi", "voice_id": vid}).encode()
        req = urllib.request.Request(
            f"{GMI_PROD_URL}/audio", data=body,
            headers={"Content-Type": "application/json", "X-Workspace-Id": workspace_id},
            method="POST",
        )
        try:
            clip = json.loads(urllib.request.urlopen(req, timeout=180).read())
            created_ids.append(clip["id"])
            mp3 = urllib.request.urlopen(clip["url"], timeout=60).read()
            (OUT / f"gmi-{vid}.mp3").write_bytes(mp3)
            kept.append(entry("gmi", vid, vid, gender, age, style))
            print("gmi", vid, "ok")
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
