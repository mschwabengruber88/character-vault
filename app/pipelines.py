import logging
import os
import tempfile
from pathlib import Path

from genblaze_core import KeyStrategy, Modality, ObjectStorageSink, Pipeline, StepStatus
from genblaze_core.models.asset import Asset
from genblaze_elevenlabs import ElevenLabsTTSProvider
from genblaze_openai import DalleProvider, OpenAITTSProvider
from genblaze_s3 import S3StorageBackend

from app.config import (
    B2_BUCKET_NAME,
    B2_REGION,
    ELEVENLABS_API_KEY,
    GMI_API_KEY,
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

# gpt-4o-mini-tts: ~$12 per 1M input characters. ElevenLabs cost depends
# on the account's plan, so we don't guess it (cost stays None).
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
    from genblaze_gmicloud import GMICloudVideoProvider

    meta = VIDEO_MODELS[model]
    step_kwargs: dict = {"duration": duration, "aspect_ratio": aspect_ratio}
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
            GMICloudVideoProvider(),
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
# anytime. OpenAI voices work everywhere (incl. Railway). ElevenLabs is
# richer but its free tier blocks datacenter IPs, so from the cloud it may
# be unreachable — those requests fall back to a deterministic OpenAI voice,
# and the asset records which voice actually spoke.
# The catalog (id/name/gender/age/style per voice) is generated alongside the
# sample clips by scripts/generate_voice_samples.py and committed. Loaded once.
def _load_voice_catalog() -> dict:
    import json

    path = Path(__file__).parent / "static" / "voice-samples" / "catalog.json"
    try:
        return json.loads(path.read_text())
    except Exception:
        return {"openai": [{"id": "onyx", "name": "Onyx", "gender": "male",
                            "age": "mature", "style": "deep"}], "elevenlabs": []}


VOICE_CATALOG = _load_voice_catalog()
OPENAI_VOICES = VOICE_CATALOG.get("openai", [])
ELEVENLABS_VOICES = VOICE_CATALOG.get("elevenlabs", [])
_OPENAI_VOICE_IDS = {v["id"] for v in OPENAI_VOICES}


def available_voices() -> dict:
    voices = {"openai": OPENAI_VOICES}
    if ELEVENLABS_API_KEY:
        voices["elevenlabs"] = ELEVENLABS_VOICES
    return voices


def _default_openai_voice(character_id: int) -> str:
    return OPENAI_VOICES[character_id % len(OPENAI_VOICES)]["id"]


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
    character. Accepts any ElevenLabs voice_id (so users can import their own
    cloned voice by ID); OpenAI voice_ids are validated by the caller. Reuses
    the same generation path (incl. ElevenLabs→OpenAI cloud fallback)."""
    return generate_character_voice_line(0, text, voice_provider, voice_id)


def generate_character_voice_line(
    character_id: int,
    text: str,
    voice_provider: str | None = None,
    voice_id: str | None = None,
) -> dict:
    if voice_provider == "elevenlabs" and voice_id and ELEVENLABS_API_KEY:
        try:
            result = (
                Pipeline(f"character-{character_id}-voice-line")
                .step(
                    ElevenLabsTTSProvider(output_dir=tempfile.gettempdir()),
                    model="eleven_v3",
                    prompt=text,
                    modality=Modality.AUDIO,
                    voice_id=voice_id,
                )
                .run(sink=get_storage_sink(), timeout=120)
            )
            asset = _asset_result(result)
            asset["cost_usd"] = None  # ElevenLabs pricing is plan-dependent
            asset["voice"] = f"elevenlabs:{voice_id}"
            return asset
        except Exception as exc:
            # Surface WHY it fell back (cloud IP block, quota, voice needs a
            # paid plan, …) instead of silently swallowing it.
            logger.warning(
                "ElevenLabs voice %s unavailable, falling back to OpenAI: %s",
                voice_id, exc,
            )

    if voice_provider == "openai" and voice_id in _OPENAI_VOICE_IDS:
        voice = voice_id
    else:
        voice = _default_openai_voice(character_id)
    return _openai_voice_line(character_id, text, voice)
