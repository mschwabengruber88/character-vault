import hashlib
import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from genblaze_core import KeyStrategy, Modality, ObjectStorageSink, Pipeline, StepStatus
from genblaze_core.models.asset import Asset
from genblaze_openai import DalleProvider, OpenAITTSProvider
from genblaze_s3 import S3StorageBackend

from app.config import (
    B2_BUCKET_NAME,
    B2_REGION,
    GMI_API_KEY,
    OPENAI_API_KEY,
    SEQUENCE_CACHE_DIR,
    SEQUENCE_CACHE_MAX_MB,
)

logger = logging.getLogger("character_vault.pipelines")

_sink: ObjectStorageSink | None = None


def get_storage_sink() -> ObjectStorageSink:
    global _sink
    if _sink is None:
        backend_kwargs = {"region": B2_REGION} if B2_REGION else {}
        _sink = ObjectStorageSink(
            S3StorageBackend.for_backblaze(B2_BUCKET_NAME, **backend_kwargs),
            key_strategy=KeyStrategy.HIERARCHICAL,
        )
    return _sink


def _asset_result(result) -> dict:
    step = result.run.steps[0]
    if step.status != StepStatus.SUCCEEDED or not step.assets:
        raise RuntimeError(step.error or f"step ended with status={step.status}")
    asset = step.assets[0]
    return {
        "url": asset.url,
        "sha256": asset.sha256,
        "mime_type": asset.media_type,
        "manifest_verified": result.manifest.verify(),
    }


# Style is per character, always. A photoreal person and a drawn character
# share the frame the way Meister Eder and Pumuckl do — neither is converted
# into the other's medium.
#
# This used to demand ONE art style across the whole image, which was aimed at
# a different bug: the model would colour a single character's hair while the
# rest of a manga panel stayed monochrome. That rule is kept below, but scoped
# to *arbitrary* recolouring rather than to the medium itself — otherwise it
# flattens exactly the mix we want.
#
# "Cartoon" alone is not enough to keep a drawn character drawn: image models
# read it as 3D CGI (Pixar-style), which is what most of their cartoon training
# data looks like, so a flat children's-book fox came back sculpted and glossy.
# The medium rule therefore names the 3D look explicitly and rules it out.
SCENE_INSTRUCTION = (
    "Compose a single new image containing ALL of these characters together in "
    "one scene, each matching their own reference image exactly (same face, hair, "
    "colors, and outfit). Do not merge or swap their features. "
    "CRITICAL — every character keeps the art style and medium of their OWN "
    "reference: a character referenced by a photograph stays fully "
    "photorealistic, and a character referenced by a cartoon, painting or "
    "illustration stays drawn in exactly that style, down to line weight and "
    "shading. Never harmonise, average or convert them into one shared style; "
    "do not make the drawn character photoreal, and do not make the "
    "photographed character drawn. Mixed media in one frame is intended. "
    "A flat 2D drawing must stay flat 2D: keep the reference's visible linework, "
    "its flat or hand-shaded colour, and its drawn-on-paper surface. Do NOT "
    "re-render a drawn character as a 3D model, CGI or Pixar/DreamWorks-style "
    "animation — no sculpted volume, no glossy or plastic surfaces, no rendered "
    "fur or skin shading, no smooth digital gradients or ray-traced highlights "
    "on a character whose reference has none of them. "
    "What they DO share is the place: one lighting direction and colour "
    "temperature, one perspective and horizon, consistent relative scale, and "
    "contact with the same ground, with shadows to match — so the composite "
    "reads as a single scene rather than cut-out figures pasted together. "
    "Keep each character's own palette as it appears in their reference; never "
    "invent colour for a character whose reference has none, and never leave "
    "one character's clothing or hair oddly recoloured against their own "
    "reference. If the scene includes speech "
    "bubbles, draw each bubble's tail pointing clearly at the character who is "
    "speaking it, positioned near their mouth, so it's unambiguous who says what. "
)

IDENTITY_INSTRUCTION = (
    "Use the person from the reference image(s) and keep their identity exactly: "
    "same face, facial features, hair color and style, age, and build. "
    "Render that same person in a new scene: "
)

# OpenAI API list prices per 1024x1024 image for gpt-image-2 (August 2026);
# draft iterations cost ~35x less than finals — the main waste-reduction lever.
# The spread widened with gpt-image-2: drafts got cheaper than on gpt-image-1
# ($0.006 vs $0.011), finals dearer ($0.211 vs $0.167). Iterating in draft and
# rendering only the keeper in final therefore pays off more than before.
QUALITY_TIERS = {"draft": "low", "final": "high"}
IMAGE_COST_USD = {"draft": 0.006, "final": 0.211}

# Image-model registry. gpt-image-2 (OpenAI) is the general-purpose model
# with only loose "family resemblance" from references. flux-kontext-pro and
# gemini-2.5-flash-image ("Nano Banana") run on GMI Cloud and do real
# identity conditioning from reference images — purpose-built for keeping the
# same character across scenes. GMI models take references as HTTPS URLs;
# OpenAI takes them as local files (different SDK requirements).
# Note: GMI's flux-kontext-pro is deployed as text-to-image ONLY (no image
# input), so it cannot do identity conditioning from a reference — it would
# silently ignore the reference. It's deliberately not offered here.
# gemini-2.5-flash-image (Nano Banana) is the verified identity model.
IMAGE_MODELS = {
    "gpt-image-2": {
        "label": "OpenAI gpt-image-2",
        "provider": "openai",
        "identity": False,
        "quality_tiers": True,
    },
    "gemini-2.5-flash-image": {
        "label": "Nano Banana / Gemini 2.5 Flash Image (identity)",
        "provider": "gmi",
        "identity": True,
        "quality_tiers": False,
        "cost_usd": 0.039,  # GMI list price estimate
    },
}
DEFAULT_IMAGE_MODEL = "gpt-image-2"


def available_image_models() -> list[dict]:
    """Models the server can actually call, given configured keys."""
    out = []
    for slug, meta in IMAGE_MODELS.items():
        if meta["provider"] == "gmi" and not GMI_API_KEY:
            continue
        out.append({
            "slug": slug,
            "label": meta["label"],
            "identity": meta["identity"],
            "quality_tiers": meta["quality_tiers"],
            "cost_draft": IMAGE_COST_USD["draft"] if meta["quality_tiers"] else None,
            "cost_final": IMAGE_COST_USD["final"] if meta["quality_tiers"] else None,
            "cost": meta.get("cost_usd"),
        })
    return out


def _gmi_references(references: list[dict], limit: int = 3) -> list[Asset]:
    """GMI Cloud requires HTTPS reference URLs — use presigned B2 links."""
    from app.storage import presign_asset_url

    assets = []
    for ref in references[:limit]:
        signed = presign_asset_url(ref["url"])
        if signed:
            assets.append(Asset(url=signed, media_type="image/png", sha256=ref.get("sha256")))
    return assets

# gpt-4o-mini-tts: ~$12 per 1M input characters. GMI's Inworld TTS pricing
# isn't publicly listed, so we don't guess it (cost stays None).
OPENAI_TTS_USD_PER_CHAR = 12 / 1_000_000


def _fetch_references_to_temp(references: list[dict]) -> tuple[list[Asset], list[Path]]:
    """Download reference originals from B2 to local .png temp files.

    The OpenAI SDK infers upload MIME type from the file suffix, so the
    provider's own https download (suffix .img) gets rejected as
    octet-stream — local file:// inputs with a .png suffix don't. The
    stored sha256 rides along so the provenance manifest stays stable.
    """
    from app.disclosure import _bucket_key
    from app.storage import _s3_client

    client = _s3_client()
    assets: list[Asset] = []
    temps: list[Path] = []
    for ref in references[:3]:
        data = client.get_object(Bucket=B2_BUCKET_NAME, Key=_bucket_key(ref["url"]))["Body"].read()
        fd, tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        path = Path(tmp)
        path.write_bytes(data)
        temps.append(path)
        assets.append(Asset(url=path.as_uri(), media_type="image/png", sha256=ref.get("sha256")))
    return assets, temps


def generate_character_portrait(
    character_id: int,
    prompt: str,
    disclosure: str = "invisible",
    references: list[dict] | None = None,
    quality: str = "draft",
    model: str = DEFAULT_IMAGE_MODEL,
    personality: str | None = None,
    seed: int | None = None,
) -> dict:
    from app.disclosure import apply_image_disclosure

    meta = IMAGE_MODELS[model]
    step_kwargs: dict = {}
    final_prompt = prompt
    temps: list[Path] = []

    if references:
        if meta["provider"] == "gmi":
            inputs = _gmi_references(references)
        else:
            inputs, temps = _fetch_references_to_temp(references)
        if inputs:
            step_kwargs["external_inputs"] = inputs
            final_prompt = IDENTITY_INSTRUCTION + prompt

    # The character's personality shapes expression, posture and mood.
    if personality:
        final_prompt = f"{final_prompt}. Character personality to convey through expression and body language: {personality}"

    if meta["provider"] == "gmi":
        from genblaze_gmicloud import GMICloudImageProvider

        provider = GMICloudImageProvider()
        if seed is not None:
            step_kwargs["seed"] = seed
    else:
        # DalleProvider defaults to a 60s HTTP timeout, which only ever fit
        # drafts. Measured against gpt-image-2: a draft generate returns in
        # ~20s, but a *final* edit conditioned on a reference portrait takes
        # ~160s — so every final-quality portrait died on the timeout rather
        # than on anything OpenAI did wrong.
        provider = DalleProvider(http_timeout=300.0)
        step_kwargs["size"] = "1024x1024"
        step_kwargs["quality"] = QUALITY_TIERS[quality]

    try:
        result = (
            Pipeline(f"character-{character_id}-portrait")
            .step(
                provider,
                model=model,
                prompt=final_prompt,
                modality=Modality.IMAGE,
                **step_kwargs,
            )
            .run(sink=get_storage_sink(), timeout=360)
        )
    finally:
        for path in temps:
            path.unlink(missing_ok=True)

    asset = _asset_result(result)
    asset["original_url"] = asset["url"]
    asset["url"] = apply_image_disclosure(asset["url"], result.manifest, disclosure)
    asset["disclosure"] = disclosure
    asset["model"] = model
    asset["seed"] = seed if meta["provider"] == "gmi" else None  # only GMI models honor it
    if meta["quality_tiers"]:
        asset["quality"] = quality
        asset["cost_usd"] = IMAGE_COST_USD[quality]
    else:
        asset["quality"] = None
        asset["cost_usd"] = meta.get("cost_usd")
    return asset


# ── Ebene 2: image-generation modes ──────────────────────────────────────
# One standing character → many images. The mode decides the PROMPT STRATEGY:
# a variation set deliberately changes outfit/pose/background each frame; a
# photoshoot locks wardrobe & location and only moves the camera; a story
# turns a script into one panel per beat. Identity is held across every frame
# by the same reference portraits + seed, so the person stays the same person.
MODE_MAX = {"single": 1, "variation": 100, "photoshoot": 100, "story": 60}

# Rotated per frame so a set genuinely varies instead of drifting by luck.
_VARIATION_AXES = [
    "wearing a completely different outfit",
    "in a different pose and gesture",
    "against a different background/location",
    "in different lighting and time of day",
    "with a different facial expression and mood",
    "seen from a different camera angle",
    "in a different season and weather",
    "doing a different everyday activity",
]

# A photoshoot keeps the SAME wardrobe/location/light — only the shot changes.
_PHOTOSHOOT_SHOTS = [
    "tight head-and-shoulders portrait, eye contact",
    "three-quarter body shot, relaxed stance",
    "full-body shot",
    "side profile view",
    "candid shot looking away from camera",
    "over-the-shoulder glance back at the camera",
    "low-angle hero shot",
    "soft-smile close-up",
]

_PHOTOSHOOT_LOCK = (
    "Professional photo session: keep the EXACT same outfit, hairstyle, makeup, "
    "location and lighting consistent across every shot. This frame: "
)


def _split_story_beats(script: str, limit: int) -> list[str]:
    """Turn a script into ordered beats — one image per beat. Blank-line or
    newline separated lines are beats; a single blob is split by sentence."""
    lines = [ln.strip(" -•\t") for ln in script.splitlines() if ln.strip(" -•\t")]
    if len(lines) <= 1:
        import re

        blob = lines[0] if lines else script.strip()
        lines = [s.strip() for s in re.split(r"(?<=[.!?])\s+", blob) if s.strip()]
    return lines[:limit]


def build_batch_prompts(mode: str, prompt: str, count: int) -> list[str]:
    """Expand a base prompt/script into one prompt per image for the mode."""
    limit = MODE_MAX.get(mode, 1)
    if mode == "story":
        beats = _split_story_beats(prompt, limit)
        return [f"A single illustrated panel for this story moment: {b}" for b in beats]

    count = max(1, min(count, limit))
    if mode == "single" or count == 1:
        return [prompt]
    if mode == "variation":
        axes = _VARIATION_AXES
        return [f"{prompt}. Variation — {axes[i % len(axes)]}." for i in range(count)]
    if mode == "photoshoot":
        shots = _PHOTOSHOOT_SHOTS
        return [f"{prompt}. {_PHOTOSHOOT_LOCK}{shots[i % len(shots)]}." for i in range(count)]
    return [prompt for _ in range(count)]


# ── Script generator: idea → script ──────────────────────────────────────
# Turn a one-line idea into a structured, visual script. Each format is shaped
# to flow straight into the rest of the app: "story" emits one line per panel
# (drops into the Story image mode), the others read as shootable scene scripts.
SCRIPT_MODEL = "gpt-4o-mini"

SCRIPT_FORMATS = {
    "story": "an illustrated picture-book story. Output ONE short line per page — each line is a single vivid visual moment that could become one illustration. No page numbers, no headings, no commentary; just the lines, one per row.",
    "video": "a short video script. Break it into numbered scenes. For each scene give a one-line VISUAL: description, then a NARRATION: line for the voiceover. Keep it tight and shootable.",
    "manga": "a manga / comic script. Break it into numbered panels. For each panel give a short visual description, then any dialogue in quotes with the speaker's name.",
    "dialogue": "a dialogue scene. Format every line as SPEAKER: their line. Keep it natural and characterful, and let it move the story forward.",
}

SCRIPT_LENGTHS = {
    "short": "about 5 beats",
    "medium": "about 10 beats",
    "long": "about 16 beats",
}


def available_script_formats() -> list[str]:
    return list(SCRIPT_FORMATS)


def generate_script(idea: str, fmt: str = "story", length: str = "medium",
                    characters: list[str] | None = None) -> str:
    """Generate a script from a short idea via OpenAI chat. Returns plain text."""
    from openai import OpenAI

    style = SCRIPT_FORMATS.get(fmt, SCRIPT_FORMATS["story"])
    beats = SCRIPT_LENGTHS.get(length, SCRIPT_LENGTHS["medium"])
    cast = ""
    if characters:
        cast = f" Feature these characters by name: {', '.join(characters)}."
    system = (
        "You are a concise creative writer for a generative-media studio. Write "
        "vivid, concrete, visual scripts that are easy to turn into images and "
        "video. No preamble, no closing remarks — output only the script."
    )
    user = f"Idea: {idea}\n\nWrite {style}\nLength: {beats}.{cast}"
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=SCRIPT_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=1200,
        temperature=0.9,
    )
    return (resp.choices[0].message.content or "").strip()


# ── Video: image-to-video (character) & text-to-video ────────────────────
# GMI Cloud video models. Image-to-video animates a stored character portrait
# as the first frame, so the character's identity carries into the clip — the
# same "the vault holds the identity" idea as the images. Text-to-video needs
# no reference. Veo 3 additionally produces an audio track.
VIDEO_MODELS = {
    "Kling-Image2Video-V2.1-Master": {
        "label": "Kling 2.1 — image→video (keeps character)",
        "needs_image": True, "audio": False,
        "best_for": "Photoreal character animation",
        "description": "Animates a stored portrait with lifelike, expressive motion and strong identity retention. The best pick for bringing a photoreal character convincingly to life.",
    },
    "pixverse-v5.6-i2v": {
        "label": "Pixverse 5.6 — image→video (keeps character)",
        "needs_image": True, "audio": False,
        "best_for": "Fast, stylised character motion",
        "description": "Fast portrait animation with punchy, dynamic movement. Great for stylised or anime characters and quick iterations where speed matters more than photoreal polish.",
    },
    "Kling-Text2Video-V2.1-Master": {
        "label": "Kling 2.1 — text→video",
        "needs_image": False, "audio": False,
        "best_for": "Cinematic shots from a prompt",
        "description": "High-fidelity text-to-video with smooth camera work and strong prompt adherence. No character needed — describe the whole shot and it directs it.",
    },
    "pixverse-v5.6-t2v": {
        "label": "Pixverse 5.6 — text→video",
        "needs_image": False, "audio": False,
        "best_for": "Quick, creative social clips",
        "description": "Quick, creative text-to-video for stylised clips and social-ready shots, with shorter render times. Good for iterating on ideas.",
    },
    "Veo3-Fast": {
        "label": "Google Veo 3 Fast — text→video + audio",
        "needs_image": False, "audio": True,
        "best_for": "Video with built-in sound",
        "description": "Google Veo 3 — produces video with a synced audio track (ambient sound and speech) in a single pass. Best when you want sound baked in, not added later.",
    },
}
DEFAULT_VIDEO_MODEL = "Kling-Image2Video-V2.1-Master"

# Pixverse v5.6 diverges from the shared GMI video param shape the SDK
# builds for Kling/Veo/Wan. Reverse-engineered against GMI's live API
# (2026-07, see console.gmicloud.ai/api/v1/ie/requestqueue): `duration` is
# a string enum ("5"/"8"/"10", not an int) and the reference image is a
# top-level `image_url` field, not `image`. `quality` is required with no
# server-side default.
_PIXVERSE_VIDEO_MODELS = {"pixverse-v5.6-i2v", "pixverse-v5.6-t2v"}
_PIXVERSE_DURATIONS = (5, 8, 10)
_PIXVERSE_QUALITY = "720p"


def available_video_models() -> list[dict]:
    if not GMI_API_KEY:
        return []
    return [
        {
            "slug": slug, "label": m["label"], "needs_image": m["needs_image"],
            "audio": m["audio"], "best_for": m["best_for"], "description": m["description"],
        }
        for slug, m in VIDEO_MODELS.items()
    ]


# ── Lip-sync (Pipeline 2): audio-driven talking video ────────────────────
# GMI hosts kling-lip-sync (Audio-to-Video): feed a short face video + an audio
# track and it re-renders the mouth to match the speech — real lip-sync, not
# audio laid over motion. It's not in the Genblaze SDK's model registry, so we
# call GMI's request-queue REST API directly (same key, same account). Any
# failure falls back to the ffmpeg mux so the talking feature never breaks.
LIPSYNC_MODEL = "kling-lip-sync"
GMI_TTS_MODEL = "inworld-tts-2"
_GMI_QUEUE = "https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey/requests"


def _dig(obj, *keys):
    for k in keys:
        if isinstance(obj, dict) and obj.get(k) is not None:
            return obj[k]
    return None


IDENTIFY_FACE_MODEL = "kling-identify-face"


def _gmi_submit_poll(client, model: str, payload: dict, headers: dict, timeout: int = 600) -> dict:
    """Submit one GMI request-queue job and poll it to completion. Returns the
    final status dict. Raises with the response body on any error."""
    import time as _time

    resp = client.post(_GMI_QUEUE, json={"model": model, "payload": payload}, headers=headers)
    if resp.status_code >= 400:
        raise RuntimeError(f"{model} submit {resp.status_code}: {resp.text[:500]}")
    submitted = resp.json()
    rid = (_dig(submitted, "request_id", "id", "requestId")
           or _dig(_dig(submitted, "data") or {}, "request_id", "id"))
    if not rid:
        raise RuntimeError(f"{model} submit returned no request id: {str(submitted)[:400]}")
    deadline = _time.time() + timeout
    while _time.time() < deadline:
        _time.sleep(6)
        st = client.get(f"{_GMI_QUEUE}/{rid}", headers=headers).json()
        status = str(_dig(st, "status") or "").lower()
        if status in ("success", "succeeded", "completed", "done"):
            return st
        if status in ("failed", "error", "cancelled"):
            raise RuntimeError(f"{model} failed: {str(_dig(st, 'error') or st)[:400]}")
    raise TimeoutError(f"{model} timed out")


def _audio_ms(url: str) -> int:
    """Audio duration in ms via ffprobe (reads the URL directly)."""
    import subprocess
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", url],
            capture_output=True, text=True, timeout=40,
        ).stdout.strip()
        return max(2000, int(float(out) * 1000))
    except Exception:
        return 8000


def generate_lipsync(video_url: str, audio_url: str) -> dict:
    """Real audio-driven lip-sync via GMI's two-step Kling flow: identify the
    face in the motion clip, then re-render its mouth to the audio. Returns
    {url, sha256, mime_type} stored in B2. Raises on any failure so the caller
    can fall back to the plain mux."""
    import uuid as _uuid

    import httpx

    from app.storage import presign_asset_url, upload_bytes

    if not GMI_API_KEY:
        raise RuntimeError("GMI_API_KEY not configured")
    v = presign_asset_url(video_url) or video_url
    a = presign_asset_url(audio_url) or audio_url
    headers = {"Authorization": f"Bearer {GMI_API_KEY}", "Content-Type": "application/json"}

    with httpx.Client(timeout=60) as client:
        # Step 1 — detect the face(s) and open a session. Result lives at
        # outcome.data.{session_id, face_data[].face_id}.
        ident = _gmi_submit_poll(client, IDENTIFY_FACE_MODEL, {"video_url": v}, headers, timeout=300)
        idata = _dig(_dig(ident, "outcome") or ident, "data") or _dig(ident, "outcome") or ident
        session_id = _dig(idata, "session_id", "sessionId")
        faces = _dig(idata, "face_data", "face_ids", "faces", "face_id")
        if not session_id:
            raise RuntimeError(f"identify-face returned no session_id: {str(ident)[:600]}")
        face0 = faces[0] if isinstance(faces, list) and faces else "0"
        if isinstance(face0, dict):
            face0 = _dig(face0, "face_id", "id") or "0"

        # Step 2 — lip-sync the chosen face to the audio (audio at the start).
        payload = {
            "session_id": session_id,
            "face_choose": [{
                "face_id": str(face0),
                "sound_file": a,
                "sound_insert_time": 0,
                "sound_start_time": 0,
                "sound_end_time": _audio_ms(a),
                "sound_volume": 1,
                "original_audio_volume": 0,
            }],
        }
        st = _gmi_submit_poll(client, LIPSYNC_MODEL, payload, headers, timeout=600)
        sdata = _dig(_dig(st, "outcome") or st, "data") or _dig(st, "outcome") or st
        urls = _dig(sdata, "media_urls", "mediaUrls", "video_url", "videoUrl", "url", "outputs", "output", "works")
        if isinstance(urls, list) and urls and isinstance(urls[0], dict):
            urls = _dig(urls[0], "url", "resource", "video_url", "media_url")
        out_url = urls[0] if isinstance(urls, list) and urls else (urls if isinstance(urls, str) else None)
        if not out_url:
            raise RuntimeError(f"lip-sync finished without a media url: {str(st)[:600]}")

    data = httpx.get(out_url, timeout=180).content
    url, sha = upload_bytes(f"videos/lipsync/{_uuid.uuid4().hex}.mp4", data, "video/mp4")
    return {"url": url, "sha256": sha, "mime_type": "video/mp4"}


def _gmi_voice_line(character_id: int, text: str, voice_id: str) -> dict:
    """TTS via GMI's Inworld model, called through the raw request-queue REST
    API rather than the genblaze SDK's Pipeline abstraction — the SDK's audio
    ParamSurface allowlist doesn't include "text", so it gets silently
    dropped and the call fails server-side even though it's a valid field.
    Same bypass pattern as generate_lipsync()."""
    import uuid as _uuid

    import httpx

    from app.storage import upload_bytes

    if not GMI_API_KEY:
        raise RuntimeError("GMI_API_KEY not configured")
    headers = {"Authorization": f"Bearer {GMI_API_KEY}", "Content-Type": "application/json"}
    payload = {"text": text, "voice_id": voice_id, "audio_encoding": "MP3"}

    with httpx.Client(timeout=60) as client:
        result = _gmi_submit_poll(client, GMI_TTS_MODEL, payload, headers, timeout=120)
    data = _dig(_dig(result, "outcome") or result, "data") or _dig(result, "outcome") or result
    out_url = _dig(data, "audio_url", "url")
    if not out_url:
        raise RuntimeError(f"{GMI_TTS_MODEL} finished without an audio url: {str(result)[:600]}")

    audio = httpx.get(out_url, timeout=120).content
    url, sha = upload_bytes(f"audio/voice-lines/{_uuid.uuid4().hex}.mp3", audio, "audio/mpeg")
    return {
        "url": url,
        "sha256": sha,
        "mime_type": "audio/mpeg",
        "cost_usd": None,  # GMI Inworld TTS pricing not publicly listed
        "voice": f"gmi:{voice_id}",
        # No genblaze Pipeline ran (raw REST bypass), so there's no C2PA-style
        # manifest to verify — unlike _asset_result()'s result.manifest.verify().
        "manifest_verified": False,
    }


def mux_video_with_audio(video_url: str, audio_url: str) -> dict:
    """Combine a silent clip with the character's spoken line into one talking
    MP4 (ffmpeg), upload it to B2 and return {url, sha256, mime_type}. The video
    keeps its full length; the voice plays over the start."""
    import subprocess
    import uuid as _uuid

    from app.storage import download_bytes, upload_bytes

    video = download_bytes(video_url)
    audio = download_bytes(audio_url)
    with tempfile.TemporaryDirectory() as d:
        vp, ap, op = f"{d}/v.mp4", f"{d}/a.mp3", f"{d}/out.mp4"
        Path(vp).write_bytes(video)
        Path(ap).write_bytes(audio)
        subprocess.run(
            ["ffmpeg", "-y", "-i", vp, "-i", ap,
             "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
             "-map", "0:v:0", "-map", "1:a:0", op],
            check=True, capture_output=True, timeout=120,
        )
        out = Path(op).read_bytes()
    url, sha = upload_bytes(f"videos/talking/{_uuid.uuid4().hex}.mp4", out, "video/mp4")
    return {"url": url, "sha256": sha, "mime_type": "video/mp4"}


def extract_poster_frame(video_url: str) -> dict:
    """Grab the first frame of a clip as a PNG (ffmpeg), upload it to B2 and
    return {url, sha256, width, height}. The canvas editor uses it as the
    locked background for overlay editing, so the pixel size matters: the
    overlay PNG is exported at exactly these dimensions."""
    import io
    import subprocess
    import uuid as _uuid

    from PIL import Image

    from app.storage import download_bytes, upload_bytes

    video = download_bytes(video_url)
    with tempfile.TemporaryDirectory() as d:
        vp, fp = f"{d}/v.mp4", f"{d}/poster.png"
        Path(vp).write_bytes(video)
        subprocess.run(
            ["ffmpeg", "-y", "-i", vp, "-frames:v", "1", fp],
            check=True, capture_output=True, timeout=60,
        )
        out = Path(fp).read_bytes()
    with Image.open(io.BytesIO(out)) as img:
        width, height = img.size
    url, sha = upload_bytes(f"videos/posters/{_uuid.uuid4().hex}.png", out, "image/png")
    return {"url": url, "sha256": sha, "width": width, "height": height}


def overlay_video(video_url: str, overlay_png: bytes) -> dict:
    """Composite a transparent overlay PNG onto every frame of a clip
    (ffmpeg overlay filter), upload the result to B2 and return
    {url, sha256, mime_type}. The overlay is scaled to the video's size via
    scale2ref, so a slightly-off export resolution can't misalign it; audio
    is passed through untouched when the clip has any ('0:a?')."""
    import subprocess
    import uuid as _uuid

    from app.storage import download_bytes, upload_bytes

    video = download_bytes(video_url)
    with tempfile.TemporaryDirectory() as d:
        vp, op, out_p = f"{d}/v.mp4", f"{d}/overlay.png", f"{d}/out.mp4"
        Path(vp).write_bytes(video)
        Path(op).write_bytes(overlay_png)
        try:
            subprocess.run(
                # No explicit -c:v (container default, like the motion-comic
                # slideshow); format=yuv420p rides at the end of the filter
                # chain for player compatibility. -threads 2 and -preset
                # veryfast are load-bearing on the Railway container: x264
                # otherwise sizes itself for the HOST's 40 cores
                # (threads=40, rc_lookahead=40) and the allocation alone
                # blows the container memory limit — the kernel SIGKILLs
                # ffmpeg before frame 1 (seen live on prod, 2026-07-11).
                ["ffmpeg", "-y", "-i", vp, "-i", op,
                 "-filter_complex",
                 "[1:v][0:v]scale2ref[ovr][base];[base][ovr]overlay=0:0,format=yuv420p[vout]",
                 "-map", "[vout]", "-map", "0:a?", "-c:a", "copy",
                 "-threads", "2", "-preset", "veryfast",
                 out_p],
                check=True, capture_output=True, timeout=300,
            )
        except subprocess.CalledProcessError as e:
            # capture_output swallows stderr into the exception — surface it,
            # or prod failures are undiagnosable from the logs.
            logger.error("ffmpeg overlay failed: %s", (e.stderr or b"").decode(errors="replace")[-2000:])
            raise
        out = Path(out_p).read_bytes()
    url, sha = upload_bytes(f"videos/overlay/{_uuid.uuid4().hex}.mp4", out, "video/mp4")
    return {"url": url, "sha256": sha, "mime_type": "video/mp4"}


_video_provider_instance = None
_video_provider_lock = threading.Lock()


def _video_provider():
    """GMICloudVideoProvider with the Pixverse param contract corrected —
    built once and reused (registry construction isn't free)."""
    global _video_provider_instance
    if _video_provider_instance is not None:
        return _video_provider_instance
    with _video_provider_lock:
        if _video_provider_instance is None:
            from genblaze_core.providers import ModelSpec, ParamSurface, route_images
            from genblaze_gmicloud import GMICloudVideoProvider

            registry = GMICloudVideoProvider.models_default().fork()
            pixverse_surface = (
                ParamSurface.for_modality(Modality.VIDEO)
                .extend("quality")
                .with_coercers(duration=str)
            )
            for slug in _PIXVERSE_VIDEO_MODELS:
                registry.register(
                    ModelSpec(
                        model_id=slug,
                        modality=Modality.VIDEO,
                        input_mapping=route_images(slots=("image_url",)),
                        extras={"envelope_key": "payload"},
                        **pixverse_surface.build(),
                    )
                )
            _video_provider_instance = GMICloudVideoProvider(models=registry)
    return _video_provider_instance


def _video_step_params(model: str, duration: int, aspect_ratio: str) -> dict:
    """Per-model native params. Pixverse needs a duration snapped to its
    allowed options plus an explicit quality tier; every other GMI video
    model takes the duration as-is."""
    if model in _PIXVERSE_VIDEO_MODELS:
        snapped = min(_PIXVERSE_DURATIONS, key=lambda d: abs(d - duration))
        return {"duration": snapped, "aspect_ratio": aspect_ratio, "quality": _PIXVERSE_QUALITY}
    return {"duration": duration, "aspect_ratio": aspect_ratio}


def generate_video(
    prompt: str,
    model: str = DEFAULT_VIDEO_MODEL,
    reference: dict | None = None,
    duration: int = 5,
    aspect_ratio: str = "16:9",
) -> dict:
    """Generate a video clip. If the model is image-to-video, `reference`
    (a stored portrait) is used as the first frame to hold the character's
    identity. Runs on GMI Cloud with async polling handled by the pipeline."""
    meta = VIDEO_MODELS[model]
    step_kwargs: dict = _video_step_params(model, duration, aspect_ratio)
    if meta["needs_image"]:
        if not reference:
            raise ValueError("This video model needs a character portrait as reference.")
        inputs = _gmi_references([reference], limit=1)
        if not inputs:
            raise ValueError("Could not prepare the reference image.")
        step_kwargs["external_inputs"] = inputs

    result = (
        Pipeline("character-video")
        .step(
            _video_provider(),
            model=model,
            prompt=prompt,
            modality=Modality.VIDEO,
            **step_kwargs,
        )
        .run(sink=get_storage_sink(), timeout=600)
    )
    asset = _asset_result(result)
    asset["original_url"] = asset["url"]
    asset["model"] = model
    asset["cost_usd"] = None  # GMI video pricing is not exposed statically
    return asset


# ── Studio: character-less text-to-image ─────────────────────────────────
# Two modes. "background" makes an empty environment/scene plate (no people)
# you can later drop a character into; "photo-art" is a free artistic image
# generator à la Midjourney. Both reuse the portrait pipeline with no identity
# reference — the structured prompt builder does the heavy lifting client-side.
STUDIO_MODES = {
    "background": (
        "A background environment / scene plate with no people and no characters present. "
    ),
    "photo-art": "",
}


def generate_studio_image(
    prompt: str,
    kind: str = "photo-art",
    disclosure: str = "invisible",
    quality: str = "draft",
    model: str = DEFAULT_IMAGE_MODEL,
) -> dict:
    if kind not in STUDIO_MODES:
        raise ValueError(f"Unknown studio mode '{kind}'.")
    full_prompt = f"{STUDIO_MODES[kind]}{prompt}"
    asset = generate_character_portrait(
        character_id=0,
        prompt=full_prompt,
        disclosure=disclosure,
        references=None,
        quality=quality,
        model=model,
    )
    asset["kind"] = kind
    return asset


def generate_scene(
    prompt: str,
    references: list[dict],
    descriptors: list[str] | None = None,
    disclosure: str = "invisible",
) -> dict:
    """Compose one scene containing MULTIPLE characters, each kept consistent
    with their reference. Only Nano Banana (multi-image composition) is used —
    it's the model that actually holds several identities in one frame.

    `descriptors` (one appearance line per character, in reference order) gives
    the model a per-character text anchor, which markedly improves fidelity of
    the 2nd+ character vs. a bare "put them together" instruction."""
    from app.disclosure import apply_image_disclosure
    from genblaze_gmicloud import GMICloudImageProvider

    inputs = _gmi_references(references, limit=4)
    if len(inputs) < 2:
        raise ValueError("A scene needs at least two character references.")

    who = ""
    if descriptors:
        lines = "; ".join(f"reference {i + 1} = {d}" for i, d in enumerate(descriptors))
        who = f"The characters are: {lines}. "
    full_prompt = f"{SCENE_INSTRUCTION}{who}Scene: {prompt}"

    result = (
        Pipeline("multi-character-scene")
        .step(
            GMICloudImageProvider(),
            model="gemini-2.5-flash-image",
            prompt=full_prompt,
            modality=Modality.IMAGE,
            external_inputs=inputs,
        )
        .run(sink=get_storage_sink(), timeout=180)
    )
    asset = _asset_result(result)
    asset["original_url"] = asset["url"]
    asset["url"] = apply_image_disclosure(asset["url"], result.manifest, disclosure)
    asset["disclosure"] = disclosure
    asset["model"] = "gemini-2.5-flash-image"
    asset["quality"] = None
    asset["cost_usd"] = IMAGE_MODELS["gemini-2.5-flash-image"]["cost_usd"]
    return asset


# Each character can be assigned a voice from either provider, switchable
# anytime. OpenAI voices work everywhere (incl. Railway). GMI's Inworld TTS
# runs through the same account/key as our image and video models — no new
# external signup, and (unlike ElevenLabs' free tier) not IP-blocked from
# Railway's datacenter, so it's the richer default.
# The catalog (id/name/gender/age/style per voice) is generated alongside the
# sample clips by scripts/generate_voice_samples.py and committed. Loaded once.
def _load_voice_catalog() -> dict:
    import json

    path = Path(__file__).parent / "static" / "voice-samples" / "catalog.json"
    try:
        return json.loads(path.read_text())
    except Exception:
        return {"openai": [{"id": "onyx", "name": "Onyx", "gender": "male",
                            "age": "mature", "style": "deep"}], "gmi": []}


VOICE_CATALOG = _load_voice_catalog()
OPENAI_VOICES = VOICE_CATALOG.get("openai", [])

# Which voices GMI offers is a property of the provider, not of which samples
# we happen to have recorded. Deriving the roster from the sample catalog made
# those two inseparable and produced a deadlock: _apply_voice rejects any voice
# missing from the catalog, and a voice only enters the catalog once recorded —
# which required passing that very check. No new voice could ever be
# introduced. The roster therefore lives here; the catalog contributes only
# sample-derived metadata.
#
# inworld-tts-2 ships 65 voices across 16 languages, and a voice speaks the
# language it was built for — language is part of its identity, not a request
# parameter. Gender is filled in where the name is unambiguous and left as None
# where it is not; a wrong value is worse than an empty filter. Age and tone are
# undocumented for the non-English voices and carry a neutral placeholder.
GMI_VOICE_ROSTER = [
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
    ("Johanna", "female", "adult", "native German", "de"),
    ("Josef", "male", "adult", "native German", "de"),
    ("Alain", "male", "adult", "native French", "fr"),
    ("Hélène", "female", "adult", "native French", "fr"),
    ("Mathieu", "male", "adult", "native French", "fr"),
    ("Étienne", "male", "adult", "native French", "fr"),
    ("Diego", "male", "adult", "native Spanish", "es"),
    ("Lupita", "female", "adult", "native Spanish", "es"),
    ("Miguel", "male", "adult", "native Spanish", "es"),
    ("Rafael", "male", "adult", "native Spanish", "es"),
    ("Gianni", "male", "adult", "native Italian", "it"),
    ("Orietta", "female", "adult", "native Italian", "it"),
    ("Heitor", "male", "adult", "native Brazilian Portuguese", "pt"),
    ("Maitê", "female", "adult", "native Brazilian Portuguese", "pt"),
    ("Erik", "male", "adult", "native Dutch", "nl"),
    ("Katrien", "female", "adult", "native Dutch", "nl"),
    ("Lennart", "male", "adult", "native Dutch", "nl"),
    ("Lore", "female", "adult", "native Dutch", "nl"),
    ("Szymon", "male", "adult", "native Polish", "pl"),
    ("Wojciech", "male", "adult", "native Polish", "pl"),
    ("Svetlana", "female", "adult", "native Russian", "ru"),
    ("Elena", "female", "adult", "native Russian", "ru"),
    ("Dmitry", "male", "adult", "native Russian", "ru"),
    ("Nikolai", "male", "adult", "native Russian", "ru"),
    ("Yichen", None, "adult", "native Mandarin", "zh"),
    ("Xiaoyin", "female", "adult", "native Mandarin", "zh"),
    ("Xinyi", "female", "adult", "native Mandarin", "zh"),
    ("Jing", "female", "adult", "native Mandarin", "zh"),
    ("Asuka", "female", "adult", "native Japanese", "ja"),
    ("Satoshi", "male", "adult", "native Japanese", "ja"),
    ("Hyunwoo", "male", "adult", "native Korean", "ko"),
    ("Minji", "female", "adult", "native Korean", "ko"),
    ("Seojun", "male", "adult", "native Korean", "ko"),
    ("Yoona", "female", "adult", "native Korean", "ko"),
    ("Riya", "female", "adult", "native Hindi", "hi"),
    ("Manoj", "male", "adult", "native Hindi", "hi"),
    ("Yael", "female", "adult", "native Hebrew", "he"),
    ("Oren", "male", "adult", "native Hebrew", "he"),
    ("Nour", None, "adult", "native Arabic", "ar"),
    ("Omar", "male", "adult", "native Arabic", "ar"),
]


def _gmi_voice_list() -> list[dict]:
    """The roster, enriched with catalog metadata wherever a sample exists.

    `has_sample` tells the UI whether a preview clip can be played. A voice is
    fully usable without one — it just cannot be auditioned yet."""
    recorded = {v["id"]: v for v in VOICE_CATALOG.get("gmi", [])}
    out = []
    for vid, gender, age, style, language in GMI_VOICE_ROSTER:
        entry = dict(recorded.get(vid) or {
            "id": vid, "name": vid, "provider": "gmi",
            "gender": gender, "age": age, "style": style,
        })
        entry.setdefault("language", language)
        entry["has_sample"] = vid in recorded
        out.append(entry)
    return out


GMI_VOICES = _gmi_voice_list()
_OPENAI_VOICE_IDS = {v["id"] for v in OPENAI_VOICES}


def available_voices() -> dict:
    voices = {"openai": OPENAI_VOICES}
    if GMI_API_KEY:
        voices["gmi"] = GMI_VOICES
    return voices


def _default_openai_voice(character_id: int) -> str:
    return OPENAI_VOICES[character_id % len(OPENAI_VOICES)]["id"]


# Neither provider ships a genuinely childlike voice on a free plan — OpenAI's
# catalog has none, and ElevenLabs' child-style voices live in the paid
# shared library (confirmed: "payment_required" on this account). As a
# stand-in, these pitch an existing OpenAI voice up a few semitones after
# generation — same line, higher register. Catalog entries with these ids
# carry age="child".
_CHILD_VOICE_BASE = {
    "shimmer-child": ("shimmer", 5),
    "ballad-child": ("ballad", 4),
}


def _pitch_shift(data: bytes, semitones: float) -> bytes:
    """Raise pitch by `semitones` while keeping duration roughly constant
    (asetrate for the pitch shift, atempo to undo the resulting speed-up).
    Must resample at the source's actual rate, not a guessed constant —
    OpenAI TTS outputs 24kHz, and using the wrong base rate compounds with
    the pitch ratio and badly distorts duration."""
    import subprocess

    ratio = 2 ** (semitones / 12)
    with tempfile.TemporaryDirectory() as d:
        ip, op = f"{d}/in.mp3", f"{d}/out.mp3"
        Path(ip).write_bytes(data)
        sr = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=sample_rate", "-of", "default=nw=1:nk=1", ip],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip()
        sr = int(sr) if sr.isdigit() else 24000
        subprocess.run(
            ["ffmpeg", "-y", "-i", ip, "-filter:a",
             f"asetrate={sr}*{ratio},aresample={sr},atempo={1 / ratio}", op],
            check=True, capture_output=True, timeout=60,
        )
        return Path(op).read_bytes()


def _openai_voice_line_pitched(character_id: int, text: str, label: str) -> dict:
    import uuid as _uuid

    from app.storage import download_bytes, upload_bytes

    base_voice, semitones = _CHILD_VOICE_BASE[label]
    base = _openai_voice_line(character_id, text, base_voice)
    shifted = _pitch_shift(download_bytes(base["url"]), semitones)
    url, sha = upload_bytes(f"audio/voice-lines/{_uuid.uuid4().hex}.mp3", shifted, "audio/mpeg")
    return {**base, "url": url, "sha256": sha, "voice": f"openai:{label}"}


def _openai_voice_line(character_id: int, text: str, voice: str) -> dict:
    result = (
        Pipeline(f"character-{character_id}-voice-line-openai")
        .step(
            OpenAITTSProvider(),
            model="gpt-4o-mini-tts",
            prompt=text,
            modality=Modality.AUDIO,
            voice=voice,
        )
        .run(sink=get_storage_sink(), timeout=120)
    )
    asset = _asset_result(result)
    asset["cost_usd"] = round(len(text) * OPENAI_TTS_USD_PER_CHAR, 6)
    asset["voice"] = f"openai:{voice}"
    return asset


def generate_audio(
    text: str,
    voice_provider: str | None = None,
    voice_id: str | None = None,
) -> dict:
    """Standalone TTS for the Audio pipeline — narration/voiceover not tied to a
    character. voice_id must be one of the catalog's fixed GMI or OpenAI
    voices. Reuses the same generation path (incl. GMI→OpenAI fallback)."""
    return generate_character_voice_line(0, text, voice_provider, voice_id)


def generate_character_voice_line(
    character_id: int,
    text: str,
    voice_provider: str | None = None,
    voice_id: str | None = None,
) -> dict:
    if voice_provider == "gmi" and voice_id and GMI_API_KEY:
        try:
            return _gmi_voice_line(character_id, text, voice_id)
        except Exception as exc:
            logger.warning(
                "GMI voice %s unavailable, falling back to OpenAI: %s",
                voice_id, exc,
            )

    if voice_provider == "openai" and voice_id in _CHILD_VOICE_BASE:
        return _openai_voice_line_pitched(character_id, text, voice_id)

    if voice_provider == "openai" and voice_id in _OPENAI_VOICE_IDS:
        voice = voice_id
    else:
        voice = _default_openai_voice(character_id)
    return _openai_voice_line(character_id, text, voice)


def generate_dialogue_audio(turns: list[dict]) -> dict:
    """Turn a multi-character script into one combined clip: each turn speaks
    in its own character's fixed voice (reusing generate_character_voice_line
    as-is — no new voice logic), the resulting lines are concatenated in
    order with ffmpeg, and the combined clip is uploaded once.

    `turns`: [{"character_id", "character_name", "voice_provider",
    "voice_id", "text"}, ...] — one entry per line, in speaking order.
    Returns {url, sha256, mime_type, manifest_verified, cost_usd, script}
    where `script` echoes each turn's character_name/text for display."""
    import subprocess
    import uuid as _uuid

    from app.storage import download_bytes, upload_bytes

    lines = []
    for turn in turns:
        asset = generate_character_voice_line(
            turn["character_id"], turn["text"], turn.get("voice_provider"), turn.get("voice_id"),
        )
        lines.append({**turn, "asset": asset})

    with tempfile.TemporaryDirectory() as d:
        clip_paths = []
        for i, line in enumerate(lines):
            path = Path(d) / f"line{i}.mp3"
            path.write_bytes(download_bytes(line["asset"]["url"]))
            clip_paths.append(path)

        inputs = []
        for p in clip_paths:
            inputs += ["-i", str(p)]
        filter_inputs = "".join(f"[{i}:a]" for i in range(len(clip_paths)))
        op = Path(d) / "dialogue.mp3"
        subprocess.run(
            ["ffmpeg", "-y", *inputs, "-filter_complex",
             f"{filter_inputs}concat=n={len(clip_paths)}:v=0:a=1[out]", "-map", "[out]", str(op)],
            check=True, capture_output=True, timeout=120,
        )
        out = op.read_bytes()

    url, sha = upload_bytes(f"audio/dialogues/{_uuid.uuid4().hex}.mp3", out, "audio/mpeg")
    costs = [line["asset"].get("cost_usd") for line in lines if line["asset"].get("cost_usd") is not None]
    return {
        "url": url,
        "sha256": sha,
        "mime_type": "audio/mpeg",
        "manifest_verified": all(line["asset"].get("manifest_verified") for line in lines),
        "cost_usd": sum(costs) if costs else None,
        "script": [
            {"character_id": l["character_id"], "character_name": l["character_name"], "text": l["text"]}
            for l in lines
        ],
    }


def _probe_duration_s(path: Path) -> float:
    import subprocess

    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, timeout=20,
    ).stdout.strip()
    return max(0.5, float(out)) if out else 3.0


_CAPTION_FONT = Path(__file__).parent / "static" / "fonts" / "NotoSans.ttf"


def _draw_caption(image_bytes: bytes, text: str) -> bytes:
    """Burn a bottom-bar caption into a still image with PIL, not ffmpeg's
    drawtext — the locally-tested ffmpeg build doesn't have libfreetype
    compiled in, and Railway's apt-get ffmpeg isn't guaranteed to either, so
    this sidesteps that entirely and gets the same result more portably."""
    from io import BytesIO

    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    font_size = max(20, w // 22)
    font = ImageFont.truetype(str(_CAPTION_FONT), font_size)
    try:
        font.set_variation_by_name("Bold")
    except Exception:
        pass  # non-variable font fallback — still renders, just not bold

    max_width = int(w * 0.86)
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    line_height = int(font_size * 1.3)
    bar_height = line_height * len(lines) + 40
    draw.rectangle([0, h - bar_height, w, h], fill=(0, 0, 0, 165))
    y = h - bar_height + 20
    for line in lines:
        tw = draw.textlength(line, font=font)
        draw.text(((w - tw) / 2, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_height

    out = BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


@lru_cache(maxsize=1)
def _ffmpeg_filters() -> frozenset:
    """Names of the filters this machine's ffmpeg actually has."""
    import subprocess

    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-filters"],
            capture_output=True, text=True, timeout=20,
        ).stdout
    except Exception:
        return frozenset()
    names = set()
    for line in out.splitlines():
        parts = line.split()
        # Rows look like " T.. name  in->out  description"; the flags column
        # comes first, so the filter's name is the second field.
        if len(parts) >= 2 and not line.startswith(" ---"):
            names.add(parts[1])
    return frozenset(names)


def ffmpeg_has_filter(name: str) -> bool:
    return name in _ffmpeg_filters()


def ffmpeg_has_drawtext() -> bool:
    """Whether this machine's ffmpeg was built with libfreetype.

    Nothing here depends on the answer — every piece of text this app burns
    into video goes through Pillow (`_draw_caption`, `_render_title_card`),
    which wraps lines and picks fonts far better than drawtext can and needs no
    ffmpeg feature at all. The probe exists so a deployed image can be asked
    what it actually has (it is reported by /capabilities): the ffmpeg used
    during development has NO drawtext filter, and a `-vf drawtext=…` that
    silently works on one host and dies on another is exactly the surprise this
    app should not ship. Any future change tempted to reach for drawtext has to
    pass this check first.
    """
    return ffmpeg_has_filter("drawtext")


# ── Timeline: cut existing vault assets into one sequence ────────────────
# The last step of the chain. Everything else in this file CREATES material;
# this assembles material that already exists into a finished cut, so no
# provider is called and nothing is billed — local ffmpeg work, like the canvas
# overlay.
#
# A cut is built out of PIECES, not whole clips. Each piece is a short, fully
# self-contained MP4 — a clip's body, or the half-second where two clips meet —
# and the finished film is those pieces joined with the concat demuxer.
#
# That shape buys two things a naive "one segment per clip" design cannot:
#
# 1. Real cross-dissolves. The obvious way to dissolve is one big
#    filter_complex chaining xfade across every clip, but it holds every input
#    open at once, and this app already learned on the small production
#    container that a filtergraph sized for the host gets SIGKILLed before
#    frame 1 (see overlay_video). Here a dissolve is a single xfade over two
#    HALF-SECOND inputs — the tail of one clip and the head of the next — so
#    peak memory is a fraction of one clip no matter how long the film is.
#
# 2. A cache that actually helps. A piece depends only on its own inputs, so
#    nudging clip 5's length re-encodes clip 5 and the two joins touching it,
#    and reuses everything else verbatim.

SEQUENCE_RESOLUTIONS = {
    # (long edge, short edge). 720p is the default because the production VM in
    # DEPLOY.md is small; 1080p is offered for a final deliverable and is
    # roughly twice the encode time.
    "720p": (1280, 720),
    "1080p": (1920, 1080),
}
SEQUENCE_ASPECTS = ("16:9", "9:16", "1:1")
DEFAULT_SEQUENCE_RESOLUTION = "720p"

# Kept as a name for the three canvases at the default resolution — the editor
# and /capabilities both talk about aspect ratios, not pixel pairs.
SEQUENCE_SIZES = {
    aspect: None for aspect in SEQUENCE_ASPECTS
}


def sequence_size(aspect_ratio: str, resolution: str = DEFAULT_SEQUENCE_RESOLUTION) -> tuple:
    """Output frame for an aspect ratio at a resolution tier.

    A square canvas uses the SHORT edge for both sides: taking the long edge
    would make 1:1 the largest, slowest format of the three, which is the
    opposite of what picking "square" implies.
    """
    long_edge, short_edge = SEQUENCE_RESOLUTIONS.get(
        resolution, SEQUENCE_RESOLUTIONS[DEFAULT_SEQUENCE_RESOLUTION])
    if aspect_ratio == "9:16":
        return short_edge, long_edge
    if aspect_ratio == "1:1":
        return short_edge, short_edge
    return long_edge, short_edge


SEQUENCE_FPS = 24
SEQUENCE_MAX_FADE = 2.0
# A transition may never eat more than this share of either clip it touches. A
# clip with a transition on both sides therefore always keeps at least 30% of
# itself as untouched body, and a 0.5s fade can't outlive a 0.4s title card.
SEQUENCE_FADE_SHARE = 0.35
# Below this, a body piece is shorter than a few frames and not worth cutting
# in; the transition is shortened until the body clears it.
SEQUENCE_MIN_BODY = 0.12

# "cut" is no transition at all. "fade" dips through black — the outgoing clip
# darkens, the incoming one lifts, and the film's total length is unchanged.
# "dissolve" blends the two directly, so it OVERLAPS: a 0.5s dissolve makes the
# finished cut half a second shorter than the sum of its clips.
SEQUENCE_TRANSITIONS = ("cut", "fade", "dissolve")

# Text panels come as finished designs rather than a pile of knobs — position,
# alignment, weight and rule are chosen together per style, which is what keeps
# them from looking assembled by accident.
SEQUENCE_TITLE_STYLES = ("center", "lower_third", "left", "end_card")

# Colour looks. Deliberately built from ffmpeg's own primitives rather than
# shipped LUT files: no binary assets to license or version, and every look
# stays readable as what it does. `eq` handles exposure/saturation,
# `colorbalance` shifts the shadows/midtones/highlights per channel — the same
# controls a grading panel exposes, just spelled out.
SEQUENCE_LOOKS = {
    "none": "",
    "enhance": "eq=contrast=1.10:saturation=1.08:gamma=1.02,unsharp=5:5:0.6:5:5:0.0",
    "warm": "eq=contrast=1.06:saturation=1.10,colorbalance=rs=0.06:gs=0.01:bs=-0.06:rm=0.05:bm=-0.05",
    "cool": "eq=contrast=1.06:saturation=1.02,colorbalance=rs=-0.06:bs=0.08:rm=-0.04:bm=0.06",
    "noir": "hue=s=0,eq=contrast=1.28:brightness=-0.02,unsharp=5:5:0.4:5:5:0.0",
    "vivid": "eq=contrast=1.14:saturation=1.35:gamma=1.04",
    "vintage": "curves=preset=vintage,eq=saturation=0.88:contrast=0.96",
    "soft": "eq=contrast=0.94:brightness=0.03:saturation=0.96,gblur=sigma=0.6",
}

# Camera moves for stills. A still held dead-still for four seconds is what
# makes a slideshow read as a slideshow; a slow push or drift is the single
# cheapest thing that makes the same material read as film.
SEQUENCE_MOTIONS = ("none", "zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down")


_TITLE_INK = (255, 255, 255)
_TITLE_ACCENT = (168, 255, 53)   # the app's lime, as in the badge and the UI
_TITLE_BG = (11, 10, 22)


def _render_title_card(text: str, subtitle: str | None, width: int, height: int,
                       style: str = "center") -> bytes:
    """A text panel as a PNG, drawn with Pillow — see ffmpeg_has_drawtext() for
    why this never goes through ffmpeg's drawtext filter.

    The four styles are finished designs, not parameters: each fixes size,
    position, alignment and rule together. Exposing those individually is how
    title cards end up looking assembled rather than designed.
    """
    from io import BytesIO

    from PIL import Image, ImageDraw, ImageFont

    if style not in SEQUENCE_TITLE_STYLES:
        style = "center"

    img = Image.new("RGB", (width, height), _TITLE_BG)
    draw = ImageDraw.Draw(img)
    unit = min(width, height)

    def _font(size: int, bold: bool):
        font = ImageFont.truetype(str(_CAPTION_FONT), max(12, size))
        if bold:
            try:
                font.set_variation_by_name("Bold")
            except Exception:
                pass  # non-variable font fallback — still renders, just not bold
        return font

    def _wrap(content: str, font, max_width: int) -> list[str]:
        lines, current = [], ""
        for word in (content or "").split():
            trial = f"{current} {word}".strip()
            if draw.textlength(trial, font=font) <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    # style -> (title size, subtitle size, text box width, horizontal anchor,
    #           vertical placement, accent rule, subtitle above the title)
    spec = {
        "center":      (unit // 9,  unit // 26, 0.82, "center", "middle", False, False),
        "lower_third": (unit // 13, unit // 30, 0.62, "left",   "lower",  True,  False),
        "left":        (unit // 8,  unit // 26, 0.70, "left",   "middle", True,  False),
        "end_card":    (unit // 12, unit // 30, 0.70, "center", "middle", True,  True),
    }[style]
    title_size, sub_size, box_share, anchor, placement, rule, sub_first = spec

    box_width = int(width * box_share)
    margin = int(width * (0.09 if anchor == "center" else 0.08))

    title_font = _font(title_size, bold=True)
    title_lines = _wrap(text, title_font, box_width)
    title_step = int(title_font.size * 1.22)

    sub_font, sub_lines, sub_step = None, [], 0
    if subtitle:
        sub_font = _font(sub_size, bold=False)
        sub_lines = _wrap(subtitle, sub_font, box_width)
        sub_step = int(sub_font.size * 1.35)

    gap = int(unit * 0.035) if sub_lines else 0
    rule_gap = int(unit * 0.03) if rule else 0
    rule_height = max(2, unit // 220) if rule else 0
    block = (title_step * len(title_lines) + gap + sub_step * len(sub_lines)
             + (rule_height + rule_gap if rule else 0))

    if placement == "lower":
        y = height - int(height * 0.14) - block
    else:
        y = (height - block) / 2

    def _draw_line(line, font, fill):
        text_width = draw.textlength(line, font=font)
        x = (width - text_width) / 2 if anchor == "center" else margin
        draw.text((x, y), line, font=font, fill=fill)

    def _draw_rule():
        nonlocal y
        rule_width = int(box_width * 0.28)
        x = (width - rule_width) / 2 if anchor == "center" else margin
        draw.rectangle([x, y, x + rule_width, y + rule_height], fill=_TITLE_ACCENT)
        y += rule_height + rule_gap

    if rule and not sub_first:
        _draw_rule()
    if sub_first and sub_lines:
        for line in sub_lines:
            _draw_line(line, sub_font, _TITLE_ACCENT)
            y += sub_step
        y += gap
        if rule:
            _draw_rule()
    for line in title_lines:
        _draw_line(line, title_font, _TITLE_INK)
        y += title_step
    if sub_lines and not sub_first:
        y += gap
        for line in sub_lines:
            _draw_line(line, sub_font, _TITLE_ACCENT)
            y += sub_step

    out = BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _still_png(image_bytes: bytes, caption: str | None) -> bytes:
    """Normalise any stored still to a plain RGB PNG, with an optional caption
    burned in. Going through Pillow unconditionally also rescues inputs ffmpeg
    would misread — CMYK JPEGs, palette PNGs, uploads whose extension lies."""
    from io import BytesIO

    from PIL import Image

    if caption:
        return _draw_caption(image_bytes, caption)
    with Image.open(BytesIO(image_bytes)) as img:
        out = BytesIO()
        img.convert("RGB").save(out, format="PNG")
        return out.getvalue()


def _has_audio_stream(path: Path) -> bool:
    import subprocess

    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
             "stream=index", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
    except Exception:
        return False
    return bool(out)


def _grade_chain(clip: dict) -> str:
    """Colour work for one clip: a named look, plus manual trims on top.

    The manual values are offsets around neutral (0 = unchanged) so a slider at
    rest costs nothing, and they compose with the look rather than replacing
    it — nudging exposure on a graded clip is the normal case, not an
    either/or."""
    parts = []
    look = SEQUENCE_LOOKS.get(clip.get("look") or "none", "")
    if look:
        parts.append(look)
    brightness = float(clip.get("brightness") or 0.0)
    contrast = float(clip.get("contrast") or 0.0)
    saturation = float(clip.get("saturation") or 0.0)
    if brightness or contrast or saturation:
        parts.append(
            f"eq=brightness={max(-0.5, min(0.5, brightness)):.3f}"
            f":contrast={max(0.2, min(2.5, 1.0 + contrast)):.3f}"
            f":saturation={max(0.0, min(3.0, 1.0 + saturation)):.3f}"
        )
    return ",".join(parts)


def _fade_filters(fade_in: float, fade_out: float, length: float) -> tuple[str, str]:
    """Video and audio fade fragments for one segment (either may be empty).
    Returned separately because stills get silence rather than a filter chain."""
    video, audio = [], []
    if fade_in > 0:
        video.append(f"fade=t=in:st=0:d={fade_in:.3f}")
        audio.append(f"afade=t=in:st=0:d={fade_in:.3f}")
    if fade_out > 0:
        start = max(0.0, length - fade_out)
        video.append(f"fade=t=out:st={start:.3f}:d={fade_out:.3f}")
        audio.append(f"afade=t=out:st={start:.3f}:d={fade_out:.3f}")
    return ",".join(video), ",".join(audio)


def _fit_chain(width: int, height: int) -> str:
    """Fit any source into the output frame without cropping or distorting it —
    letterboxed/pillarboxed instead, so a 9:16 portrait dropped into a 16:9 cut
    keeps its whole frame."""
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1"
    )


def _kenburns_chain(motion: str, width: int, height: int, piece_frames: int,
                    clip_frames: int, frame_offset: int) -> str:
    """A slow camera move over a still, via zoompan.

    zoompan expands ONE input frame into `piece_frames` output frames, so the
    caller must feed a single image (not `-loop 1`) — looping would multiply the
    move once per looped frame and produce a stutter. The source is first scaled
    to twice the output: zoompan steps its crop window in integer pixels, and on
    a frame-sized input those steps read as judder.

    Every expression is ABSOLUTE in the clip's own frame index rather than
    accumulating from the previous frame (`zoom+step`). That is what lets a
    still be cut into pieces at all: a piece starting 2 seconds into the clip
    renders with `frame_offset` set and lands exactly where the accumulating
    version would have been, so the move continues across a join instead of
    snapping back to the start.
    """
    over = (f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=decrease,"
            f"pad={width * 2}:{height * 2}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1")
    span = max(1, clip_frames - 1)
    # Progress through the WHOLE clip, evaluated at this piece's frames.
    at = f"min(1,(on+{frame_offset})/{span})"
    centre_x, centre_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    peak = 1.12

    if motion == "zoom_in":
        z, x, y = f"1+{peak - 1:.4f}*{at}", centre_x, centre_y
    elif motion == "zoom_out":
        z, x, y = f"{peak}-{peak - 1:.4f}*{at}", centre_x, centre_y
    elif motion in ("pan_left", "pan_right"):
        progress = at if motion == "pan_right" else f"(1-{at})"
        z, x, y = str(peak), f"(iw-iw/zoom)*{progress}", centre_y
    else:  # pan_up / pan_down
        progress = at if motion == "pan_down" else f"(1-{at})"
        z, x, y = str(peak), centre_x, f"(ih-ih/zoom)*{progress}"

    return (f"{over},zoompan=z='{z}':x='{x}':y='{y}'"
            f":d={piece_frames}:s={width}x{height}:fps={SEQUENCE_FPS}")


_X264 = ["-c:v", "libx264", "-preset", "veryfast", "-threads", "2",
         "-r", str(SEQUENCE_FPS), "-pix_fmt", "yuv420p"]
# Every segment gets an audio track — silent for stills — because the concat
# demuxer needs the same stream layout in every part, and a cut mixing talking
# clips with stills would otherwise lose its audio at the first still.
_AAC = ["-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"]
_SILENCE = "anullsrc=channel_layout=stereo:sample_rate=48000"


def _run_ffmpeg(args: list[str], what: str, timeout: int = 600) -> None:
    import subprocess

    try:
        subprocess.run(args, check=True, capture_output=True, timeout=timeout)
    except subprocess.CalledProcessError as exc:
        # capture_output swallows stderr into the exception — surface it, or a
        # production failure is undiagnosable from the logs (same reasoning as
        # overlay_video).
        logger.error("ffmpeg %s failed: %s", what,
                     (exc.stderr or b"").decode(errors="replace")[-2000:])
        raise


def _join_chain(*parts: str) -> str:
    return ",".join(p for p in parts if p)


# ── The piece cache ──────────────────────────────────────────────────────
# Bump whenever an encoder flag or a filter chain changes, or a stale piece
# encoded by the previous version will be served as a cache hit and the film
# will quietly mix two generations of settings.
_PIECE_CACHE_VERSION = 1


def _cache_dir() -> Path:
    path = Path(SEQUENCE_CACHE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_key(payload: dict) -> str:
    blob = json.dumps({**payload, "v": _PIECE_CACHE_VERSION},
                      sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:40]


def _cached(prefix: str, key: str, suffix: str, build) -> Path:
    """Return a cached artefact, building it on a miss.

    The suffix stays at the END of both the final and the temporary name:
    ffmpeg picks its output muxer from the file extension, and a name like
    `piece.mp4-<hash>` leaves it with nothing to go on ("Unable to choose an
    output format").

    The build writes to that temporary name and is only then moved into place,
    so a render killed mid-encode — which the production container does under
    memory pressure — can never leave a truncated file that later reads as a
    valid hit.
    """
    path = _cache_dir() / f"{prefix}-{key}{suffix}"
    if path.exists() and path.stat().st_size > 0:
        os.utime(path, None)  # touch: the cache evicts by last use, not by age
        return path
    partial = path.with_name(f"{prefix}-{key}.partial{suffix}")
    try:
        build(partial)
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
    return path


def prune_piece_cache(max_bytes: int | None = None) -> int:
    """Drop least-recently-used pieces until the cache fits. Returns bytes freed."""
    limit = max_bytes if max_bytes is not None else SEQUENCE_CACHE_MAX_MB * 1024 * 1024
    try:
        files = [p for p in _cache_dir().iterdir() if p.is_file() and not p.name.endswith(".partial")]
    except OSError:
        return 0
    stats = []
    for path in files:
        try:
            stats.append((path.stat().st_mtime, path.stat().st_size, path))
        except OSError:
            continue
    total = sum(size for _, size, _ in stats)
    freed = 0
    for _, size, path in sorted(stats):
        if total - freed <= limit:
            break
        try:
            path.unlink()
            freed += size
        except OSError:
            continue
    return freed


def _cached_source(url: str, sha256: str | None, suffix: str) -> Path:
    """The bytes behind a clip, downloaded once and kept.

    Re-downloading a 10 MB clip from B2 on every render is the slowest part of
    iterating, and unlike an encode it buys nothing new — the object is
    immutable under its URL.
    """
    from app.storage import download_bytes

    key = _cache_key({"url": url, "sha": sha256})
    return _cached("src", key, suffix, lambda out: out.write_bytes(download_bytes(url)))


# ── Encoding one piece ───────────────────────────────────────────────────
# A piece is a slice [offset, offset+length) of one clip, rendered complete:
# scaled, graded, moved, with its own audio, and optionally faded at one end.
# Pieces never depend on their neighbours' content, only on the transition
# lengths, which is what makes them cacheable.

def _audio_inputs_for(clip: dict, source: Path | None, has_audio: bool,
                      offset: float, length: float, voice: Path | None) -> tuple:
    """Input arguments and a filter graph producing a single [aout] label.

    Every piece carries an audio track — silence for a bare still — because the
    concat demuxer needs the same stream layout in every part, and a cut mixing
    talking clips with stills would otherwise lose its audio at the first still.
    """
    args, labels, graph = [], [], []
    next_index = 1 if source is not None else 0

    volume = max(0.0, min(4.0, float(clip.get("volume") if clip.get("volume") is not None else 1.0)))
    if has_audio:
        graph.append(f"[0:a]volume={volume:.3f}[clipa]")
        labels.append("[clipa]")

    if voice is not None:
        voice_volume = max(0.0, min(4.0, float(clip.get("voice_volume") or 1.0)))
        args += ["-ss", f"{offset:.3f}", "-i", str(voice)]
        # apad, then the output -t, so a voice shorter than the clip leaves
        # silence rather than truncating the picture with -shortest.
        graph.append(f"[{next_index}:a]volume={voice_volume:.3f},apad[voicea]")
        labels.append("[voicea]")
        next_index += 1

    if not labels:
        args += ["-f", "lavfi", "-t", f"{length:.3f}", "-i", _SILENCE]
        return args, f"[{next_index}:a]anull[aout]"
    if len(labels) == 1:
        return args, ";".join(graph + [f"{labels[0]}anull[aout]"])
    joined = "".join(labels)
    return args, ";".join(
        graph + [f"{joined}amix=inputs={len(labels)}:duration=longest:normalize=0[aout]"])


def _encode_piece(clip: dict, out_path: Path, *, source: Path | None, offset: float,
                  length: float, width: int, height: int, fade_in: float, fade_out: float,
                  clip_length: float, voice: Path | None) -> None:
    is_still = clip["source"] == "title" or clip.get("_still", False)
    motion = (clip.get("motion") or "none") if is_still else "none"
    video_fade, audio_fade = _fade_filters(fade_in, fade_out, length)
    piece_frames = max(2, int(round(length * SEQUENCE_FPS)))

    args = ["ffmpeg", "-y"]
    if is_still:
        if motion != "none":
            args += ["-i", str(source)]  # a single frame — zoompan expands it
            geometry = _kenburns_chain(
                motion, width, height, piece_frames,
                clip_frames=max(2, int(round(clip_length * SEQUENCE_FPS))),
                frame_offset=int(round(offset * SEQUENCE_FPS)),
            )
        else:
            args += ["-loop", "1", "-t", f"{length:.3f}", "-i", str(source)]
            geometry = f"{_fit_chain(width, height)},fps={SEQUENCE_FPS}"
        has_audio = False
    else:
        if offset > 0:
            args += ["-ss", f"{offset:.3f}"]
        args += ["-i", str(source)]
        geometry = f"{_fit_chain(width, height)},fps={SEQUENCE_FPS}"
        has_audio = _has_audio_stream(source)

    audio_args, audio_graph = _audio_inputs_for(clip, source, has_audio, offset, length, voice)
    args += audio_args

    video_chain = _join_chain(geometry, _grade_chain(clip), video_fade, "format=yuv420p")
    if audio_fade:
        audio_graph = audio_graph.replace("[aout]", "[apre]") + f";[apre]{audio_fade}[aout]"

    args += ["-filter_complex", f"[0:v]{video_chain}[vout];{audio_graph}",
             "-map", "[vout]", "-map", "[aout]",
             *_X264, *_AAC, "-t", f"{length:.3f}", str(out_path)]
    _run_ffmpeg(args, "piece", timeout=600)


def _encode_dissolve(tail: Path, head: Path, out_path: Path, length: float) -> None:
    """The half-second where two clips overlap.

    xfade sees exactly two inputs, each `length` long, so this is the smallest
    possible form of a cross-dissolve — the reason a blended transition is
    affordable here at all. acrossfade does the same for the sound; both
    produce exactly `length` seconds out of 2×`length` seconds in.
    """
    _run_ffmpeg(
        ["ffmpeg", "-y", "-i", str(tail), "-i", str(head),
         "-filter_complex",
         f"[0:v][1:v]xfade=transition=fade:duration={length:.3f}:offset=0[vout];"
         f"[0:a][1:a]acrossfade=d={length:.3f}:c1=tri:c2=tri[aout]",
         "-map", "[vout]", "-map", "[aout]", *_X264, *_AAC, str(out_path)],
        "dissolve", timeout=300,
    )


def _ffmetadata_escape(value: str) -> str:
    for char in ("\\", "=", ";", "#", "\n"):
        value = value.replace(char, "\\" + char)
    return value


def _write_ffmetadata(path: Path, tags: dict[str, str]) -> None:
    """ffmpeg's own metadata format. Used instead of repeated `-metadata k=v`
    arguments because the merged manifest runs to several kilobytes of JSON,
    well past what is safe to pass as a single argv element."""
    lines = [";FFMETADATA1"]
    lines += [f"{key}={_ffmetadata_escape(value)}" for key, value in tags.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_sequence_manifest(name: str, entries: list[dict], total: float, width: int,
                             height: int, resolution: str, audio_tracks: list[dict]) -> dict:
    """The merged provenance manifest: what this cut is made of.

    Each source keeps its own record — model, prompt, hash, disclosure mode and
    whether ITS manifest verified — alongside where it sits on the timeline and
    what grading was applied to it. The summary reports `all_sources_verified`
    rather than one verified flag for the cut: the assembly ran no genblaze
    pipeline, so there is no manifest over the output to verify, and claiming
    one would be exactly the unearned badge this app argues against.
    """
    costs = [e["provenance"].get("cost_usd") for e in entries
             if e["provenance"].get("cost_usd") is not None]
    generated = [e for e in entries if e["provenance"].get("ai_generated")]
    # Only generative models. The title-card renderer and an uploaded clip's
    # "upload" marker are producers too, but listing them here would read as
    # "this cut used four AI models" — the one claim this summary exists to
    # get right.
    models = sorted({e["provenance"].get("model") for e in generated
                     if e["provenance"].get("model")})
    return {
        "type": "loomina.sequence.provenance",
        "version": 1,
        "assembled_at": datetime.now(timezone.utc).isoformat(),
        "sequence": {
            "name": name,
            "duration_s": round(total, 3),
            "width": width,
            "height": height,
            "resolution": resolution,
            "fps": SEQUENCE_FPS,
            "clip_count": len(entries),
        },
        "assembly": {
            "tool": "ffmpeg",
            "method": "per-piece encode + concat demuxer",
            "transitions": sorted({e.get("transition_in", "cut") for e in entries}),
            "text_panels": "pillow",
            "provider_calls": 0,
            "cost_usd": 0.0,
        },
        "sources": entries,
        "audio": audio_tracks,
        "summary": {
            "ai_generated_clips": len(generated),
            "captured_or_uploaded_clips": len(entries) - len(generated),
            "models": models,
            "source_cost_usd": round(sum(costs), 6) if costs else None,
            # True only if every AI-generated source carried a manifest that
            # verified. One unverified source makes the whole cut unverified —
            # that is the honest aggregation.
            "all_sources_verified": bool(generated) and all(
                e["provenance"].get("manifest_verified") for e in generated
            ),
        },
    }


def _plan_transitions(clips: list[dict], lengths: list[float]) -> tuple[list, list, list]:
    """Settle every join before a single frame is encoded.

    Returns (kinds, spans, cuts) where cuts[i] is (head, tail) — how much of
    clip i is consumed by the transitions on either side of it. A span is
    clamped by BOTH clips it touches and by what is left of them afterwards, so
    a half-second dissolve can never swallow a third of a short title card or
    leave a body piece thinner than a few frames. A span squeezed below a
    perceptible length degrades to a hard cut rather than rendering a
    transition nobody can see.
    """
    kinds, spans = [], []
    for index, clip in enumerate(clips):
        kind = clip.get("transition") or "cut"
        if kind not in SEQUENCE_TRANSITIONS:
            kind = "cut"
        # There is nothing before the first clip to dissolve from; the only
        # thing that shape can mean is opening out of black.
        if index == 0 and kind == "dissolve":
            kind = "fade"
        if kind == "cut":
            kinds.append("cut")
            spans.append(0.0)
            continue

        span = min(float(clip.get("fade_duration") or 0.5), SEQUENCE_MAX_FADE,
                   SEQUENCE_FADE_SHARE * lengths[index],
                   (lengths[index] - SEQUENCE_MIN_BODY) / 2)
        if index > 0:
            span = min(span, SEQUENCE_FADE_SHARE * lengths[index - 1],
                       (lengths[index - 1] - SEQUENCE_MIN_BODY) / 2)
        # Under about three frames there is nothing to see — the transition
        # reads as a flicker, not as a transition. Tie the floor to the frame
        # rate rather than to a guessed number of milliseconds.
        if span < 3 / SEQUENCE_FPS:
            kinds.append("cut")
            spans.append(0.0)
            continue
        kinds.append(kind)
        spans.append(round(span, 3))

    cuts = [[0.0, 0.0] for _ in clips]
    for index, kind in enumerate(kinds):
        if kind == "cut":
            continue
        cuts[index][0] = spans[index]          # head of the incoming clip
        if index > 0:
            cuts[index - 1][1] = spans[index]  # tail of the outgoing clip
    return kinds, spans, cuts


def _duck_graph(track_count: int, volumes: list[float], duck_flags: list[bool]) -> str:
    """Mix the added tracks under the cut's own audio.

    Where a track is ducked, the film's own sound drives a compressor on it, so
    music steps back the moment someone speaks and comes back up over a silent
    still — which is the difference between a bed and a track fighting the
    voice. Without sidechaincompress in the build, the level is simply static;
    the mix is quieter but never wrong.
    """
    can_duck = ffmpeg_has_filter("sidechaincompress")
    ducked = [i for i in range(track_count) if duck_flags[i] and can_duck]
    if not can_duck and any(duck_flags):
        logger.info("ffmpeg has no sidechaincompress — laying tracks at a static level instead")

    parts, mix_labels = [], []
    if ducked:
        keys = "".join(f"[key{i}]" for i in ducked)
        parts.append(f"[0:a]asplit={len(ducked) + 1}[main]{keys}")
        mix_labels.append("[main]")
    else:
        mix_labels.append("[0:a]")

    for index in range(track_count):
        source = f"[{index + 1}:a]"
        parts.append(f"{source}volume={volumes[index]:.3f}[lvl{index}]")
        if index in ducked:
            parts.append(
                f"[lvl{index}][key{index}]sidechaincompress="
                f"threshold=0.05:ratio=8:attack=20:release=350[trk{index}]")
        else:
            parts.append(f"[lvl{index}]anull[trk{index}]")
        mix_labels.append(f"[trk{index}]")

    parts.append(f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}"
                 f":duration=first:dropout_transition=0:normalize=0[aout]")
    return ";".join(parts)


def render_sequence(
    name: str,
    clips: list[dict],
    aspect_ratio: str = "16:9",
    audio_tracks: list[dict] | None = None,
    resolution: str = DEFAULT_SEQUENCE_RESOLUTION,
) -> dict:
    """Cut `clips` into one MP4 and store it in B2 with a merged manifest.

    Each clip arrives already resolved by the caller (which owns database
    access): {source, ref_id, url, duration, in_point, out_point, transition,
    fade_duration, look, motion, brightness, contrast, saturation, volume,
    text, subtitle, provenance}. `source` is "title" for a text panel, "video"
    for a moving clip, anything else for a still.

    `audio_tracks` are laid UNDER the finished cut — music or a voiceover added
    after the fact: [{url, volume, duck, provenance}]. The clips keep their own
    audio; a ducked track steps back whenever the film itself is loud.

    Returns {url, sha256, mime_type, duration, manifest, manifest_url}.
    """
    import uuid as _uuid

    from app.storage import download_bytes, upload_bytes

    if not clips:
        raise ValueError("A sequence needs at least one clip.")
    width, height = sequence_size(aspect_ratio, resolution)
    audio_tracks = audio_tracks or []

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)

        # Pass 1 — get every source onto disk and settle its real length. A
        # video's length comes from the clip itself (trimmed by in/out), never
        # from the requested duration, so the timeline can't claim time the
        # clip doesn't have. Sources are cached by URL: the object behind one
        # is immutable, so re-downloading it on every render buys nothing.
        prepared, lengths = [], []
        for clip in clips:
            voice = None
            if clip.get("voice_url"):
                voice = _cached_source(clip["voice_url"], None, ".audio")

            if clip["source"] == "title":
                style = clip.get("title_style") or "center"
                key = _cache_key({"t": clip.get("text"), "s": clip.get("subtitle"),
                                  "st": style, "w": width, "h": height})
                path = _cached("title", key, ".png", lambda out, s=style, c=clip: out.write_bytes(
                    _render_title_card(c.get("text") or "", c.get("subtitle"), width, height, s)))
                length = max(0.2, float(clip.get("duration") or 3.0))
                prepared.append({"clip": {**clip, "_still": True}, "path": path,
                                 "still": True, "start": 0.0, "voice": voice})
            elif clip["source"] == "video":
                path = _cached_source(clip["url"], (clip.get("provenance") or {}).get("sha256"), ".mp4")
                available = _probe_duration_s(path)
                start = min(max(0.0, float(clip.get("in_point") or 0.0)),
                            max(0.0, available - 0.2))
                end = clip.get("out_point")
                end = available if end is None else min(float(end), available)
                length = max(0.2, end - start)
                prepared.append({"clip": clip, "path": path, "still": False,
                                 "start": start, "voice": voice,
                                 "source_duration": available})
            else:
                sha = (clip.get("provenance") or {}).get("sha256")
                key = _cache_key({"url": clip["url"], "sha": sha, "cap": clip.get("text")})
                path = _cached("still", key, ".png", lambda out, c=clip: out.write_bytes(
                    _still_png(download_bytes(c["url"]), c.get("text"))))
                length = max(0.2, float(clip.get("duration") or 3.0))
                prepared.append({"clip": {**clip, "_still": True}, "path": path,
                                 "still": True, "start": 0.0, "voice": voice})
            lengths.append(length)

        kinds, spans, cuts = _plan_transitions(clips, lengths)

        def piece(index: int, offset: float, span: float,
                  fade_in: float = 0.0, fade_out: float = 0.0) -> Path:
            """One cached slice of clip `index`, ready to be concatenated."""
            item = prepared[index]
            clip = item["clip"]
            key = _cache_key({
                "src": clip.get("url") or str(item["path"].name),
                "sha": (clip.get("provenance") or {}).get("sha256"),
                "still": item["still"], "start": round(item["start"] + offset, 3),
                "off": round(offset, 3), "len": round(span, 3),
                "clip_len": round(lengths[index], 3),
                "w": width, "h": height, "fps": SEQUENCE_FPS,
                "fi": round(fade_in, 3), "fo": round(fade_out, 3),
                "look": clip.get("look"), "motion": clip.get("motion"),
                "b": clip.get("brightness"), "c": clip.get("contrast"),
                "s": clip.get("saturation"), "vol": clip.get("volume"),
                "voice": clip.get("voice_url"), "vvol": clip.get("voice_volume"),
                "cap": clip.get("text"), "title": clip.get("title_style"),
            })
            return _cached("piece", key, ".mp4", lambda out: _encode_piece(
                clip, out, source=item["path"],
                offset=(item["start"] + offset) if not item["still"] else offset,
                length=span, width=width, height=height,
                fade_in=fade_in, fade_out=fade_out,
                clip_length=lengths[index], voice=item["voice"],
            ))

        # Pass 2 — lay out the pieces in order. A fade emits a darkened tail and
        # a lifting head as separate pieces (total length unchanged); a dissolve
        # emits ONE piece that is both clips at once (total length shortened by
        # the overlap). Everything between is untouched body.
        pieces, entries, at = [], [], 0.0
        for index, item in enumerate(prepared):
            clip, length, span = item["clip"], lengths[index], spans[index]
            head_cut, tail_cut = cuts[index]

            if kinds[index] == "fade":
                pieces.append(piece(index, 0.0, span, fade_in=span))
            elif kinds[index] == "dissolve":
                tail = piece(index - 1, lengths[index - 1] - span, span)
                head = piece(index, 0.0, span)
                blend_key = _cache_key({"tail": tail.name, "head": head.name, "d": round(span, 3)})
                pieces.append(_cached("blend", blend_key, ".mp4",
                                      lambda out, a=tail, b=head, s=span: _encode_dissolve(a, b, out, s)))
                at -= span  # a dissolve overlaps, so the film gets shorter here

            body = length - head_cut - tail_cut
            if body > 0.01:
                pieces.append(piece(index, head_cut, body))

            entry = {
                "index": index,
                "source": clip["source"],
                "ref_id": clip.get("ref_id"),
                "starts_at_s": round(at, 3),
                "duration_s": round(length, 3),
                "transition_in": kinds[index],
                "transition_s": round(span, 3) if kinds[index] != "cut" else 0.0,
                "look": clip.get("look") or "none",
                "motion": clip.get("motion") or "none",
                "provenance": dict(clip.get("provenance") or {}),
            }
            if clip["source"] == "title":
                entry["text"] = clip.get("text")
                entry["subtitle"] = clip.get("subtitle")
                entry["title_style"] = clip.get("title_style") or "center"
            else:
                entry["url"] = clip["url"]
                if clip.get("text"):
                    entry["burned_in_caption"] = clip["text"]
            if not item["still"]:
                entry["trimmed_from"] = {
                    "in_s": round(item["start"], 3),
                    "out_s": round(item["start"] + length, 3),
                    "source_duration_s": round(item["source_duration"], 3),
                }
            if clip.get("voice_url"):
                entry["voiceover"] = {
                    "url": clip["voice_url"],
                    "volume": clip.get("voice_volume") or 1.0,
                }
            entries.append(entry)
            at += length

            # A fade out of this clip into the next belongs after its body.
            if index + 1 < len(prepared) and kinds[index + 1] == "fade":
                next_span = spans[index + 1]
                pieces.append(piece(index, length - next_span, next_span, fade_out=next_span))

        # Pass 3 — join. Every piece shares codec, rate, size and channel
        # layout, so the concat demuxer can stream-copy them.
        list_path = tmp / "pieces.txt"
        list_path.write_text("\n".join(f"file '{p}'" for p in pieces) + "\n")
        joined = tmp / "joined.mp4"
        _run_ffmpeg(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
             "-c", "copy", "-fflags", "+genpts", str(joined)],
            "concat", timeout=420,
        )

        total = _probe_duration_s(joined)
        manifest = _build_sequence_manifest(
            name, entries, total, width, height, resolution,
            [{"url": t.get("url"), "volume": t.get("volume", 0.25),
              "ducked": bool(t.get("duck", True)),
              "provenance": t.get("provenance") or {}} for t in audio_tracks],
        )

        # Pass 4 — lay the added audio under the cut and bake the manifest into
        # the file. `duration=first` keeps the cut's own length authoritative:
        # a soundtrack longer than the film is cut off, a shorter one (looped
        # by -stream_loop) never extends it.
        meta_path = tmp / "manifest.ffmeta"
        _write_ffmetadata(meta_path, {
            "title": name,
            "comment": (
                f"Assembled by Loomina from {len(entries)} vault clips "
                f"({manifest['summary']['ai_generated_clips']} AI-generated). "
                "Full provenance in the loomina_provenance tag."
            ),
            "loomina_provenance": json.dumps(manifest, separators=(",", ":")),
        })

        out_path = tmp / "out.mp4"
        args = ["ffmpeg", "-y", "-i", str(joined)]
        for track_index, track in enumerate(audio_tracks):
            track_path = _cached_source(track["url"], None, f".track{track_index}")
            args += ["-stream_loop", "-1", "-i", str(track_path)]
        args += ["-f", "ffmetadata", "-i", str(meta_path)]

        if audio_tracks:
            volumes = [max(0.0, min(2.0, float(t.get("volume") or 0.25))) for t in audio_tracks]
            ducks = [bool(t.get("duck", True)) for t in audio_tracks]
            args += ["-filter_complex", _duck_graph(len(audio_tracks), volumes, ducks),
                     "-map", "0:v:0", "-map", "[aout]",
                     "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                     "-map_metadata", str(len(audio_tracks) + 1)]
        else:
            args += ["-map", "0:v:0", "-map", "0:a:0", "-c", "copy", "-map_metadata", "1"]
        args += ["-movflags", "use_metadata_tags+faststart", str(out_path)]
        _run_ffmpeg(args, "final mux", timeout=600)

        data = out_path.read_bytes()
        duration = _probe_duration_s(out_path)

    # Keep the cache within its budget once the render owns no temp files —
    # doing it earlier could evict a piece this very render still needs.
    prune_piece_cache()

    stem = _uuid.uuid4().hex
    url, sha = upload_bytes(f"videos/sequence/{stem}.mp4", data, "video/mp4")
    # The sidecar keeps the manifest readable without an ffprobe round-trip and
    # survives any player or upload that strips container metadata.
    manifest_url, _ = upload_bytes(
        f"videos/sequence/{stem}.manifest.json",
        json.dumps(manifest, indent=2).encode("utf-8"),
        "application/json",
    )
    return {
        "url": url,
        "sha256": sha,
        "mime_type": "video/mp4",
        "duration": duration,
        "manifest": manifest,
        "manifest_url": manifest_url,
    }


def read_embedded_manifest(path_or_url: str) -> dict | None:
    """Read the merged manifest back out of a rendered MP4.

    The point of embedding it is that the cut carries its own provenance
    wherever it travels — this is the reader that proves it, and what a
    verifier would use on a file that arrived without our database.
    """
    import json
    import subprocess

    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format_tags",
             "-of", "json", path_or_url],
            capture_output=True, text=True, timeout=60,
        ).stdout
        tags = json.loads(out or "{}").get("format", {}).get("tags", {})
    except Exception:
        return None
    raw = tags.get("loomina_provenance") or tags.get("LOOMINA_PROVENANCE")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def probe_media(path_or_url: str) -> dict:
    """Duration and pixel size of a media file, for uploads that arrive with no
    metadata of their own. Best-effort: a file ffprobe can't read is still
    stored, it just shows up in the timeline without a known length."""
    import json
    import subprocess

    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=width,height,codec_type",
             "-of", "json", path_or_url],
            capture_output=True, text=True, timeout=60,
        ).stdout
        data = json.loads(out or "{}")
    except Exception:
        return {"duration": None, "width": None, "height": None}
    try:
        duration = float(data.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        duration = None
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    return {"duration": duration, "width": video.get("width"), "height": video.get("height")}


# ── AI-assisted cut ──────────────────────────────────────────────────────
# The editorial decision — which shot, how long, in what order — is the one
# part of this chain the app could not previously help with. The model gets
# what an assistant editor would get: the shot list with its prompts and real
# durations, the brief, and the target length. It returns an edit, not media,
# and every id it names is checked against the pool before anything renders —
# a hallucinated shot is dropped, not fetched.

SEQUENCE_PLANNER_MODEL = "gpt-4o-mini"

_PLANNER_SYSTEM = (
    "You are an assistant video editor. You are given a shot list from a media "
    "library and a brief, and you return an edit decision list as JSON. You "
    "never invent shots: every clip you use must reference a key from the shot "
    "list verbatim. Good editing means varying shot length (2-5s for stills, "
    "the natural length for motion clips), opening on the strongest image, "
    "using fades only where a beat genuinely changes, and ending on the shot "
    "that carries the message. Add short title cards only where they earn "
    "their screen time — an opener and a closing line at most, unless asked "
    "for more."
)

_PLANNER_SCHEMA = (
    'Return ONLY JSON of the form {"name": string, "clips": [clip, ...]} where a '
    'clip is either {"key": "<shot key from the list>", "duration": number, '
    '"transition": "cut"|"fade"|"dissolve", "look": "none"|"enhance"|"warm"|'
    '"cool"|"noir"|"vivid"|"vintage"|"soft", "motion": "none"|"zoom_in"|'
    '"zoom_out"|"pan_left"|"pan_right", "text": string|null} or a title card '
    '{"key": "title", "duration": number, "transition": "cut"|"fade"|"dissolve", '
    '"text": string, "subtitle": string|null, "title_style": "center"|'
    '"lower_third"|"left"|"end_card"}. "motion" applies to stills only. '
    '"dissolve" blends two shots and suits a soft change of place or time; '
    '"fade" dips through black and suits a real break. "text" on a non-title '
    'clip is a caption burned into the frame — use it sparingly.'
)


def plan_sequence(brief: str, pool: list[dict], target_seconds: int = 30,
                  aspect_ratio: str = "16:9") -> dict:
    """Ask the model for an edit over `pool`.

    `pool` entries: {key, kind ("still"/"video"), label, duration}. Returns the
    raw {"name", "clips"} dict — the caller validates every key against the
    pool and turns it into real clips, so a wrong or invented key can never
    reach the renderer.
    """
    import json

    from openai import OpenAI

    if not pool:
        raise ValueError("There is nothing in the vault to cut yet.")

    shots = "\n".join(
        f"- {p['key']} [{p['kind']}"
        + (f", {p['duration']:.1f}s" if p.get("duration") else "")
        + f"]: {(p.get('label') or '').strip()[:160]}"
        for p in pool
    )
    user = (
        f"Brief: {brief}\n"
        f"Target length: about {target_seconds} seconds.\n"
        f"Aspect ratio: {aspect_ratio}.\n\n"
        f"Shot list:\n{shots}\n\n{_PLANNER_SCHEMA}"
    )
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=SEQUENCE_PLANNER_MODEL,
        messages=[{"role": "system", "content": _PLANNER_SYSTEM},
                  {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        max_tokens=2000,
        temperature=0.7,
    )
    return json.loads(resp.choices[0].message.content or "{}")


def generate_motion_comic(panels: list[dict], music_url: str | None = None) -> dict:
    """A slideshow, not a video model: each panel's still image is shown for
    exactly as long as its own voice line takes to speak, in order. No GMI
    video call happens at all — this is the deliberate workaround for
    multi-character talking video, since kling-identify-face only ever
    detects a single face per clip (confirmed: a 2-person scene image still
    only returns one face_data entry), so real lip-sync across several
    characters at once isn't achievable there.

    `panels`: [{"image_url", "character_id", "character_name",
    "voice_provider", "voice_id", "text", "caption"}, ...] — one entry per
    panel, in display order. `caption` is optional per-panel overlay text
    (subtitle or a CTA line), burned into the still image directly.
    `music_url` is an optional background track, looped to length and mixed
    under the voice lines at reduced volume. Returns {url, sha256,
    mime_type, duration, cost_usd, manifest_verified, script}."""
    import subprocess
    import uuid as _uuid

    from app.storage import download_bytes, upload_bytes

    lines = []
    for panel in panels:
        asset = generate_character_voice_line(
            panel["character_id"], panel["text"], panel.get("voice_provider"), panel.get("voice_id"),
        )
        lines.append({**panel, "asset": asset})

    with tempfile.TemporaryDirectory() as d:
        audio_paths, image_paths, durations = [], [], []
        for i, line in enumerate(lines):
            ap = Path(d) / f"a{i}.mp3"
            ap.write_bytes(download_bytes(line["asset"]["url"]))
            audio_paths.append(ap)
            durations.append(_probe_duration_s(ap))

            ip = Path(d) / f"img{i}.png"
            image_bytes = download_bytes(line["image_url"])
            if line.get("caption"):
                image_bytes = _draw_caption(image_bytes, line["caption"])
            ip.write_bytes(image_bytes)
            image_paths.append(ip)

        audio_inputs = []
        for p in audio_paths:
            audio_inputs += ["-i", str(p)]
        filter_a = "".join(f"[{i}:a]" for i in range(len(audio_paths)))
        combined_audio = Path(d) / "audio.mp3"
        subprocess.run(
            ["ffmpeg", "-y", *audio_inputs, "-filter_complex",
             f"{filter_a}concat=n={len(audio_paths)}:v=0:a=1[out]", "-map", "[out]", str(combined_audio)],
            check=True, capture_output=True, timeout=120,
        )

        if music_url:
            music_path = Path(d) / "music.src"
            music_path.write_bytes(download_bytes(music_url))
            mixed_audio = Path(d) / "mixed.mp3"
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(combined_audio), "-stream_loop", "-1", "-i", str(music_path),
                 "-filter_complex",
                 "[1:a]volume=0.18[music];[0:a][music]amix=inputs=2:duration=first:dropout_transition=0[aout]",
                 "-map", "[aout]", str(mixed_audio)],
                check=True, capture_output=True, timeout=120,
            )
            combined_audio = mixed_audio

        # concat demuxer: each image held for its own line's duration; the
        # final entry is repeated without a duration (ffmpeg quirk — the
        # last file's duration is otherwise ignored).
        list_path = Path(d) / "images.txt"
        entries = []
        for ip, dur in zip(image_paths, durations):
            entries.append(f"file '{ip}'")
            entries.append(f"duration {dur}")
        entries.append(f"file '{image_paths[-1]}'")
        list_path.write_text("\n".join(entries))

        slideshow = Path(d) / "slideshow.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
             "-vf", "fps=24,format=yuv420p", str(slideshow)],
            check=True, capture_output=True, timeout=120,
        )

        op = Path(d) / "out.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(slideshow), "-i", str(combined_audio),
             "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
             "-map", "0:v:0", "-map", "1:a:0", "-shortest", str(op)],
            check=True, capture_output=True, timeout=120,
        )
        out = op.read_bytes()
        total_duration = _probe_duration_s(op)

    url, sha = upload_bytes(f"videos/motion-comic/{_uuid.uuid4().hex}.mp4", out, "video/mp4")
    costs = [l["asset"].get("cost_usd") for l in lines if l["asset"].get("cost_usd") is not None]
    return {
        "url": url,
        "sha256": sha,
        "mime_type": "video/mp4",
        "duration": total_duration,
        "manifest_verified": all(l["asset"].get("manifest_verified") for l in lines),
        "cost_usd": sum(costs) if costs else None,
        "script": [
            {"character_id": l["character_id"], "character_name": l["character_name"], "text": l["text"]}
            for l in lines
        ],
    }
