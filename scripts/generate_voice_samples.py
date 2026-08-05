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

# GMI's Inworld TTS voices (id doubles as display name — GMI doesn't expose
# separate ids, see app/pipelines.py GMI_TTS_MODEL). Transcribed from GMI's
# public docs (docs.gmicloud.ai), which is the only place this catalog is
# documented.
#
# inworld-tts-2 ships 65 voices across 16 languages, and a voice speaks the
# language it was built for — there is no language parameter that makes an
# English voice read German well. Offering only the 25 English ones therefore
# left every non-English character sounding like an American doing an accent,
# which is the real reason the picker felt thin.
#
# For the non-English voices the docs give the name and language only. Gender is
# filled in where the name makes it unambiguous and left as None where it does
# not (Yichen, Nour) — a wrong value is worse than an empty filter. Age and tone
# are undocumented for them, so they carry a neutral placeholder rather than an
# invented description.
GMI = [
    # ── English ──
    ("Alex", "male", "adult", "energetic, mid-range", "en"),
    ("Ashley", "female", "adult", "warm, natural", "en"),
    ("Blake", "male", "adult", "rich, intimate", "en"),
    ("Carter", "male", "mature", "radio announcer", "en"),
    ("Clive", "male", "adult", "British, calm", "en"),
    ("Craig", "male", "mature", "older British, refined", "en"),
    ("Deborah", "female", "mature", "gentle, elegant", "en"),
    ("Dennis", "male", "adult", "smooth, calm", "en"),
    ("Dominus", "male", "adult", "robotic, deep", "en"),
    ("Edward", "male", "adult", "fast-talking, emphatic", "en"),
    ("Elizabeth", "female", "adult", "professional", "en"),
    ("Hades", "male", "mature", "commanding, gruff", "en"),
    ("Hana", "female", "young", "bright, expressive", "en"),
    ("Julia", "female", "young", "quirky, high-pitched", "en"),
    ("Luna", "female", "adult", "calm, relaxing", "en"),
    ("Mark", "male", "adult", "energetic, rapid-fire", "en"),
    ("Olivia", "female", "young", "British, upbeat", "en"),
    ("Pixie", "female", "child", "childlike", "en"),
    ("Priya", "female", "adult", "Indian accent", "en"),
    ("Ronald", "male", "mature", "British, deep", "en"),
    ("Sarah", "female", "young", "young adult, natural", "en"),
    ("Shaun", "male", "adult", "friendly, dynamic", "en"),
    ("Theodore", "male", "mature", "gravelly, elderly", "en"),
    ("Timothy", "male", "young", "lively American", "en"),
    ("Wendy", "female", "adult", "British, posh", "en"),
    # ── German ──
    ("Johanna", "female", "adult", "native German", "de"),
    ("Josef", "male", "adult", "native German", "de"),
    # ── French ──
    ("Alain", "male", "adult", "native French", "fr"),
    ("Hélène", "female", "adult", "native French", "fr"),
    ("Mathieu", "male", "adult", "native French", "fr"),
    ("Étienne", "male", "adult", "native French", "fr"),
    # ── Spanish ──
    ("Diego", "male", "adult", "native Spanish", "es"),
    ("Lupita", "female", "adult", "native Spanish", "es"),
    ("Miguel", "male", "adult", "native Spanish", "es"),
    ("Rafael", "male", "adult", "native Spanish", "es"),
    # ── Italian ──
    ("Gianni", "male", "adult", "native Italian", "it"),
    ("Orietta", "female", "adult", "native Italian", "it"),
    # ── Portuguese (Brazil) ──
    ("Heitor", "male", "adult", "native Brazilian Portuguese", "pt"),
    ("Maitê", "female", "adult", "native Brazilian Portuguese", "pt"),
    # ── Dutch ──
    ("Erik", "male", "adult", "native Dutch", "nl"),
    ("Katrien", "female", "adult", "native Dutch", "nl"),
    ("Lennart", "male", "adult", "native Dutch", "nl"),
    ("Lore", "female", "adult", "native Dutch", "nl"),
    # ── Polish ──
    ("Szymon", "male", "adult", "native Polish", "pl"),
    ("Wojciech", "male", "adult", "native Polish", "pl"),
    # ── Russian ──
    ("Svetlana", "female", "adult", "native Russian", "ru"),
    ("Elena", "female", "adult", "native Russian", "ru"),
    ("Dmitry", "male", "adult", "native Russian", "ru"),
    ("Nikolai", "male", "adult", "native Russian", "ru"),
    # ── Chinese ──
    ("Yichen", None, "adult", "native Mandarin", "zh"),
    ("Xiaoyin", "female", "adult", "native Mandarin", "zh"),
    ("Xinyi", "female", "adult", "native Mandarin", "zh"),
    ("Jing", "female", "adult", "native Mandarin", "zh"),
    # ── Japanese ──
    ("Asuka", "female", "adult", "native Japanese", "ja"),
    ("Satoshi", "male", "adult", "native Japanese", "ja"),
    # ── Korean ──
    ("Hyunwoo", "male", "adult", "native Korean", "ko"),
    ("Minji", "female", "adult", "native Korean", "ko"),
    ("Seojun", "male", "adult", "native Korean", "ko"),
    ("Yoona", "female", "adult", "native Korean", "ko"),
    # ── Hindi ──
    ("Riya", "female", "adult", "native Hindi", "hi"),
    ("Manoj", "male", "adult", "native Hindi", "hi"),
    # ── Hebrew ──
    ("Yael", "female", "adult", "native Hebrew", "he"),
    ("Oren", "male", "adult", "native Hebrew", "he"),
    # ── Arabic ──
    ("Nour", None, "adult", "native Arabic", "ar"),
    ("Omar", "male", "adult", "native Arabic", "ar"),
]


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
