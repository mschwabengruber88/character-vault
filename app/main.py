import logging
import threading
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import db
from app.config import CORS_ORIGINS, GENERATE_API_KEY
from app.pipelines import (
    DEFAULT_IMAGE_MODEL,
    IMAGE_COST_USD,
    IMAGE_MODELS,
    MODE_MAX,
    available_image_models,
    available_voices,
    DEFAULT_VIDEO_MODEL,
    VIDEO_MODELS,
    available_video_models,
    build_batch_prompts,
    generate_audio,
    generate_character_portrait,
    generate_character_voice_line,
    generate_scene,
    generate_studio_image,
    generate_video,
)
from app.storage import presign_asset_url, upload_reference_image, with_signed_url

logger = logging.getLogger("character_vault")


def require_api_key(x_api_key: str = Header(default="")):
    if not GENERATE_API_KEY or x_api_key != GENERATE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


_inflight_lock = threading.Lock()
_inflight: set[tuple[int, str]] = set()


def _acquire_slot(character_id: int, kind: str) -> None:
    key = (character_id, kind)
    with _inflight_lock:
        if key in _inflight:
            raise HTTPException(
                status_code=409,
                detail="A generation for this character is already running. Please wait for it to finish.",
            )
        _inflight.add(key)


def _release_slot(character_id: int, kind: str) -> None:
    with _inflight_lock:
        _inflight.discard((character_id, kind))


@contextmanager
def generation_slot(character_id: int, kind: str):
    """One paid generation per character+kind at a time — a duplicate
    request (double-click, impatient retry) is rejected instead of
    silently billed twice."""
    _acquire_slot(character_id, kind)
    try:
        yield
    finally:
        _release_slot(character_id, kind)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Character Vault", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


class CharacterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    personality: str | None = Field(default=None, max_length=1000)
    purpose: str | None = Field(default=None, max_length=500)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


class CharacterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    personality: str | None = Field(default=None, max_length=1000)
    purpose: str | None = Field(default=None, max_length=500)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


class PortraitRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)
    disclosure: Literal["visible", "invisible"] = "invisible"
    use_identity: bool = True
    quality: Literal["draft", "final"] = "draft"
    model: str = DEFAULT_IMAGE_MODEL


def identity_references(character: dict) -> list[dict]:
    """Pick reference images for consistent identity: the character's first
    portrait anchors the identity, plus up to two of the newest portraits.
    Uses the untouched originals, never watermarked copies."""
    images = [a for a in character["assets"] if a["kind"] == "image"]
    if not images:
        return []
    picked = [images[0]] + images[1:][-2:]
    seen: set[int] = set()
    refs = []
    for asset in picked:
        if asset["id"] not in seen:
            seen.add(asset["id"])
            refs.append({
                "url": asset.get("original_url") or asset["url"],
                "sha256": asset.get("sha256"),
            })
    return refs


class BatchRequest(BaseModel):
    mode: Literal["single", "variation", "photoshoot", "story"]
    prompt: str = Field(min_length=1, max_length=4000)
    count: int = Field(default=1, ge=1, le=100)
    disclosure: Literal["visible", "invisible"] = "invisible"
    use_identity: bool = True
    quality: Literal["draft", "final"] = "draft"
    model: str = DEFAULT_IMAGE_MODEL


def per_image_cost(model: str, quality: str) -> float | None:
    """Best-effort per-image price for the estimate shown before a batch runs."""
    meta = IMAGE_MODELS.get(model, {})
    if meta.get("quality_tiers"):
        return IMAGE_COST_USD.get(quality)
    return meta.get("cost_usd")


class VoiceLineRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class VoiceAssign(BaseModel):
    voice_provider: Literal["openai", "elevenlabs"]
    voice_id: str = Field(min_length=1, max_length=100)


class SceneRequest(BaseModel):
    character_ids: list[int] = Field(min_length=2, max_length=4)
    prompt: str = Field(min_length=1, max_length=500)
    disclosure: Literal["visible", "invisible"] = "invisible"


def scene_reference(character: dict) -> tuple[dict, str] | None:
    """One identity anchor (first portrait) per character, plus an appearance
    descriptor built from the character's name and that portrait's prompt."""
    images = [a for a in character["assets"] if a["kind"] == "image"]
    if not images:
        return None
    anchor = images[0]
    ref = {"url": anchor.get("original_url") or anchor["url"], "sha256": anchor.get("sha256")}
    appearance = (anchor.get("prompt") or "").strip()[:160]
    descriptor = f"{character['name']} ({appearance})" if appearance else character["name"]
    return ref, descriptor


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/capabilities")
def capabilities():
    return {
        "image_models": available_image_models(),
        "video_models": available_video_models(),
    }


@app.get("/voices")
def voices():
    return available_voices()


@app.post("/characters")
def create_character(body: CharacterCreate):
    return db.create_character(
        body.name, body.description, body.personality, body.purpose, body.seed
    )


@app.patch("/characters/{character_id}")
def update_character(character_id: int, body: CharacterUpdate):
    character = db.update_character(character_id, body.model_dump(exclude_unset=True))
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    character["assets"] = [with_signed_url(a) for a in character["assets"]]
    return character


@app.get("/characters")
def list_characters():
    characters = db.list_characters()
    for character in characters:
        source = character.pop("thumbnail_source_url", None)
        character["thumbnail_url"] = presign_asset_url(source) if source else None
    return characters


@app.get("/characters/{character_id}")
def get_character(character_id: int):
    character = db.get_character(character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    character["assets"] = [with_signed_url(a) for a in character["assets"]]
    return character


MAX_UPLOAD_BYTES = 12 * 1024 * 1024
ALLOWED_UPLOAD_TYPES = {"image/png", "image/jpeg", "image/webp"}


@app.post("/characters/{character_id}/reference", dependencies=[Depends(require_api_key)])
async def upload_reference(character_id: int, file: UploadFile = File(...)):
    character = db.get_character(character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    if file.content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(status_code=400, detail="Upload a PNG, JPEG or WebP image.")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Image too large (max 12 MB).")
    url, sha256 = upload_reference_image(character_id, data, file.content_type)
    return with_signed_url(db.add_asset(
        character_id=character_id,
        kind="image",
        url=url,
        sha256=sha256,
        mime_type=file.content_type,
        prompt="Uploaded reference photo",
        manifest_verified=False,
        original_url=url,
        model="upload",
    ))


@app.put("/characters/{character_id}/voice")
def set_character_voice(character_id: int, body: VoiceAssign):
    valid_ids = {v["id"] for v in available_voices().get(body.voice_provider, [])}
    if body.voice_id not in valid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Voice '{body.voice_id}' is not available for provider '{body.voice_provider}'.",
        )
    character = db.set_character_voice(character_id, body.voice_provider, body.voice_id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


@app.delete("/characters/{character_id}", status_code=204)
def delete_character(character_id: int):
    if not db.delete_character(character_id):
        raise HTTPException(status_code=404, detail="Character not found")


@app.get("/assets")
def list_assets(kind: str | None = Query(default=None, pattern="^(image|voice)$")):
    return [with_signed_url(a) for a in db.list_assets(kind)]


@app.delete("/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: int):
    if not db.delete_asset(asset_id):
        raise HTTPException(status_code=404, detail="Asset not found")


@app.post("/characters/{character_id}/generate/image", dependencies=[Depends(require_api_key)])
def generate_image(character_id: int, body: PortraitRequest):
    character = db.get_character(character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    if body.model not in {m["slug"] for m in available_image_models()}:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{body.model}' is not available. Configure its API key first.",
        )
    references = identity_references(character) if body.use_identity else []
    with generation_slot(character_id, "image"):
        try:
            result = generate_character_portrait(
                character_id, body.prompt, body.disclosure, references, body.quality,
                body.model, character.get("personality"), character.get("seed"),
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("Image generation failed for character %s", character_id)
            raise HTTPException(status_code=502, detail="Image generation failed. Please try again.")
    return with_signed_url(db.add_asset(
        character_id=character_id,
        kind="image",
        url=result["url"],
        sha256=result["sha256"],
        mime_type=result["mime_type"],
        prompt=body.prompt,
        manifest_verified=result["manifest_verified"],
        disclosure=result.get("disclosure"),
        original_url=result.get("original_url"),
        quality=result.get("quality"),
        cost_usd=result.get("cost_usd"),
        model=result.get("model"),
    ))


def _run_batch(job_id: int, character_id: int, prompts: list[str], references: list[dict],
               body: BatchRequest, personality: str | None, base_seed: int | None) -> None:
    """Background worker: generate each frame in turn, recording every image as
    a normal asset tagged with this batch. A cancelled job stops between frames
    so a runaway 100-image run can be halted without wasting the rest."""
    try:
        for i, prompt in enumerate(prompts):
            job = db.get_batch(job_id)
            if job is None or job["status"] == "cancelled":
                break
            seed = None if base_seed is None else base_seed + i
            try:
                result = generate_character_portrait(
                    character_id, prompt, body.disclosure, references, body.quality,
                    body.model, personality, seed,
                )
                db.add_asset(
                    character_id=character_id, kind="image", url=result["url"],
                    sha256=result["sha256"], mime_type=result["mime_type"], prompt=prompt,
                    manifest_verified=result["manifest_verified"],
                    disclosure=result.get("disclosure"), original_url=result.get("original_url"),
                    quality=result.get("quality"), cost_usd=result.get("cost_usd"),
                    model=result.get("model"), batch_id=job_id,
                )
                db.bump_batch(job_id, completed=1)
            except Exception:
                logger.exception("Batch %s frame %s failed", job_id, i)
                db.bump_batch(job_id, failed=1)
        final = db.get_batch(job_id)
        if final and final["status"] != "cancelled":
            done = final["completed"] > 0
            db.finish_batch(job_id, "done" if done else "error",
                            None if done else "No frames were generated.")
    finally:
        _release_slot(character_id, "image")


@app.post("/characters/{character_id}/generate/batch", dependencies=[Depends(require_api_key)])
def generate_batch(character_id: int, body: BatchRequest):
    character = db.get_character(character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    if body.model not in {m["slug"] for m in available_image_models()}:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{body.model}' is not available. Configure its API key first.",
        )
    prompts = build_batch_prompts(body.mode, body.prompt, body.count)
    if not prompts:
        raise HTTPException(status_code=400, detail="Nothing to generate — the script is empty.")
    if len(prompts) > MODE_MAX[body.mode]:
        prompts = prompts[: MODE_MAX[body.mode]]

    unit = per_image_cost(body.model, body.quality)
    estimate = round(unit * len(prompts), 4) if unit is not None else None
    references = identity_references(character) if body.use_identity else []

    _acquire_slot(character_id, "image")
    try:
        job = db.create_batch(
            character_id=character_id, mode=body.mode, prompt=body.prompt,
            requested=len(prompts), quality=body.quality, model=body.model,
            disclosure=body.disclosure, cost_estimate=estimate,
        )
    except Exception:
        _release_slot(character_id, "image")
        raise
    thread = threading.Thread(
        target=_run_batch,
        args=(job["id"], character_id, prompts, references, body,
              character.get("personality"), character.get("seed")),
        daemon=True,
    )
    thread.start()
    return job


@app.get("/batches/{batch_id}")
def get_batch(batch_id: int):
    job = db.get_batch(batch_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return job


@app.post("/batches/{batch_id}/cancel")
def cancel_batch(batch_id: int):
    job = db.get_batch(batch_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    if job["status"] == "running":
        db.finish_batch(batch_id, "cancelled")
    return db.get_batch(batch_id)


@app.post("/characters/{character_id}/generate/voice", dependencies=[Depends(require_api_key)])
def generate_voice(character_id: int, body: VoiceLineRequest):
    character = db.get_character(character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    with generation_slot(character_id, "voice"):
        try:
            result = generate_character_voice_line(
                character_id, body.text,
                character.get("voice_provider"), character.get("voice_id"),
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("Voice generation failed for character %s", character_id)
            raise HTTPException(status_code=502, detail="Voice generation failed. Please try again.")
    return with_signed_url(db.add_asset(
        character_id=character_id,
        kind="voice",
        url=result["url"],
        sha256=result["sha256"],
        mime_type=result["mime_type"],
        prompt=body.text,
        manifest_verified=result["manifest_verified"],
        cost_usd=result.get("cost_usd"),
        model=result.get("voice"),
    ))


def _scene_with_signed_url(scene: dict) -> dict:
    try:
        scene["signed_url"] = presign_asset_url(scene["url"])
    except Exception:
        scene["signed_url"] = None
    return scene


@app.get("/scenes")
def list_scenes():
    return [_scene_with_signed_url(s) for s in db.list_scenes()]


@app.post("/scenes", dependencies=[Depends(require_api_key)])
def create_scene(body: SceneRequest):
    references, descriptors, names, ids = [], [], [], []
    for cid in body.character_ids:
        character = db.get_character(cid)
        if character is None:
            raise HTTPException(status_code=404, detail=f"Character {cid} not found")
        result = scene_reference(character)
        if result is None:
            raise HTTPException(
                status_code=400,
                detail=f"Character '{character['name']}' has no portrait to use as reference.",
            )
        ref, descriptor = result
        references.append(ref)
        descriptors.append(descriptor)
        names.append(character["name"])
        ids.append(cid)

    if not IMAGE_MODELS["gemini-2.5-flash-image"]["provider"] == "gmi" or \
            "gemini-2.5-flash-image" not in {m["slug"] for m in available_image_models()}:
        raise HTTPException(
            status_code=400,
            detail="Multi-character scenes need the Nano Banana model (GMI_API_KEY not configured).",
        )

    with generation_slot(0, "scene"):
        try:
            result = generate_scene(body.prompt, references, descriptors, body.disclosure)
        except HTTPException:
            raise
        except Exception:
            logger.exception("Scene generation failed for %s", ids)
            raise HTTPException(status_code=502, detail="Scene generation failed. Please try again.")

    return _scene_with_signed_url(db.create_scene(
        prompt=body.prompt,
        url=result["url"],
        original_url=result.get("original_url"),
        sha256=result["sha256"],
        model=result.get("model"),
        disclosure=result.get("disclosure"),
        cost_usd=result.get("cost_usd"),
        manifest_verified=result["manifest_verified"],
        participant_ids=ids,
        participant_names=names,
    ))


@app.delete("/scenes/{scene_id}", status_code=204)
def delete_scene(scene_id: int):
    if not db.delete_scene(scene_id):
        raise HTTPException(status_code=404, detail="Scene not found")


class StudioRequest(BaseModel):
    kind: Literal["background", "photo-art"]
    prompt: str = Field(min_length=1, max_length=4000)
    disclosure: Literal["visible", "invisible"] = "invisible"
    quality: Literal["draft", "final"] = "draft"
    model: str = DEFAULT_IMAGE_MODEL


@app.get("/studio")
def list_studio(kind: str | None = Query(default=None, pattern="^(background|photo-art)$")):
    return [_scene_with_signed_url(s) for s in db.list_studio_images(kind)]


@app.post("/studio", dependencies=[Depends(require_api_key)])
def create_studio(body: StudioRequest):
    if body.model not in {m["slug"] for m in available_image_models()}:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{body.model}' is not available. Configure its API key first.",
        )
    with generation_slot(0, "studio"):
        try:
            result = generate_studio_image(
                body.prompt, body.kind, body.disclosure, body.quality, body.model,
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("Studio generation failed (%s)", body.kind)
            raise HTTPException(status_code=502, detail="Image generation failed. Please try again.")
    return _scene_with_signed_url(db.create_studio_image(
        kind=body.kind,
        prompt=body.prompt,
        url=result["url"],
        original_url=result.get("original_url"),
        sha256=result["sha256"],
        model=result.get("model"),
        quality=result.get("quality"),
        disclosure=result.get("disclosure"),
        cost_usd=result.get("cost_usd"),
        manifest_verified=result["manifest_verified"],
    ))


@app.delete("/studio/{image_id}", status_code=204)
def delete_studio(image_id: int):
    if not db.delete_studio_image(image_id):
        raise HTTPException(status_code=404, detail="Studio image not found")


class AudioRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    voice_provider: Literal["openai", "elevenlabs"]
    voice_id: str = Field(min_length=1, max_length=100)


@app.get("/audio")
def list_audio():
    return [_scene_with_signed_url(c) for c in db.list_audio_clips()]


@app.post("/audio", dependencies=[Depends(require_api_key)])
def create_audio(body: AudioRequest):
    # OpenAI voices must be one of the fixed set; ElevenLabs accepts ANY id so
    # users can import their own cloned voice by its Voice ID.
    if body.voice_provider == "openai":
        valid = {v["id"] for v in available_voices().get("openai", [])}
        if body.voice_id not in valid:
            raise HTTPException(status_code=400, detail=f"Unknown OpenAI voice '{body.voice_id}'.")
    with generation_slot(0, "audio"):
        try:
            result = generate_audio(body.text, body.voice_provider, body.voice_id)
        except HTTPException:
            raise
        except Exception:
            logger.exception("Audio generation failed")
            raise HTTPException(status_code=502, detail="Audio generation failed. Please try again.")
    return _scene_with_signed_url(db.create_audio_clip(
        text=body.text,
        voice=result.get("voice"),
        url=result["url"],
        sha256=result["sha256"],
        mime_type=result["mime_type"],
        model=result.get("voice"),
        cost_usd=result.get("cost_usd"),
        manifest_verified=result["manifest_verified"],
    ))


@app.delete("/audio/{clip_id}", status_code=204)
def delete_audio(clip_id: int):
    if not db.delete_audio_clip(clip_id):
        raise HTTPException(status_code=404, detail="Audio clip not found")


class VideoRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)
    model: str = DEFAULT_VIDEO_MODEL
    character_id: int | None = None
    duration: int = Field(default=5, ge=3, le=10)
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"


def _run_video(video_id: int, prompt: str, model: str, reference: dict | None,
               duration: int, aspect_ratio: str) -> None:
    """Background worker — video generation takes minutes, so it runs off the
    request thread and the row's status is polled by the client."""
    try:
        result = generate_video(prompt, model, reference, duration, aspect_ratio)
        db.finish_video(
            video_id, status="done", url=result["url"],
            original_url=result.get("original_url"), sha256=result["sha256"],
            mime_type=result["mime_type"], cost_usd=result.get("cost_usd"),
            manifest_verified=result["manifest_verified"],
        )
    except Exception as exc:
        logger.exception("Video %s failed", video_id)
        db.finish_video(video_id, status="error", error="Video generation failed. Please try again.")
    finally:
        _release_slot(0, "video")


def _video_with_signed_url(video: dict) -> dict:
    try:
        video["signed_url"] = presign_asset_url(video["url"]) if video.get("url") else None
    except Exception:
        video["signed_url"] = None
    return video


@app.get("/videos")
def list_videos():
    return [_video_with_signed_url(v) for v in db.list_videos()]


@app.get("/videos/{video_id}")
def get_video(video_id: int):
    video = db.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return _video_with_signed_url(video)


@app.post("/videos", dependencies=[Depends(require_api_key)])
def create_video(body: VideoRequest):
    if body.model not in {m["slug"] for m in available_video_models()}:
        raise HTTPException(
            status_code=400,
            detail=f"Video model '{body.model}' is not available (GMI_API_KEY not configured?).",
        )
    meta = VIDEO_MODELS[body.model]
    reference, character_id, character_name, kind = None, None, None, "text"
    if meta["needs_image"]:
        if body.character_id is None:
            raise HTTPException(status_code=400, detail="This model animates a character — pick one.")
        character = db.get_character(body.character_id)
        if character is None:
            raise HTTPException(status_code=404, detail="Character not found")
        refs = identity_references(character)
        if not refs:
            raise HTTPException(
                status_code=400,
                detail=f"'{character['name']}' has no portrait to animate. Generate one first.",
            )
        reference = refs[0]
        character_id, character_name, kind = character["id"], character["name"], "character"

    _acquire_slot(0, "video")
    try:
        video = db.create_video(
            character_id=character_id, character_name=character_name, kind=kind,
            prompt=body.prompt, model=body.model, duration=body.duration,
            aspect_ratio=body.aspect_ratio,
        )
    except Exception:
        _release_slot(0, "video")
        raise
    thread = threading.Thread(
        target=_run_video,
        args=(video["id"], body.prompt, body.model, reference, body.duration, body.aspect_ratio),
        daemon=True,
    )
    thread.start()
    return _video_with_signed_url(video)


@app.delete("/videos/{video_id}", status_code=204)
def delete_video(video_id: int):
    if not db.delete_video(video_id):
        raise HTTPException(status_code=404, detail="Video not found")
