import logging
import threading
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Literal

import time

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import db
from app.config import (
    CORS_ORIGINS,
    GENERATE_API_KEY,
    MAX_KEYLESS_BATCH,
    RATE_GLOBAL_PER_DAY,
    RATE_IP_PER_HOUR,
    RATE_VIDEO_PER_DAY,
    VIDEO_UNITS,
)
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
    generate_dialogue_audio,
    generate_motion_comic,
    generate_scene,
    generate_script,
    generate_studio_image,
    generate_video,
    generate_lipsync,
    mux_video_with_audio,
)
from app.storage import presign_asset_url, upload_reference_image, with_signed_url

logger = logging.getLogger("character_vault")


def _is_owner(x_api_key: str) -> bool:
    """The GENERATE_API_KEY still exists — but now as an OWNER bypass for
    unlimited generation, not a wall. Anyone else generates rate-limited."""
    return bool(GENERATE_API_KEY) and x_api_key == GENERATE_API_KEY


class RateLimiter:
    """In-memory rate limiter. Keyless generation runs on the owner's provider
    keys, so cap it: per-IP hourly units, a global daily unit budget, and a
    hard global daily video count. Counters live in fixed time buckets and old
    buckets are pruned lazily. Resets on restart — fine for this scale."""

    def __init__(self):
        self._lock = threading.Lock()
        self._ip_hour: dict = {}   # (ip, hour_bucket) -> units
        self._day: dict = {}       # (scope, day_bucket) -> count/units

    def allow(self, ip: str, kind: str, units: int = 1) -> bool:
        now = time.time()
        hour, day = int(now // 3600), int(now // 86400)
        with self._lock:
            self._prune(hour, day)
            ip_used = self._ip_hour.get((ip, hour), 0)
            global_used = self._day.get(("all", day), 0)
            video_used = self._day.get(("video", day), 0)
            if ip_used + units > RATE_IP_PER_HOUR:
                return False
            if global_used + units > RATE_GLOBAL_PER_DAY:
                return False
            if kind == "video" and video_used + 1 > RATE_VIDEO_PER_DAY:
                return False
            self._ip_hour[(ip, hour)] = ip_used + units
            self._day[("all", day)] = global_used + units
            if kind == "video":
                self._day[("video", day)] = video_used + 1
            return True

    def _prune(self, hour: int, day: int) -> None:
        for key in [k for k in self._ip_hour if k[1] != hour]:
            del self._ip_hour[key]
        for key in [k for k in self._day if k[1] != day]:
            del self._day[key]

    def reset(self) -> None:
        with self._lock:
            self._ip_hour.clear()
            self._day.clear()


rate_limiter = RateLimiter()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate(request: Request, x_api_key: str, kind: str, units: int = 1) -> None:
    if _is_owner(x_api_key):
        return
    if not rate_limiter.allow(_client_ip(request), kind, units):
        raise HTTPException(
            status_code=429,
            detail="The shared free limit is reached for now — please try again later, "
                   "or add the owner API key for unlimited generation.",
        )


def generation_guard(kind: str, units: int = 1):
    def dep(request: Request, x_api_key: str = Header(default="")):
        enforce_rate(request, x_api_key, kind, units)
    return dep


def require_workspace(x_workspace_id: str = Header(default="")) -> str:
    """Every data request is scoped to a workspace (tenant). The workspace id is
    a bearer token the client stores; unknown/missing → 401. Data of other
    workspaces is never visible or reachable, even by guessing row IDs."""
    workspace = db.get_workspace(x_workspace_id) if x_workspace_id else None
    if workspace is None:
        raise HTTPException(
            status_code=401,
            detail="Missing or unknown workspace. Create a workspace or enter your workspace token.",
        )
    return workspace["id"]


_inflight_lock = threading.Lock()
_inflight: set[tuple] = set()


def _acquire_slot(scope, kind: str) -> None:
    key = (scope, kind)
    with _inflight_lock:
        if key in _inflight:
            raise HTTPException(
                status_code=409,
                detail="A generation is already running here. Please wait for it to finish.",
            )
        _inflight.add(key)


def _release_slot(scope, kind: str) -> None:
    with _inflight_lock:
        _inflight.discard((scope, kind))


@contextmanager
def generation_slot(scope, kind: str):
    """One paid generation per scope+kind at a time — a duplicate request
    (double-click, impatient retry) is rejected instead of silently billed
    twice. `scope` is a character id for per-character ops, or a workspace id
    for the shared studio/scene/audio/video pipelines."""
    _acquire_slot(scope, kind)
    try:
        yield
    finally:
        _release_slot(scope, kind)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Loomina", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def revalidate_frontend(request: Request, call_next):
    """Force the browser to revalidate the HTML/JS/CSS on every load so a
    freshly deployed build can't be served as a stale mix of old + new files
    (which breaks init and leaves half the UI dead). StaticFiles still sends
    ETag/Last-Modified, so unchanged files return a cheap 304."""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


class CharacterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    personality: str | None = Field(default=None, max_length=1000)
    purpose: str | None = Field(default=None, max_length=500)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    voice_provider: Literal["openai", "elevenlabs"] | None = None
    voice_id: str | None = Field(default=None, max_length=100)


class CharacterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    personality: str | None = Field(default=None, max_length=1000)
    purpose: str | None = Field(default=None, max_length=500)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    voice_provider: Literal["openai", "elevenlabs"] | None = None
    voice_id: str | None = Field(default=None, max_length=100)


def _apply_voice(workspace: str, character_id: int, provider: str | None, voice_id: str | None) -> None:
    """The character's voice is fixed on the character (set at creation, edited
    only in the profile). OpenAI voices are validated against the catalog;
    ElevenLabs accepts any id (own cloned voice)."""
    if not provider or not voice_id:
        return
    if provider == "openai":
        valid = {v["id"] for v in available_voices().get("openai", [])}
        if voice_id not in valid:
            raise HTTPException(status_code=400, detail=f"Unknown OpenAI voice '{voice_id}'.")
    db.set_character_voice(workspace, character_id, provider, voice_id)


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


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)


@app.post("/workspaces")
def create_workspace(body: WorkspaceCreate):
    """Create a new tenant. The returned id is the token the client stores and
    sends as X-Workspace-Id on every request."""
    return db.create_workspace(body.name)


@app.get("/workspaces/current")
def current_workspace(workspace: str = Depends(require_workspace)):
    """Validate a stored workspace token and return its name (used on load)."""
    return db.get_workspace(workspace)


@app.post("/characters")
def create_character(body: CharacterCreate, workspace: str = Depends(require_workspace)):
    character = db.create_character(
        workspace, body.name, body.description, body.personality, body.purpose, body.seed
    )
    _apply_voice(workspace, character["id"], body.voice_provider, body.voice_id)
    return db.get_character(workspace, character["id"])


@app.patch("/characters/{character_id}")
def update_character(character_id: int, body: CharacterUpdate, workspace: str = Depends(require_workspace)):
    fields = body.model_dump(exclude_unset=True)
    fields.pop("voice_provider", None)
    fields.pop("voice_id", None)
    character = db.update_character(workspace, character_id, fields)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    _apply_voice(workspace, character_id, body.voice_provider, body.voice_id)
    character = db.get_character(workspace, character_id)
    character["assets"] = [with_signed_url(a) for a in character["assets"]]
    return character


@app.get("/characters")
def list_characters(workspace: str = Depends(require_workspace)):
    characters = db.list_characters(workspace)
    for character in characters:
        source = character.pop("thumbnail_source_url", None)
        character["thumbnail_url"] = presign_asset_url(source) if source else None
    return characters


@app.get("/characters/{character_id}")
def get_character(character_id: int, workspace: str = Depends(require_workspace)):
    character = db.get_character(workspace, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    character["assets"] = [with_signed_url(a) for a in character["assets"]]
    return character


MAX_UPLOAD_BYTES = 12 * 1024 * 1024
ALLOWED_UPLOAD_TYPES = {"image/png", "image/jpeg", "image/webp"}


@app.post("/characters/{character_id}/reference", dependencies=[Depends(generation_guard("image", 1))])
async def upload_reference(character_id: int, file: UploadFile = File(...),
                           workspace: str = Depends(require_workspace)):
    character = db.get_character(workspace, character_id)
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
def set_character_voice(character_id: int, body: VoiceAssign, workspace: str = Depends(require_workspace)):
    valid_ids = {v["id"] for v in available_voices().get(body.voice_provider, [])}
    if body.voice_id not in valid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Voice '{body.voice_id}' is not available for provider '{body.voice_provider}'.",
        )
    character = db.set_character_voice(workspace, character_id, body.voice_provider, body.voice_id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


@app.delete("/characters/{character_id}", status_code=204)
def delete_character(character_id: int, workspace: str = Depends(require_workspace)):
    if not db.delete_character(workspace, character_id):
        raise HTTPException(status_code=404, detail="Character not found")


@app.get("/assets")
def list_assets(kind: str | None = Query(default=None, pattern="^(image|voice)$"),
                workspace: str = Depends(require_workspace)):
    return [with_signed_url(a) for a in db.list_assets(workspace, kind)]


@app.delete("/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: int, workspace: str = Depends(require_workspace)):
    if not db.delete_asset(workspace, asset_id):
        raise HTTPException(status_code=404, detail="Asset not found")


@app.post("/characters/{character_id}/generate/image", dependencies=[Depends(generation_guard("image", 1))])
def generate_image(character_id: int, body: PortraitRequest, workspace: str = Depends(require_workspace)):
    character = db.get_character(workspace, character_id)
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


@app.post("/characters/{character_id}/generate/batch")
def generate_batch(character_id: int, body: BatchRequest, request: Request,
                   workspace: str = Depends(require_workspace),
                   x_api_key: str = Header(default="")):
    character = db.get_character(workspace, character_id)
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
    # Keyless callers get a smaller batch cap; the owner key lifts it.
    if not _is_owner(x_api_key) and len(prompts) > MAX_KEYLESS_BATCH:
        prompts = prompts[:MAX_KEYLESS_BATCH]
    # Rate-limit the whole batch by its frame count (owner bypasses).
    enforce_rate(request, x_api_key, "image", units=len(prompts))

    unit = per_image_cost(body.model, body.quality)
    estimate = round(unit * len(prompts), 4) if unit is not None else None
    references = identity_references(character) if body.use_identity else []

    _acquire_slot(character_id, "image")
    try:
        job = db.create_batch(
            workspace_id=workspace, character_id=character_id, mode=body.mode, prompt=body.prompt,
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


def _owned_batch(batch_id: int, workspace: str) -> dict:
    job = db.get_batch(batch_id)
    if job is None or job.get("workspace_id") != workspace:
        raise HTTPException(status_code=404, detail="Batch not found")
    return job


@app.get("/batches/{batch_id}")
def get_batch(batch_id: int, workspace: str = Depends(require_workspace)):
    return _owned_batch(batch_id, workspace)


@app.post("/batches/{batch_id}/cancel")
def cancel_batch(batch_id: int, workspace: str = Depends(require_workspace)):
    job = _owned_batch(batch_id, workspace)
    if job["status"] == "running":
        db.finish_batch(batch_id, "cancelled")
    return db.get_batch(batch_id)


@app.post("/characters/{character_id}/generate/voice", dependencies=[Depends(generation_guard("voice", 1))])
def generate_voice(character_id: int, body: VoiceLineRequest, workspace: str = Depends(require_workspace)):
    character = db.get_character(workspace, character_id)
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
def list_scenes(workspace: str = Depends(require_workspace)):
    return [_scene_with_signed_url(s) for s in db.list_scenes(workspace)]


@app.post("/scenes", dependencies=[Depends(generation_guard("scene", 4))])
def create_scene(body: SceneRequest, workspace: str = Depends(require_workspace)):
    references, descriptors, names, ids = [], [], [], []
    for cid in body.character_ids:
        character = db.get_character(workspace, cid)
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

    with generation_slot(workspace, "scene"):
        try:
            result = generate_scene(body.prompt, references, descriptors, body.disclosure)
        except HTTPException:
            raise
        except Exception:
            logger.exception("Scene generation failed for %s", ids)
            raise HTTPException(status_code=502, detail="Scene generation failed. Please try again.")

    return _scene_with_signed_url(db.create_scene(
        workspace_id=workspace,
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
def delete_scene(scene_id: int, workspace: str = Depends(require_workspace)):
    if not db.delete_scene(workspace, scene_id):
        raise HTTPException(status_code=404, detail="Scene not found")


class StudioRequest(BaseModel):
    kind: Literal["background", "photo-art"]
    prompt: str = Field(min_length=1, max_length=4000)
    disclosure: Literal["visible", "invisible"] = "invisible"
    quality: Literal["draft", "final"] = "draft"
    model: str = DEFAULT_IMAGE_MODEL


@app.get("/studio")
def list_studio(kind: str | None = Query(default=None, pattern="^(background|photo-art)$"),
                workspace: str = Depends(require_workspace)):
    return [_scene_with_signed_url(s) for s in db.list_studio_images(workspace, kind)]


@app.post("/studio", dependencies=[Depends(generation_guard("image", 1))])
def create_studio(body: StudioRequest, workspace: str = Depends(require_workspace)):
    if body.model not in {m["slug"] for m in available_image_models()}:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{body.model}' is not available. Configure its API key first.",
        )
    with generation_slot(workspace, "studio"):
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
        workspace_id=workspace,
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
def delete_studio(image_id: int, workspace: str = Depends(require_workspace)):
    if not db.delete_studio_image(workspace, image_id):
        raise HTTPException(status_code=404, detail="Studio image not found")


class AudioRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    voice_provider: Literal["openai", "elevenlabs"]
    voice_id: str = Field(min_length=1, max_length=100)


@app.get("/audio")
def list_audio(workspace: str = Depends(require_workspace)):
    return [_scene_with_signed_url(c) for c in db.list_audio_clips(workspace)]


@app.post("/audio", dependencies=[Depends(generation_guard("voice", 1))])
def create_audio(body: AudioRequest, workspace: str = Depends(require_workspace)):
    # OpenAI voices must be one of the fixed set; ElevenLabs accepts ANY id so
    # users can import their own cloned voice by its Voice ID.
    if body.voice_provider == "openai":
        valid = {v["id"] for v in available_voices().get("openai", [])}
        if body.voice_id not in valid:
            raise HTTPException(status_code=400, detail=f"Unknown OpenAI voice '{body.voice_id}'.")
    with generation_slot(workspace, "audio"):
        try:
            result = generate_audio(body.text, body.voice_provider, body.voice_id)
        except HTTPException:
            raise
        except Exception:
            logger.exception("Audio generation failed")
            raise HTTPException(status_code=502, detail="Audio generation failed. Please try again.")
    return _scene_with_signed_url(db.create_audio_clip(
        workspace_id=workspace,
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
def delete_audio(clip_id: int, workspace: str = Depends(require_workspace)):
    if not db.delete_audio_clip(workspace, clip_id):
        raise HTTPException(status_code=404, detail="Audio clip not found")


class DialogueTurn(BaseModel):
    character_id: int
    text: str = Field(min_length=1, max_length=500)


class DialogueRequest(BaseModel):
    # Ordered speaking turns — a character can appear more than once (a
    # back-and-forth conversation), so this isn't just "pick N characters",
    # it's the actual script.
    turns: list[DialogueTurn] = Field(min_length=2, max_length=20)


@app.get("/audio/dialogue")
def list_dialogues(workspace: str = Depends(require_workspace)):
    return [_scene_with_signed_url(d) for d in db.list_dialogues(workspace)]


@app.post("/audio/dialogue")
def create_dialogue(body: DialogueRequest, request: Request,
                    workspace: str = Depends(require_workspace),
                    x_api_key: str = Header(default="")):
    ids = list(dict.fromkeys(t.character_id for t in body.turns))  # first-appearance order
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="A dialogue needs at least two characters.")
    if len(ids) > 6:
        raise HTTPException(status_code=400, detail="Pick at most six characters.")
    if not _is_owner(x_api_key) and len(body.turns) > MAX_KEYLESS_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Keyless dialogues are capped at {MAX_KEYLESS_BATCH} lines — shorten the script "
                   "or add the owner API key.",
        )

    characters = {}
    for cid in ids:
        character = db.get_character(workspace, cid)
        if character is None:
            raise HTTPException(status_code=404, detail=f"Character {cid} not found")
        if not character.get("voice_id"):
            raise HTTPException(
                status_code=400,
                detail=f"'{character['name']}' has no voice set — give it one in the profile first.",
            )
        characters[cid] = character

    enforce_rate(request, x_api_key, "voice", units=len(body.turns))

    turns = [
        {
            "character_id": t.character_id,
            "character_name": characters[t.character_id]["name"],
            "voice_provider": characters[t.character_id].get("voice_provider"),
            "voice_id": characters[t.character_id].get("voice_id"),
            "text": t.text,
        }
        for t in body.turns
    ]

    with generation_slot(workspace, "dialogue"):
        try:
            result = generate_dialogue_audio(turns)
        except HTTPException:
            raise
        except Exception:
            logger.exception("Dialogue generation failed")
            raise HTTPException(status_code=502, detail="Dialogue generation failed. Please try again.")

    return _scene_with_signed_url(db.create_dialogue(
        workspace_id=workspace,
        script=result["script"],
        url=result["url"],
        sha256=result["sha256"],
        mime_type=result["mime_type"],
        cost_usd=result.get("cost_usd"),
        manifest_verified=result["manifest_verified"],
        participant_ids=ids,
        participant_names=[characters[cid]["name"] for cid in ids],
    ))


@app.delete("/audio/dialogue/{dialogue_id}", status_code=204)
def delete_dialogue(dialogue_id: int, workspace: str = Depends(require_workspace)):
    if not db.delete_dialogue(workspace, dialogue_id):
        raise HTTPException(status_code=404, detail="Dialogue not found")


class VideoRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)
    model: str = DEFAULT_VIDEO_MODEL
    character_id: int | None = None
    # Animate an existing multi-character scene image instead of a single
    # character's portrait — several characters in one clip. Mutually
    # exclusive with character_id; no lip-sync is attempted for these (no
    # single fixed voice to sync to a face), so speech is ignored.
    scene_id: int | None = None
    duration: int = Field(default=5, ge=3, le=10)
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    # Optional line for the character to SPEAK — turns a silent clip into a
    # talking one (their fixed voice, muxed onto the video).
    speech: str | None = Field(default=None, max_length=400)


def _run_video(scope, video_id: int, prompt: str, model: str, reference: dict | None,
               duration: int, aspect_ratio: str, character_id: int | None = None,
               speech: str | None = None, voice_provider: str | None = None,
               voice_id: str | None = None) -> None:
    """Background worker — video generation takes minutes, so it runs off the
    request thread and the row's status is polled by the client. If `speech`
    is set, the character's fixed voice is generated and muxed onto the clip so
    the character actually talks."""
    try:
        result = generate_video(prompt, model, reference, duration, aspect_ratio)
        url, sha, mime = result["url"], result["sha256"], result["mime_type"]
        if speech and speech.strip():
            try:
                voice = generate_character_voice_line(
                    character_id or 0, speech.strip(), voice_provider, voice_id,
                )
                try:
                    # Pipeline 2: real audio-driven lip-sync (kling-lip-sync).
                    talking = generate_lipsync(result["url"], voice["url"])
                except Exception:
                    # Robust fallback: audio muxed onto the motion clip.
                    logger.exception("Lip-sync failed for video %s — falling back to mux", video_id)
                    talking = mux_video_with_audio(result["url"], voice["url"])
                url, sha, mime = talking["url"], talking["sha256"], talking["mime_type"]
            except Exception:
                logger.exception("Adding speech to video %s failed — keeping silent clip", video_id)
        db.finish_video(
            video_id, status="done", url=url, original_url=result.get("original_url"),
            sha256=sha, mime_type=mime, cost_usd=result.get("cost_usd"),
            manifest_verified=result["manifest_verified"],
        )
    except Exception:
        logger.exception("Video %s failed", video_id)
        db.finish_video(video_id, status="error", error="Video generation failed. Please try again.")
    finally:
        _release_slot(scope, "video")


def _video_with_signed_url(video: dict) -> dict:
    try:
        video["signed_url"] = presign_asset_url(video["url"]) if video.get("url") else None
    except Exception:
        video["signed_url"] = None
    return video


@app.get("/videos")
def list_videos(workspace: str = Depends(require_workspace)):
    return [_video_with_signed_url(v) for v in db.list_videos(workspace)]


@app.get("/videos/{video_id}")
def get_video(video_id: int, workspace: str = Depends(require_workspace)):
    video = db.get_video(workspace, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return _video_with_signed_url(video)


@app.post("/videos", dependencies=[Depends(generation_guard("video", VIDEO_UNITS))])
def create_video(body: VideoRequest, workspace: str = Depends(require_workspace)):
    if body.model not in {m["slug"] for m in available_video_models()}:
        raise HTTPException(
            status_code=400,
            detail=f"Video model '{body.model}' is not available (GMI_API_KEY not configured?).",
        )
    meta = VIDEO_MODELS[body.model]
    reference, character_id, character_name, kind = None, None, None, "text"
    voice_provider = voice_id = None
    speech = body.speech
    if meta["needs_image"]:
        if body.scene_id is not None:
            scene = db.get_scene(workspace, body.scene_id)
            if scene is None:
                raise HTTPException(status_code=404, detail="Scene not found")
            reference = {"url": scene.get("original_url") or scene["url"], "sha256": scene.get("sha256")}
            character_name = " + ".join(scene["participant_names"])
            kind = "scene"
            speech = None  # several characters, no single fixed voice to lip-sync to
        elif body.character_id is not None:
            character = db.get_character(workspace, body.character_id)
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
            voice_provider, voice_id = character.get("voice_provider"), character.get("voice_id")
        else:
            raise HTTPException(status_code=400, detail="This model animates a character or scene — pick one.")
    else:
        speech = None  # text-to-video has no character voice to speak with

    # For a talking clip, keep the base motion's mouth calm so lip-sync alone
    # drives the speech — otherwise the base clip "talks" too and the mouth
    # over-moves. (Display prompt stays as the user wrote it.)
    motion_prompt = body.prompt
    if speech and speech.strip():
        motion_prompt = (f"{body.prompt}. Keep the mouth relaxed and mostly closed with "
                         f"minimal lip movement; calm, steady expression, eyes on camera.")

    _acquire_slot(workspace, "video")
    try:
        video = db.create_video(
            workspace_id=workspace, character_id=character_id, character_name=character_name,
            kind=kind, prompt=body.prompt, model=body.model, duration=body.duration,
            aspect_ratio=body.aspect_ratio,
        )
    except Exception:
        _release_slot(workspace, "video")
        raise
    thread = threading.Thread(
        target=_run_video,
        args=(workspace, video["id"], motion_prompt, body.model, reference, body.duration,
              body.aspect_ratio, character_id, speech, voice_provider, voice_id),
        daemon=True,
    )
    thread.start()
    return _video_with_signed_url(video)


@app.delete("/videos/{video_id}", status_code=204)
def delete_video(video_id: int, workspace: str = Depends(require_workspace)):
    if not db.delete_video(workspace, video_id):
        raise HTTPException(status_code=404, detail="Video not found")


class MotionComicPanel(BaseModel):
    scene_id: int
    character_id: int
    text: str = Field(min_length=1, max_length=500)


class MotionComicRequest(BaseModel):
    # No GMI video call happens here at all — see generate_motion_comic's
    # docstring for why (kling-identify-face only ever finds one face, so
    # real multi-character lip-sync isn't achievable). Each panel is a still
    # scene image held on screen for exactly as long as its own line takes.
    panels: list[MotionComicPanel] = Field(min_length=2, max_length=12)


@app.post("/videos/motion-comic")
def create_motion_comic(body: MotionComicRequest, request: Request,
                        workspace: str = Depends(require_workspace),
                        x_api_key: str = Header(default="")):
    if not _is_owner(x_api_key) and len(body.panels) > MAX_KEYLESS_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Keyless motion comics are capped at {MAX_KEYLESS_BATCH} panels — shorten it "
                   "or add the owner API key.",
        )

    panels, char_names = [], []
    for p in body.panels:
        scene = db.get_scene(workspace, p.scene_id)
        if scene is None:
            raise HTTPException(status_code=404, detail=f"Scene {p.scene_id} not found")
        character = db.get_character(workspace, p.character_id)
        if character is None:
            raise HTTPException(status_code=404, detail=f"Character {p.character_id} not found")
        if not character.get("voice_id"):
            raise HTTPException(
                status_code=400,
                detail=f"'{character['name']}' has no voice set — give it one in the profile first.",
            )
        char_names.append(character["name"])
        panels.append({
            "image_url": scene.get("original_url") or scene["url"],
            "character_id": p.character_id,
            "character_name": character["name"],
            "voice_provider": character.get("voice_provider"),
            "voice_id": character.get("voice_id"),
            "text": p.text,
        })

    enforce_rate(request, x_api_key, "voice", units=len(body.panels))

    video = db.create_video(
        workspace_id=workspace, character_id=None,
        character_name=" + ".join(dict.fromkeys(char_names)),
        kind="motion_comic", prompt=f"{len(body.panels)}-panel motion comic",
        model="motion-comic", duration=None, aspect_ratio=None,
    )
    with generation_slot(workspace, "motion_comic"):
        try:
            result = generate_motion_comic(panels)
        except Exception:
            logger.exception("Motion comic generation failed")
            db.finish_video(video["id"], status="error",
                            error="Motion comic generation failed. Please try again.")
            raise HTTPException(status_code=502, detail="Motion comic generation failed. Please try again.")

    db.finish_video(
        video["id"], status="done", url=result["url"], original_url=result["url"],
        sha256=result["sha256"], mime_type=result["mime_type"], cost_usd=result.get("cost_usd"),
        manifest_verified=result["manifest_verified"], duration=round(result["duration"]),
        script=result["script"],
    )
    return _video_with_signed_url(db.get_video(workspace, video["id"]))


class ScriptRequest(BaseModel):
    idea: str = Field(min_length=1, max_length=2000)
    format: Literal["story", "video", "manga", "dialogue"] = "story"
    length: Literal["short", "medium", "long"] = "medium"
    character_ids: list[int] = Field(default_factory=list, max_length=6)


@app.get("/scripts")
def list_scripts(workspace: str = Depends(require_workspace)):
    return db.list_scripts(workspace)


@app.post("/scripts", dependencies=[Depends(generation_guard("script", 1))])
def create_script(body: ScriptRequest, workspace: str = Depends(require_workspace)):
    names = []
    for cid in body.character_ids:
        character = db.get_character(workspace, cid)
        if character:
            names.append(character["name"])
    with generation_slot(workspace, "script"):
        try:
            content = generate_script(body.idea, body.format, body.length, names or None)
        except HTTPException:
            raise
        except Exception:
            logger.exception("Script generation failed")
            raise HTTPException(status_code=502, detail="Script generation failed. Please try again.")
    if not content:
        raise HTTPException(status_code=502, detail="The script came back empty. Please try again.")
    return db.create_script(workspace, body.idea, body.format, content)


@app.delete("/scripts/{script_id}", status_code=204)
def delete_script(script_id: int, workspace: str = Depends(require_workspace)):
    if not db.delete_script(workspace, script_id):
        raise HTTPException(status_code=404, detail="Script not found")
