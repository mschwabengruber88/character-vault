import logging
import threading
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import db
from app.config import CORS_ORIGINS, GENERATE_API_KEY
from app.pipelines import (
    DEFAULT_IMAGE_MODEL,
    IMAGE_MODELS,
    available_image_models,
    available_voices,
    generate_character_portrait,
    generate_character_voice_line,
    generate_scene,
)
from app.storage import presign_asset_url, with_signed_url

logger = logging.getLogger("character_vault")


def require_api_key(x_api_key: str = Header(default="")):
    if not GENERATE_API_KEY or x_api_key != GENERATE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


_inflight_lock = threading.Lock()
_inflight: set[tuple[int, str]] = set()


@contextmanager
def generation_slot(character_id: int, kind: str):
    """One paid generation per character+kind at a time — a duplicate
    request (double-click, impatient retry) is rejected instead of
    silently billed twice."""
    key = (character_id, kind)
    with _inflight_lock:
        if key in _inflight:
            raise HTTPException(
                status_code=409,
                detail="A generation for this character is already running. Please wait for it to finish.",
            )
        _inflight.add(key)
    try:
        yield
    finally:
        with _inflight_lock:
            _inflight.discard(key)


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
    return {"image_models": available_image_models()}


@app.get("/voices")
def voices():
    return available_voices()


@app.post("/characters")
def create_character(body: CharacterCreate):
    return db.create_character(body.name, body.description)


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
                character_id, body.prompt, body.disclosure, references, body.quality, body.model
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
