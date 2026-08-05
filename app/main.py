import logging
import threading
import uuid
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Literal

import time

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import db
from app.config import (
    B2_BUCKET_NAME,
    B2_REGION,
    CORS_ORIGINS,
    GENERATE_API_KEY,
    MAX_KEYLESS_BATCH,
    MAX_WORKSPACES_PER_IP,
    OPENAI_API_KEY,
    RATE_GLOBAL_PER_DAY,
    RATE_IP_PER_HOUR,
    RATE_VIDEO_PER_DAY,
    VIDEO_UNITS,
    WORKSPACE_UNIT_QUOTA,
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
    extract_poster_frame,
    mux_video_with_audio,
    overlay_video,
    DEFAULT_SEQUENCE_RESOLUTION,
    SEQUENCE_ASPECTS,
    SEQUENCE_LOOKS,
    SEQUENCE_MAX_FADE,
    SEQUENCE_MOTIONS,
    SEQUENCE_RESOLUTIONS,
    SEQUENCE_TITLE_STYLES,
    SEQUENCE_TRANSITIONS,
    ffmpeg_has_drawtext,
    ffmpeg_has_filter,
    plan_sequence,
    probe_media,
    read_embedded_manifest,
    render_sequence,
)
from app.storage import (
    is_bucket_url,
    presign_asset_url,
    upload_bytes,
    upload_path,
    upload_reference_image,
    with_signed_url,
)

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


def enforce_quota(request: Request, x_api_key: str, workspace_id: str, units: int) -> None:
    """Draw a run's cost from the workspace's lifetime budget.

    This — not the RateLimiter above — is what actually protects the account
    behind a public link: the limiter lives in RAM and hands everyone fresh
    budget on every restart, while this budget is persisted per workspace.

    Units are drawn *before* the work runs, so anything that fails afterwards
    has to hand them back: `refund_quota_on_failure` covers work that finishes
    inside the request, and the video/batch workers refund from their thread.
    """
    if _is_owner(x_api_key):
        return
    if not db.consume_units(workspace_id, units):
        raise HTTPException(
            status_code=429,
            detail="This workspace has used up its free generation budget — it covers "
                   "one full run through the app. Thanks for trying it out!",
        )
    request.state.quota_workspace = workspace_id
    request.state.quota_units = units


def generation_guard(kind: str, units: int = 1):
    def dep(request: Request, x_api_key: str = Header(default=""),
            x_workspace_id: str = Header(default="")):
        enforce_rate(request, x_api_key, kind, units)
        enforce_quota(request, x_api_key, x_workspace_id, units)
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


def _refund_pending_quota(request: Request) -> None:
    """Hand back units the guard drew for a run that produced nothing.
    Idempotent — the pending amount is cleared before the refund lands."""
    units = getattr(request.state, "quota_units", 0)
    workspace = getattr(request.state, "quota_workspace", "")
    if units and workspace:
        request.state.quota_units = 0
        db.refund_units(workspace, units)


@app.middleware("http")
async def refund_quota_on_failure(request: Request, call_next):
    """Return budget whenever a generation request ends in an error.

    Units are drawn before the endpoint body runs, so without this a rejected
    duplicate run (409 from the in-flight guard) or a provider outage would
    quietly eat part of a visitor's single-run budget. Any non-2xx means no
    asset was stored, so the whole amount goes back.

    Only covers work that completes inside the request — video and batch
    return early and refund from the thread that does the real work.
    """
    try:
        response = await call_next(request)
    except Exception:
        _refund_pending_quota(request)
        raise
    if response.status_code >= 400:
        _refund_pending_quota(request)
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
    voice_provider: Literal["openai", "gmi"] | None = None
    voice_id: str | None = Field(default=None, max_length=100)


class CharacterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    personality: str | None = Field(default=None, max_length=1000)
    purpose: str | None = Field(default=None, max_length=500)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    voice_provider: Literal["openai", "gmi"] | None = None
    voice_id: str | None = Field(default=None, max_length=100)


def _apply_voice(workspace: str, character_id: int, provider: str | None, voice_id: str | None) -> None:
    """The character's voice is fixed on the character (set at creation, edited
    only in the profile). Both providers now use a fixed catalog — GMI's
    Inworld voices replaced ElevenLabs' custom-voice-import-by-id flow."""
    if not provider or not voice_id:
        return
    valid = {v["id"] for v in available_voices().get(provider, [])}
    if voice_id not in valid:
        raise HTTPException(status_code=400, detail=f"Unknown {provider} voice '{voice_id}'.")
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
    voice_provider: Literal["openai", "gmi"]
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
        "sequence": {
            "aspect_ratios": list(SEQUENCE_ASPECTS),
            "resolutions": list(SEQUENCE_RESOLUTIONS),
            "transitions": list(SEQUENCE_TRANSITIONS),
            "looks": list(SEQUENCE_LOOKS),
            "motions": list(SEQUENCE_MOTIONS),
            "title_styles": list(SEQUENCE_TITLE_STYLES),
            "max_clips": MAX_SEQUENCE_CLIPS,
            "max_seconds": MAX_SEQUENCE_SECONDS,
            "max_audio_tracks": MAX_AUDIO_TRACKS,
            "auto_cut": bool(OPENAI_API_KEY),
        },
        # Reported, not acted on. drawtext: the timeline draws every piece of
        # text with Pillow precisely so it does not depend on it (see
        # pipelines.ffmpeg_has_drawtext). sidechaincompress: without it a
        # soundtrack cannot duck under speech and is laid at a static level
        # instead — the mix still works, it just doesn't step back. Both are
        # surfaced so the deployed image's build is inspectable, not assumed.
        "ffmpeg": {
            "drawtext": ffmpeg_has_drawtext(),
            "sidechaincompress": ffmpeg_has_filter("sidechaincompress"),
        },
    }


@app.get("/voices")
def voices():
    return available_voices()


@app.get("/assets/proxy")
def proxy_asset(url: str, workspace: str = Depends(require_workspace)):
    """Same-origin passthrough for a signed B2 asset URL. <img> tags render
    cross-origin images fine, but drawing one onto a <canvas> element taints
    it unless the response carries CORS headers — B2 sends none, and adding
    bucket-level CORS rules is an out-of-repo dashboard change. Proxying
    through our own origin sidesteps that for the Canvas editor with zero
    B2-side configuration. Restricted to our own bucket's host+path so this
    can't become an open SSRF relay for arbitrary URLs."""
    import httpx
    from urllib.parse import urlparse

    parsed = urlparse(url)
    expected_host = f"s3.{B2_REGION}.backblazeb2.com"
    if parsed.scheme != "https" or parsed.netloc != expected_host or not parsed.path.startswith(f"/{B2_BUCKET_NAME}/"):
        raise HTTPException(status_code=400, detail="Only vault asset URLs can be proxied.")
    resp = httpx.get(url, timeout=30)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Could not fetch the asset.")
    return Response(content=resp.content, media_type=resp.headers.get("content-type", "application/octet-stream"))


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)


def _workspace_public(ws: dict) -> dict:
    """Client-facing shape of a workspace. Deliberately drops created_ip and
    exposes the budget as a remaining count, which is what the UI shows."""
    used, quota = ws.get("units_used") or 0, ws.get("units_quota") or 0
    return {
        "id": ws["id"],
        "name": ws["name"],
        "created_at": ws["created_at"],
        "units_used": used,
        "units_quota": quota,
        "units_remaining": max(0, quota - used),
    }


@app.post("/workspaces")
def create_workspace(body: WorkspaceCreate, request: Request,
                     x_api_key: str = Header(default="")):
    """Create a new tenant. The returned id is the token the client stores and
    sends as X-Workspace-Id on every request.

    On a public link each workspace carries a fixed generation budget, and one
    IP may only mint a few of them — enough that colleagues behind a shared
    corporate NAT each get their own, few enough that a single visitor can't
    mint fresh budget at will. The owner key skips the cap entirely.
    """
    if _is_owner(x_api_key):
        return _workspace_public(db.create_workspace(body.name))
    ip = _client_ip(request)
    if db.count_workspaces_for_ip(ip) >= MAX_WORKSPACES_PER_IP:
        raise HTTPException(
            status_code=429,
            detail="This network has already created the maximum number of demo "
                   "workspaces. Reopen an existing one with its token.",
        )
    return _workspace_public(
        db.create_workspace(body.name, created_ip=ip, units_quota=WORKSPACE_UNIT_QUOTA)
    )


@app.get("/workspaces/current")
def current_workspace(workspace: str = Depends(require_workspace)):
    """Validate a stored workspace token and return its name plus how much of
    the free budget is left (used on load, and after every generation)."""
    ws = db.get_workspace(workspace)
    if ws is None:
        raise HTTPException(status_code=401, detail="Unknown workspace.")
    return _workspace_public(ws)


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
        seed=result.get("seed"),
    ))


def _run_batch(job_id: int, character_id: int, prompts: list[str], references: list[dict],
               body: BatchRequest, personality: str | None, base_seed: int | None,
               workspace: str = "", quota_units: int = 0) -> None:
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
                    model=result.get("model"), batch_id=job_id, seed=result.get("seed"),
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
        # The whole batch was charged up front. Give back every frame that
        # never became an image — failed ones, and the tail of a cancelled
        # run — so stopping a runaway batch actually returns the budget.
        if quota_units and workspace and final:
            unused = max(0, len(prompts) - (final["completed"] or 0))
            if unused:
                db.refund_units(workspace, unused)
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
    # Batch can't use generation_guard: the cost is only known here, once the
    # prompt list exists. Draw it explicitly — otherwise a visitor generates
    # ten frames per call without ever touching their workspace budget.
    enforce_quota(request, x_api_key, workspace, units=len(prompts))
    drawn_units = getattr(request.state, "quota_units", 0)

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
        kwargs={"workspace": workspace, "quota_units": drawn_units},
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


MAX_CANVAS_EXPORT_BYTES = 20 * 1024 * 1024


class CanvasExportRequest(BaseModel):
    image_base64: str = Field(min_length=1)
    visible_badge: bool = False


@app.post("/canvas/export")
def export_canvas(body: CanvasExportRequest, workspace: str = Depends(require_workspace)):
    """Flatten a Canvas editor composition (text/shapes over a background)
    into a Studio-gallery asset. No provider call happens here — it's local
    compositing on the client, not generation — so unlike every /generate/*
    endpoint this deliberately has no generation_guard/rate limit, and
    manifest_verified always stays False: nothing here ran through a
    genblaze Pipeline, so there's no C2PA manifest to (honestly) claim as
    verified, same reasoning as the GMI voice-line raw-REST path."""
    import uuid as _uuid

    from app.disclosure import stamp_visible_badge

    if len(body.image_base64) > MAX_CANVAS_EXPORT_BYTES:
        raise HTTPException(status_code=400, detail="Composition is too large to export.")
    data = _decode_data_url(body.image_base64, "image_base64")

    if body.visible_badge:
        data = stamp_visible_badge(data)

    url, sha = upload_bytes(f"canvas/{_uuid.uuid4().hex}.png", data, "image/png")
    return _scene_with_signed_url(db.create_studio_image(
        workspace_id=workspace,
        kind="canvas",
        prompt="Canvas composition",
        url=url,
        original_url=url,
        sha256=sha,
        model="canvas-editor",
        quality=None,
        disclosure="visible" if body.visible_badge else None,
        cost_usd=0.0,
        manifest_verified=False,
    ))


class CanvasTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    category: str | None = Field(default=None, max_length=40)
    layout_json: str = Field(min_length=1)
    thumbnail_base64: str | None = None


def _decode_data_url(data_url: str, field_name: str) -> bytes:
    import base64
    import binascii

    header, _, encoded = data_url.partition(",")
    if not encoded or "base64" not in header:
        raise HTTPException(status_code=400, detail=f"{field_name} must be a data: URL.")
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail=f"Could not decode {field_name}.")


def _upload_canvas_thumbnail(data_url: str) -> tuple[str, str]:
    import uuid as _uuid

    data = _decode_data_url(data_url, "thumbnail_base64")
    return upload_bytes(f"canvas/thumbnails/{_uuid.uuid4().hex}.png", data, "image/png")


def _template_with_signed_thumbnail(template: dict) -> dict:
    template["signed_thumbnail_url"] = None
    if template.get("thumbnail_url"):
        try:
            template["signed_thumbnail_url"] = presign_asset_url(template["thumbnail_url"])
        except Exception:
            pass
    return template


# Templates are saved/reloaded editor layouts (Fabric's canvas.toJSON(), see
# CanvasTemplateRequest.layout_json), distinct from /canvas/export's flattened
# PNGs — a template stays editable and its image slots can be re-picked next
# time, an export is a finished asset. No rate limiting here either: like
# export, this is local persistence, not a provider call.

@app.post("/canvas/templates")
def create_canvas_template(body: CanvasTemplateRequest, workspace: str = Depends(require_workspace)):
    thumb_url = thumb_sha = None
    if body.thumbnail_base64:
        thumb_url, thumb_sha = _upload_canvas_thumbnail(body.thumbnail_base64)
    return _template_with_signed_thumbnail(db.create_canvas_template(
        workspace_id=workspace,
        name=body.name,
        category=body.category,
        layout_json=body.layout_json,
        thumbnail_url=thumb_url,
        thumbnail_sha256=thumb_sha,
    ))


@app.get("/canvas/templates")
def list_canvas_templates(workspace: str = Depends(require_workspace)):
    return [_template_with_signed_thumbnail(t) for t in db.list_canvas_templates(workspace)]


@app.get("/canvas/templates/{template_id}")
def get_canvas_template(template_id: int, workspace: str = Depends(require_workspace)):
    template = db.get_canvas_template(workspace, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return _template_with_signed_thumbnail(template)


@app.put("/canvas/templates/{template_id}")
def update_canvas_template(template_id: int, body: CanvasTemplateRequest, workspace: str = Depends(require_workspace)):
    thumb_url = thumb_sha = None
    if body.thumbnail_base64:
        thumb_url, thumb_sha = _upload_canvas_thumbnail(body.thumbnail_base64)
    else:
        existing = db.get_canvas_template(workspace, template_id)
        if existing:
            thumb_url, thumb_sha = existing["thumbnail_url"], existing["thumbnail_sha256"]
    updated = db.update_canvas_template(
        workspace_id=workspace,
        template_id=template_id,
        name=body.name,
        category=body.category,
        layout_json=body.layout_json,
        thumbnail_url=thumb_url,
        thumbnail_sha256=thumb_sha,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Template not found")
    return _template_with_signed_thumbnail(updated)


@app.delete("/canvas/templates/{template_id}", status_code=204)
def delete_canvas_template(template_id: int, workspace: str = Depends(require_workspace)):
    if not db.delete_canvas_template(workspace, template_id):
        raise HTTPException(status_code=404, detail="Template not found")


class AudioRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    voice_provider: Literal["openai", "gmi"]
    voice_id: str = Field(min_length=1, max_length=100)


@app.get("/audio")
def list_audio(workspace: str = Depends(require_workspace)):
    return [_scene_with_signed_url(c) for c in db.list_audio_clips(workspace)]


@app.post("/audio", dependencies=[Depends(generation_guard("voice", 1))])
def create_audio(body: AudioRequest, workspace: str = Depends(require_workspace)):
    valid = {v["id"] for v in available_voices().get(body.voice_provider, [])}
    if body.voice_id not in valid:
        raise HTTPException(status_code=400, detail=f"Unknown {body.voice_provider} voice '{body.voice_id}'.")
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
               voice_id: str | None = None, quota_units: int = 0) -> None:
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
        # A video is half the free budget — a provider outage must not end the
        # visitor's demo. `scope` is the workspace id for video runs.
        if quota_units:
            db.refund_units(scope, quota_units)
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
def create_video(body: VideoRequest, request: Request,
                 workspace: str = Depends(require_workspace)):
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
        # 0 for the owner, who never had units drawn — so nothing to refund.
        kwargs={"quota_units": getattr(request.state, "quota_units", 0)},
        daemon=True,
    )
    thread.start()
    return _video_with_signed_url(video)


@app.delete("/videos/{video_id}", status_code=204)
def delete_video(video_id: int, workspace: str = Depends(require_workspace)):
    if not db.delete_video(workspace, video_id):
        raise HTTPException(status_code=404, detail="Video not found")


def _finished_video_or_400(workspace: str, video_id: int) -> dict:
    video = db.get_video(workspace, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.get("status") != "done" or not video.get("url"):
        raise HTTPException(status_code=400, detail="This video isn't finished yet.")
    return video


@app.get("/videos/{video_id}/poster")
def video_poster(video_id: int, workspace: str = Depends(require_workspace)):
    """First frame of a finished clip as a PNG, for the Canvas editor's video
    mode: it becomes the locked background the overlay is drawn against, and
    width/height tell the client what resolution to export the overlay at.
    Local ffmpeg work only — no provider call, so no rate limiting."""
    video = _finished_video_or_400(workspace, video_id)
    try:
        poster = extract_poster_frame(video["url"])
    except Exception:
        logger.exception("Poster extraction failed for video %s", video_id)
        raise HTTPException(status_code=502, detail="Could not read a frame from this video.")
    return {
        "signed_url": presign_asset_url(poster["url"]),
        "width": poster["width"],
        "height": poster["height"],
    }


class VideoOverlayRequest(BaseModel):
    overlay_base64: str = Field(min_length=1)


@app.post("/videos/{video_id}/overlay")
def create_video_overlay(video_id: int, body: VideoOverlayRequest,
                         workspace: str = Depends(require_workspace)):
    """Burn a transparent overlay PNG (from the Canvas editor's video mode)
    onto a whole clip, stored as a new video row. Same honesty rules as
    /canvas/export: local ffmpeg compositing, no provider call — so no rate
    limit, cost_usd=0.0, and manifest_verified stays False (no genblaze
    Pipeline ran, so there's no C2PA manifest to verify)."""
    if len(body.overlay_base64) > MAX_CANVAS_EXPORT_BYTES:
        raise HTTPException(status_code=400, detail="Overlay is too large.")
    source = _finished_video_or_400(workspace, video_id)
    overlay_png = _decode_data_url(body.overlay_base64, "overlay_base64")

    video = db.create_video(
        workspace_id=workspace, character_id=source.get("character_id"),
        character_name=source.get("character_name"), kind="overlay",
        prompt=f"Overlay on: {source['prompt']}"[:500], model="canvas-overlay",
        duration=source.get("duration"), aspect_ratio=source.get("aspect_ratio"),
    )
    try:
        result = overlay_video(source["url"], overlay_png)
    except Exception:
        logger.exception("Overlay compositing failed for video %s", video_id)
        db.finish_video(video["id"], status="error",
                        error="Overlay compositing failed. Please try again.")
        raise HTTPException(status_code=502, detail="Overlay compositing failed. Please try again.")
    db.finish_video(
        video["id"], status="done", url=result["url"], original_url=result["url"],
        sha256=result["sha256"], mime_type=result["mime_type"], cost_usd=0.0,
        manifest_verified=False,
    )
    return _video_with_signed_url(db.get_video(workspace, video["id"]))


MAX_MUSIC_UPLOAD_BYTES = 15 * 1024 * 1024
ALLOWED_MUSIC_TYPES = {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/mp4", "audio/m4a"}


@app.post("/uploads/music")
async def upload_music(file: UploadFile = File(...), workspace: str = Depends(require_workspace)):
    """A user's own background-music file for the motion comic — not a paid
    generation call, just storage, so no rate limiting or owner-key check."""
    if file.content_type not in ALLOWED_MUSIC_TYPES:
        raise HTTPException(status_code=400, detail="Upload an MP3, WAV or M4A audio file.")
    data = await file.read()
    if len(data) > MAX_MUSIC_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Audio file too large (max 15 MB).")
    ext = {"audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav",
           "audio/x-wav": "wav", "audio/mp4": "m4a", "audio/m4a": "m4a"}.get(file.content_type, "mp3")
    url, sha256 = upload_bytes(f"uploads/music/{workspace}/{uuid.uuid4().hex}.{ext}", data, file.content_type)
    return {"url": url, "sha256": sha256}


class MotionComicPanel(BaseModel):
    scene_id: int
    character_id: int
    text: str = Field(min_length=1, max_length=500)
    caption: str | None = Field(default=None, max_length=200)


class MotionComicRequest(BaseModel):
    # No GMI video call happens here at all — see generate_motion_comic's
    # docstring for why (kling-identify-face only ever finds one face, so
    # real multi-character lip-sync isn't achievable). Each panel is a still
    # scene image held on screen for exactly as long as its own line takes.
    panels: list[MotionComicPanel] = Field(min_length=2, max_length=12)
    music_url: str | None = None


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
            "caption": p.caption,
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
            result = generate_motion_comic(panels, music_url=body.music_url)
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


# ── Bringing your own footage ────────────────────────────────────────────
# Everything else in the vault was generated here. Material shot elsewhere —
# a phone clip, a product photo, a logo — has to be able to sit on the same
# timeline, so uploads land as ordinary vault rows rather than as a separate
# second-class pool. They are marked model="upload" and never claim a
# provenance manifest, which is what lets the merged manifest of a finished
# cut say honestly which parts are AI and which are not.

MAX_VIDEO_UPLOAD_BYTES = 120 * 1024 * 1024
ALLOWED_VIDEO_TYPES = {
    "video/mp4": "mp4", "video/quicktime": "mov", "video/x-m4v": "m4v",
    "video/webm": "webm", "video/x-matroska": "mkv",
}
UPLOAD_CHUNK = 1024 * 1024


async def _spool_upload(file: UploadFile, destination: Path, max_bytes: int) -> int:
    """Stream an upload to disk, stopping the moment it exceeds the limit.

    `await file.read()` would buy the whole file into memory before the size
    check could reject it — which makes the limit advisory rather than
    protective on a container sized for one ffmpeg run.
    """
    written = 0
    with destination.open("wb") as out:
        while chunk := await file.read(UPLOAD_CHUNK):
            written += len(chunk)
            if written > max_bytes:
                raise HTTPException(
                    status_code=400,
                    detail=f"File too large (max {max_bytes // (1024 * 1024)} MB).",
                )
            out.write(chunk)
    return written


@app.post("/uploads/image")
async def upload_image(file: UploadFile = File(...),
                       workspace: str = Depends(require_workspace)):
    """A photo from outside, stored as a studio asset so it appears in the
    timeline pool and the canvas background picker like anything else."""
    import uuid as _uuid

    if file.content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(status_code=400, detail="Upload a PNG, JPEG or WebP image.")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Image too large (max 12 MB).")
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[file.content_type]
    url, sha256 = upload_bytes(
        f"uploads/images/{workspace}/{_uuid.uuid4().hex}.{ext}", data, file.content_type,
    )
    return _scene_with_signed_url(db.create_studio_image(
        workspace_id=workspace,
        kind="upload",
        prompt=(file.filename or "Uploaded image")[:200],
        url=url,
        original_url=url,
        sha256=sha256,
        model="upload",
        quality=None,
        disclosure=None,
        cost_usd=0.0,
        # Not generated here and not run through a genblaze pipeline, so there
        # is nothing to verify — same honesty rule as the canvas export.
        manifest_verified=False,
    ))


@app.post("/uploads/video")
async def upload_video(file: UploadFile = File(...),
                       workspace: str = Depends(require_workspace)):
    """A clip from outside, stored as a finished video row so it can be
    trimmed, graded and cut on the timeline like a generated one."""
    import tempfile
    import uuid as _uuid

    ext = ALLOWED_VIDEO_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(
            status_code=400, detail="Upload an MP4, MOV, M4V, WebM or MKV video.")

    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / f"upload.{ext}"
        await _spool_upload(file, local, MAX_VIDEO_UPLOAD_BYTES)
        probe = probe_media(str(local))
        url, sha256 = upload_path(
            f"uploads/video/{workspace}/{_uuid.uuid4().hex}.{ext}", local, file.content_type,
        )

    video = db.create_video(
        workspace_id=workspace, character_id=None, character_name=None,
        kind="upload", prompt=(file.filename or "Uploaded clip")[:200],
        model="upload",
        duration=int(probe["duration"]) if probe.get("duration") else None,
        aspect_ratio=_aspect_label(probe.get("width"), probe.get("height")),
    )
    db.finish_video(
        video["id"], status="done", url=url, original_url=url, sha256=sha256,
        mime_type=file.content_type, cost_usd=0.0, manifest_verified=False,
    )
    return _video_with_signed_url(db.get_video(workspace, video["id"]))


def _aspect_label(width: int | None, height: int | None) -> str | None:
    """Nearest of the three timeline canvases, for display only — the renderer
    letterboxes anything that doesn't match, so a wrong guess costs nothing."""
    if not width or not height:
        return None
    ratio = width / height
    return min(
        (("16:9", 16 / 9), ("9:16", 9 / 16), ("1:1", 1.0)),
        key=lambda option: abs(option[1] - ratio),
    )[0]


# ── Timeline: the cut ────────────────────────────────────────────────────
# The step that used to happen outside the app. A sequence is an ordered list
# of references into the vault — nothing is copied into it — so the edit stays
# small, stays editable, and can always say exactly which asset each second of
# the result came from.

MAX_SEQUENCE_CLIPS = 60
MAX_SEQUENCE_SECONDS = 300
MAX_AUDIO_TRACKS = 4

SequenceLook = Literal["none", "enhance", "warm", "cool", "noir", "vivid", "vintage", "soft"]
SequenceMotion = Literal["none", "zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"]
SequenceTransition = Literal["cut", "fade", "dissolve"]
SequenceTitleStyle = Literal["center", "lower_third", "left", "end_card"]
SequenceAspect = Literal["16:9", "9:16", "1:1"]
SequenceResolution = Literal["720p", "1080p"]
# The request schema and the renderer must offer exactly the same sets — an
# option accepted here but unknown there would silently render as its default,
# which is the worst kind of bug: it looks like the feature simply didn't work.
assert set(SequenceLook.__args__) == set(SEQUENCE_LOOKS)
assert set(SequenceMotion.__args__) == set(SEQUENCE_MOTIONS)
assert set(SequenceTransition.__args__) == set(SEQUENCE_TRANSITIONS)
assert set(SequenceTitleStyle.__args__) == set(SEQUENCE_TITLE_STYLES)
assert set(SequenceAspect.__args__) == set(SEQUENCE_ASPECTS)
assert set(SequenceResolution.__args__) == set(SEQUENCE_RESOLUTIONS)


class TimelineClip(BaseModel):
    # "title" is a text panel and carries no ref_id; every other source names a
    # row in the table it is called after.
    source: Literal["asset", "scene", "studio", "video", "title"]
    ref_id: int | None = None
    # Screen time for stills and title cards. Ignored for video clips, whose
    # length is whatever in/out actually trim out of the source.
    duration: float = Field(default=3.5, ge=0.2, le=60)
    in_point: float | None = Field(default=None, ge=0)
    out_point: float | None = Field(default=None, ge=0)
    # "fade" dips through black and keeps the film's length; "dissolve" blends
    # the two clips and therefore SHORTENS it by the overlap.
    transition: SequenceTransition = "cut"
    fade_duration: float = Field(default=0.5, ge=0.1, le=SEQUENCE_MAX_FADE)
    look: SequenceLook = "none"
    motion: SequenceMotion = "none"
    # Offsets around neutral, so an untouched slider costs nothing.
    brightness: float = Field(default=0.0, ge=-0.5, le=0.5)
    contrast: float = Field(default=0.0, ge=-0.8, le=1.5)
    saturation: float = Field(default=0.0, ge=-1.0, le=2.0)
    volume: float = Field(default=1.0, ge=0.0, le=4.0)
    text: str | None = Field(default=None, max_length=300)
    subtitle: str | None = Field(default=None, max_length=300)
    title_style: SequenceTitleStyle = "center"
    # A voice line for THIS clip, on top of whatever audio it already has —
    # the motion comic's one-voice-per-panel idea, available per clip here.
    voice_url: str | None = Field(default=None, max_length=2000)
    voice_volume: float = Field(default=1.0, ge=0.0, le=4.0)


class TimelineAudioTrack(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    volume: float = Field(default=0.25, ge=0.0, le=2.0)
    # Ducked by default: a bed that doesn't step back for speech is the single
    # most common way an otherwise good cut sounds amateurish.
    duck: bool = True
    label: str | None = Field(default=None, max_length=120)


class SequenceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    aspect_ratio: SequenceAspect = "16:9"
    resolution: SequenceResolution = DEFAULT_SEQUENCE_RESOLUTION
    clips: list[TimelineClip] = Field(default_factory=list, max_length=MAX_SEQUENCE_CLIPS)
    audio_tracks: list[TimelineAudioTrack] = Field(default_factory=list, max_length=MAX_AUDIO_TRACKS)


class AutoCutRequest(BaseModel):
    brief: str = Field(min_length=1, max_length=2000)
    name: str = Field(default="", max_length=120)
    target_seconds: int = Field(default=30, ge=5, le=MAX_SEQUENCE_SECONDS)
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"


def _clip_provenance(source: str, row: dict | None) -> dict:
    """What the merged manifest records about one source.

    `ai_generated` is decided by the model that made it, not by which table it
    sits in: an uploaded photo lives in studio_images next to generated ones,
    and the difference is exactly what a viewer of the finished cut deserves to
    be told.
    """
    if source == "title":
        return {"ai_generated": False, "model": "loomina-title-card",
                "renderer": "pillow", "manifest_verified": False}
    row = row or {}
    model = row.get("model")
    return {
        "ai_generated": model not in (None, "upload"),
        "model": model,
        "prompt": (row.get("prompt") or "")[:500] or None,
        "sha256": row.get("sha256"),
        "disclosure": row.get("disclosure"),
        "quality": row.get("quality"),
        "manifest_verified": bool(row.get("manifest_verified")),
        "cost_usd": row.get("cost_usd"),
        "created_at": row.get("created_at"),
        "character": row.get("character_name")
                     or (" + ".join(row.get("participant_names") or []) or None),
    }


def _resolve_clip(workspace: str, index: int, clip: TimelineClip) -> dict:
    """Turn one request clip into what the renderer needs: a real URL plus the
    provenance of whatever is behind it. Every lookup is workspace-scoped, so a
    guessed row id from another tenant resolves to nothing."""
    data = clip.model_dump()
    # A voice line is fetched server-side like any other input, so it may only
    # ever name an object in our own bucket.
    if clip.voice_url and not is_bucket_url(clip.voice_url):
        raise HTTPException(
            status_code=400,
            detail=f"Clip {index + 1}: a voiceover must be audio from this workspace.")

    if clip.source == "title":
        if not (clip.text or "").strip():
            raise HTTPException(
                status_code=400, detail=f"Clip {index + 1}: a text panel needs text.")
        return {**data, "url": None, "provenance": _clip_provenance("title", None)}

    if clip.ref_id is None:
        raise HTTPException(
            status_code=400, detail=f"Clip {index + 1}: no asset selected.")

    lookup = {
        "asset": db.get_asset,
        "scene": db.get_scene,
        "studio": db.get_studio_image,
        "video": db.get_video,
    }[clip.source]
    row = lookup(workspace, clip.ref_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Clip {index + 1}: {clip.source} {clip.ref_id} not found.")
    if clip.source == "video" and (row.get("status") != "done" or not row.get("url")):
        raise HTTPException(
            status_code=400,
            detail=f"Clip {index + 1}: that video isn't finished yet.")
    if clip.source == "asset" and row.get("kind") != "image":
        raise HTTPException(
            status_code=400, detail=f"Clip {index + 1}: only images can go on the timeline.")
    if clip.in_point is not None and clip.out_point is not None and clip.out_point <= clip.in_point:
        raise HTTPException(
            status_code=400, detail=f"Clip {index + 1}: the out point must come after the in point.")

    # The untouched original where one exists: a disclosed copy carries a
    # burned-in badge sized for a still, which a video frame would only blur.
    # The manifest still records the disclosure mode the source was stored with.
    return {
        **data,
        "url": row.get("original_url") or row["url"],
        "provenance": _clip_provenance(clip.source, row),
    }


def _resolve_sequence(workspace: str, body: SequenceRequest) -> tuple[list[dict], list[dict]]:
    if not body.clips:
        raise HTTPException(status_code=400, detail="The timeline is empty — add a clip first.")
    clips = [_resolve_clip(workspace, i, clip) for i, clip in enumerate(body.clips)]

    # Stills contribute their set duration; a video contributes at most its own
    # length, which is all the estimate can know without downloading it.
    estimate = 0.0
    for clip in clips:
        if clip["source"] == "video":
            estimate += (clip.get("out_point") or clip.get("duration") or 5.0) - (clip.get("in_point") or 0.0)
        else:
            estimate += clip.get("duration") or 3.5
        # A dissolve overlaps its two clips, so it makes the film shorter —
        # the estimate has to say so, or a cut right on the limit is refused
        # for length it will not actually have.
        if clip.get("transition") == "dissolve":
            estimate -= min(float(clip.get("fade_duration") or 0.5), SEQUENCE_MAX_FADE)
    if estimate > MAX_SEQUENCE_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=f"This cut is about {int(estimate)}s — the limit is {MAX_SEQUENCE_SECONDS}s. "
                   "Shorten a few clips or split it into two sequences.",
        )

    tracks = []
    for track in body.audio_tracks:
        if not is_bucket_url(track.url):
            raise HTTPException(
                status_code=400,
                detail="A soundtrack must be an audio file from this workspace — "
                       "generate one, or upload it under Audio.",
            )
        tracks.append(track.model_dump())
    return clips, tracks


def _sequence_public(sequence: dict) -> dict:
    """A sequence as the editor sees it: the rendered result and its manifest
    are signed, the stored clip list is returned untouched."""
    sequence = dict(sequence)
    for field, target in (("manifest_url", "signed_manifest_url"),):
        sequence[target] = None
        if sequence.get(field):
            try:
                sequence[target] = presign_asset_url(sequence[field])
            except Exception:
                pass
    return sequence


@app.get("/sequences")
def list_sequences(workspace: str = Depends(require_workspace)):
    return [_sequence_public(s) for s in db.list_sequences(workspace)]


@app.post("/sequences")
def create_sequence_endpoint(body: SequenceRequest, workspace: str = Depends(require_workspace)):
    """Save an edit. Clips are validated against the vault now rather than at
    render time, so a broken reference is reported while the user is still
    looking at the timeline."""
    clips, tracks = _resolve_sequence(workspace, body)
    return _sequence_public(db.create_sequence(
        workspace_id=workspace,
        name=body.name,
        clips=[c.model_dump() for c in body.clips],
        aspect_ratio=body.aspect_ratio,
        audio_tracks=tracks,
        resolution=body.resolution,
    ))


@app.get("/sequences/{sequence_id}")
def get_sequence(sequence_id: int, workspace: str = Depends(require_workspace)):
    sequence = db.get_sequence(workspace, sequence_id)
    if sequence is None:
        raise HTTPException(status_code=404, detail="Sequence not found")
    return _sequence_public(sequence)


@app.put("/sequences/{sequence_id}")
def update_sequence(sequence_id: int, body: SequenceRequest,
                    workspace: str = Depends(require_workspace)):
    _resolve_sequence(workspace, body)
    updated = db.update_sequence(
        workspace_id=workspace,
        sequence_id=sequence_id,
        name=body.name,
        clips=[c.model_dump() for c in body.clips],
        aspect_ratio=body.aspect_ratio,
        audio_tracks=[t.model_dump() for t in body.audio_tracks],
        resolution=body.resolution,
    )
    if updated is None:
        existing = db.get_sequence(workspace, sequence_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Sequence not found")
        raise HTTPException(
            status_code=409,
            detail="This sequence is rendering right now — wait for it to finish before editing.",
        )
    return _sequence_public(updated)


@app.delete("/sequences/{sequence_id}", status_code=204)
def delete_sequence(sequence_id: int, workspace: str = Depends(require_workspace)):
    if not db.delete_sequence(workspace, sequence_id):
        raise HTTPException(status_code=404, detail="Sequence not found")


def _run_sequence_render(workspace: str, sequence_id: int, name: str, clips: list[dict],
                         aspect_ratio: str, tracks: list[dict],
                         resolution: str = DEFAULT_SEQUENCE_RESOLUTION) -> None:
    """Background worker — a 30-second cut is a minute or two of ffmpeg, well
    past a request's patience, so the row's status is polled instead (same
    shape as _run_video). Re-renders are far quicker: the piece cache means
    only what actually changed is encoded again."""
    video_id = None
    try:
        result = render_sequence(name, clips, aspect_ratio, tracks, resolution)
        video = db.create_video(
            workspace_id=workspace, character_id=None,
            character_name=None, kind="sequence",
            prompt=f"Timeline cut: {name}"[:500], model="timeline",
            duration=int(round(result["duration"])), aspect_ratio=aspect_ratio,
        )
        video_id = video["id"]
        db.finish_video(
            video_id, status="done", url=result["url"], original_url=result["url"],
            sha256=result["sha256"], mime_type=result["mime_type"],
            # Local assembly, no provider call — so no cost, and no manifest of
            # our own to verify. What this cut DOES carry is the merged
            # manifest over its sources, stored on the sequence.
            cost_usd=0.0, manifest_verified=False,
        )
        db.finish_sequence(
            sequence_id, status="done", video_id=video_id,
            manifest=result["manifest"], manifest_url=result["manifest_url"],
            duration=result["duration"],
        )
    except Exception:
        logger.exception("Sequence %s render failed", sequence_id)
        db.finish_sequence(
            sequence_id, status="error", video_id=video_id,
            error="Rendering failed. Please try again.",
        )
    finally:
        _release_slot(workspace, "sequence")


@app.post("/sequences/{sequence_id}/render")
def render_sequence_endpoint(sequence_id: int, workspace: str = Depends(require_workspace)):
    """Assemble the cut. No generation_guard and no rate limit: like the canvas
    export and the video overlay, this calls no provider and costs nothing. The
    in-flight slot is what keeps one workspace from starting a second ffmpeg
    run on top of the first."""
    sequence = db.get_sequence(workspace, sequence_id)
    if sequence is None:
        raise HTTPException(status_code=404, detail="Sequence not found")

    body = SequenceRequest(
        name=sequence["name"], aspect_ratio=sequence["aspect_ratio"],
        resolution=sequence.get("resolution") or DEFAULT_SEQUENCE_RESOLUTION,
        clips=sequence["clips"], audio_tracks=sequence["audio_tracks"],
    )
    clips, tracks = _resolve_sequence(workspace, body)

    _acquire_slot(workspace, "sequence")
    if not db.start_sequence_render(workspace, sequence_id):
        _release_slot(workspace, "sequence")
        raise HTTPException(status_code=409, detail="This sequence is already rendering.")
    threading.Thread(
        target=_run_sequence_render,
        args=(workspace, sequence_id, sequence["name"], clips,
              sequence["aspect_ratio"], tracks, body.resolution),
        daemon=True,
    ).start()
    return _sequence_public(db.get_sequence(workspace, sequence_id))


@app.get("/sequences/{sequence_id}/manifest")
def sequence_manifest(sequence_id: int, workspace: str = Depends(require_workspace)):
    """The merged provenance manifest of the last render: every clip, where it
    sits, which model made it, and whether that source's own manifest
    verified."""
    sequence = db.get_sequence(workspace, sequence_id)
    if sequence is None:
        raise HTTPException(status_code=404, detail="Sequence not found")
    if not sequence.get("manifest"):
        raise HTTPException(status_code=400, detail="This sequence hasn't been rendered yet.")
    return {
        "manifest": sequence["manifest"],
        "signed_manifest_url": _sequence_public(sequence)["signed_manifest_url"],
    }


@app.post("/sequences/{sequence_id}/verify")
def verify_sequence(sequence_id: int, workspace: str = Depends(require_workspace)):
    """Read the manifest back out of the rendered MP4 and compare it with the
    stored one.

    This is the point of embedding it: the file carries its own account of what
    it is made of, so it stays verifiable after it leaves this app — which no
    external editor's output can do. A mismatch means the file was re-encoded
    somewhere along the way and the embedded copy no longer describes it.
    """
    sequence = db.get_sequence(workspace, sequence_id)
    if sequence is None:
        raise HTTPException(status_code=404, detail="Sequence not found")
    if not sequence.get("video_id") or not sequence.get("manifest"):
        raise HTTPException(status_code=400, detail="This sequence hasn't been rendered yet.")
    video = db.get_video(workspace, sequence["video_id"])
    if video is None or not video.get("url"):
        raise HTTPException(status_code=404, detail="The rendered file is gone.")

    signed = presign_asset_url(video["url"]) or video["url"]
    embedded = read_embedded_manifest(signed)
    return {
        "embedded": embedded,
        "found": embedded is not None,
        "matches_stored": embedded == sequence["manifest"],
    }


# ── Timeline: the media pool ─────────────────────────────────────────────

def _pool_entry(key: str, kind: str, label: str, url: str | None,
                duration: float | None, extra: dict | None = None) -> dict:
    entry = {"key": key, "kind": kind, "label": label, "duration": duration,
             "signed_url": None, **(extra or {})}
    if url:
        try:
            entry["signed_url"] = presign_asset_url(url)
        except Exception:
            pass
    return entry


@app.get("/timeline/pool")
def timeline_pool(workspace: str = Depends(require_workspace)):
    """Everything in this workspace that can go on a timeline, in one call.

    The editor needs stills and clips side by side; fetching four endpoints and
    stitching them client-side is what the canvas does for backgrounds, and it
    shows — the pool is the same list four times over, with four chances to
    disagree about what a label looks like."""
    pool = []
    for asset in db.list_assets(workspace, "image"):
        pool.append(_pool_entry(
            f"asset:{asset['id']}", "still",
            f"{asset.get('character_name') or '?'} — {(asset.get('prompt') or '')[:60]}",
            asset["url"], None,
            {"source": "asset", "ref_id": asset["id"], "model": asset.get("model")},
        ))
    for scene in db.list_scenes(workspace):
        pool.append(_pool_entry(
            f"scene:{scene['id']}", "still",
            f"Scene: {' + '.join(scene.get('participant_names') or [])} — {(scene.get('prompt') or '')[:50]}",
            scene["url"], None,
            {"source": "scene", "ref_id": scene["id"], "model": scene.get("model")},
        ))
    for image in db.list_studio_images(workspace):
        pool.append(_pool_entry(
            f"studio:{image['id']}", "still",
            f"{image['kind']} — {(image.get('prompt') or '')[:60]}",
            image["url"], None,
            {"source": "studio", "ref_id": image["id"], "model": image.get("model")},
        ))
    for video in db.list_videos(workspace):
        if video.get("status") != "done" or not video.get("url"):
            continue
        pool.append(_pool_entry(
            f"video:{video['id']}", "video",
            f"{(video.get('character_name') + ': ') if video.get('character_name') else ''}"
            f"{(video.get('prompt') or '')[:60]}",
            video["url"], float(video["duration"]) if video.get("duration") else None,
            {"source": "video", "ref_id": video["id"], "model": video.get("model"),
             "kind_label": video.get("kind")},
        ))
    return pool


@app.get("/timeline/audio")
def timeline_audio(workspace: str = Depends(require_workspace)):
    """Audio that can be laid under a cut: generated voiceovers, dialogues, and
    anything uploaded through /uploads/music."""
    tracks = []
    for clip in db.list_audio_clips(workspace):
        tracks.append(_pool_entry(
            f"audio:{clip['id']}", "audio", (clip.get("text") or "")[:70],
            clip["url"], None, {"url": clip["url"], "voice": clip.get("voice")},
        ))
    for dialogue in db.list_dialogues(workspace):
        tracks.append(_pool_entry(
            f"dialogue:{dialogue['id']}", "audio",
            f"Dialogue: {' + '.join(dialogue.get('participant_names') or [])}",
            dialogue["url"], None, {"url": dialogue["url"]},
        ))
    return tracks


# ── Timeline: the assisted cut ───────────────────────────────────────────

@app.post("/sequences/auto", dependencies=[Depends(generation_guard("script", 1))])
def auto_cut(body: AutoCutRequest, workspace: str = Depends(require_workspace)):
    """Let the model propose an edit over what is already in the vault.

    It returns an edit decision list, never media — and every shot key it names
    is checked against the real pool here, so an invented reference is dropped
    rather than fetched. The result is saved as a normal draft sequence: it is
    a starting point to be reworked in the editor, not a finished cut.
    """
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=400, detail="The assisted cut needs OPENAI_API_KEY to be configured.")

    pool = timeline_pool(workspace)
    if not pool:
        raise HTTPException(
            status_code=400,
            detail="There is nothing to cut yet — generate or upload some material first.",
        )
    by_key = {entry["key"]: entry for entry in pool}

    with generation_slot(workspace, "auto_cut"):
        try:
            plan = plan_sequence(
                body.brief,
                [{"key": e["key"], "kind": e["kind"], "label": e["label"],
                  "duration": e["duration"]} for e in pool],
                body.target_seconds, body.aspect_ratio,
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("Assisted cut planning failed")
            raise HTTPException(status_code=502, detail="The assisted cut failed. Please try again.")

    clips, dropped = [], 0
    for raw in (plan.get("clips") or [])[:MAX_SEQUENCE_CLIPS]:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "")
        fields = {
            "duration": raw.get("duration"),
            "transition": raw.get("transition"),
            "look": raw.get("look"),
            "motion": raw.get("motion"),
            "text": raw.get("text"),
            "subtitle": raw.get("subtitle"),
            "title_style": raw.get("title_style"),
        }
        fields = {k: v for k, v in fields.items() if v not in (None, "")}
        if key == "title":
            fields.setdefault("text", "")
            if not str(fields["text"]).strip():
                dropped += 1
                continue
            candidate = {"source": "title", **fields}
        else:
            entry = by_key.get(key)
            if entry is None:
                dropped += 1
                continue
            candidate = {"source": entry["source"], "ref_id": entry["ref_id"], **fields}
            if entry["kind"] == "video":
                # A model has no way to know how much of a clip is usable, so
                # it never gets to trim one — the whole clip plays, and the
                # editor sets in/out by eye.
                candidate.pop("motion", None)
        try:
            clips.append(TimelineClip(**candidate))
        except Exception:
            dropped += 1

    if not clips:
        raise HTTPException(
            status_code=502,
            detail="The assisted cut came back without a usable clip. Try a more specific brief.",
        )

    name = (body.name or plan.get("name") or body.brief)[:120].strip() or "Assisted cut"
    sequence = db.create_sequence(
        workspace_id=workspace, name=name,
        clips=[c.model_dump() for c in clips],
        aspect_ratio=body.aspect_ratio, audio_tracks=[],
    )
    result = _sequence_public(sequence)
    # Reported rather than hidden: a plan that lost half its shots to bad
    # references is a plan the user should look at closely.
    result["dropped_clips"] = dropped
    return result
