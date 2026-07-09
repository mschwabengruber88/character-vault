import logging
import os
import tempfile
import threading
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


SCENE_INSTRUCTION = (
    "Compose a single new image containing ALL of these characters together in "
    "one scene, each matching their own reference image exactly (same face, hair, "
    "colors, and outfit). Do not merge or swap their features. "
    "Apply ONE consistent art style and color treatment across the ENTIRE image — "
    "if it's black-and-white/monochrome, render every character and the background "
    "in grayscale too; never selectively color in just one character's hair or "
    "clothing while the rest stays monochrome. If the scene includes speech "
    "bubbles, draw each bubble's tail pointing clearly at the character who is "
    "speaking it, positioned near their mouth, so it's unambiguous who says what. "
)

IDENTITY_INSTRUCTION = (
    "Use the person from the reference image(s) and keep their identity exactly: "
    "same face, facial features, hair color and style, age, and build. "
    "Render that same person in a new scene: "
)

# OpenAI API list prices per 1024x1024 image (July 2026); draft iterations
# cost ~15x less than finals — the main waste-reduction lever.
QUALITY_TIERS = {"draft": "low", "final": "high"}
IMAGE_COST_USD = {"draft": 0.011, "final": 0.167}

# Image-model registry. gpt-image-1 (OpenAI) is the general-purpose model
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
    "gpt-image-1": {
        "label": "OpenAI gpt-image-1",
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
DEFAULT_IMAGE_MODEL = "gpt-image-1"


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
        provider = DalleProvider()
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
            .run(sink=get_storage_sink(), timeout=180)
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
GMI_VOICES = VOICE_CATALOG.get("gmi", [])
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
