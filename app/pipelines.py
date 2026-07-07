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
        })
    return out


def _gmi_references(references: list[dict]) -> list[Asset]:
    """GMI Cloud requires HTTPS reference URLs — use presigned B2 links."""
    from app.storage import presign_asset_url

    assets = []
    for ref in references[:3]:
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

    if meta["provider"] == "gmi":
        from genblaze_gmicloud import GMICloudImageProvider

        provider = GMICloudImageProvider()
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


# Each character can be assigned a voice from either provider, switchable
# anytime. OpenAI voices work everywhere (incl. Railway). ElevenLabs is
# richer but its free tier blocks datacenter IPs, so from the cloud it may
# be unreachable — those requests fall back to a deterministic OpenAI voice,
# and the asset records which voice actually spoke.
OPENAI_VOICES = [
    {"id": "alloy", "name": "Alloy — neutral"},
    {"id": "ash", "name": "Ash — warm male"},
    {"id": "ballad", "name": "Ballad — soft male"},
    {"id": "coral", "name": "Coral — bright female"},
    {"id": "echo", "name": "Echo — calm male"},
    {"id": "fable", "name": "Fable — expressive"},
    {"id": "nova", "name": "Nova — friendly female"},
    {"id": "onyx", "name": "Onyx — deep male"},
    {"id": "sage", "name": "Sage — measured"},
    {"id": "shimmer", "name": "Shimmer — light female"},
]
_OPENAI_VOICE_IDS = {v["id"] for v in OPENAI_VOICES}

# Curated ElevenLabs premade voices (stable public IDs) so the picker works
# without a server-side ElevenLabs call (which is blocked in the cloud).
ELEVENLABS_VOICES = [
    {"id": "JBFqnCBsd6RMkjVDRZzb", "name": "George — warm storyteller"},
    {"id": "nPczCjzI2devNBz1zQrb", "name": "Brian — deep, resonant"},
    {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel — calm female"},
    {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah — soft news"},
    {"id": "pFZP5JQG7iQjIQuC4Bku", "name": "Lily — warm female"},
    {"id": "TX3LPaxmHKxFdv7VOQHJ", "name": "Liam — youthful male"},
]


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
        except Exception:
            pass  # ElevenLabs unreachable (e.g. cloud IP block) → OpenAI fallback

    if voice_provider == "openai" and voice_id in _OPENAI_VOICE_IDS:
        voice = voice_id
    else:
        voice = _default_openai_voice(character_id)
    return _openai_voice_line(character_id, text, voice)
