import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import db
from app.config import CORS_ORIGINS, GENERATE_API_KEY
from app.pipelines import generate_character_portrait, generate_character_voice_line
from app.storage import with_signed_url

logger = logging.getLogger("character_vault")


def require_api_key(x_api_key: str = Header(default="")):
    if not GENERATE_API_KEY or x_api_key != GENERATE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


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


class VoiceLineRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/characters")
def create_character(body: CharacterCreate):
    return db.create_character(body.name, body.description)


@app.get("/characters")
def list_characters():
    return db.list_characters()


@app.get("/characters/{character_id}")
def get_character(character_id: int):
    character = db.get_character(character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    character["assets"] = [with_signed_url(a) for a in character["assets"]]
    return character


@app.delete("/characters/{character_id}", status_code=204)
def delete_character(character_id: int):
    if not db.delete_character(character_id):
        raise HTTPException(status_code=404, detail="Character not found")


@app.get("/assets")
def list_assets(kind: str | None = Query(default=None, pattern="^(image|voice)$")):
    return [with_signed_url(a) for a in db.list_assets(kind)]


@app.post("/characters/{character_id}/generate/image", dependencies=[Depends(require_api_key)])
def generate_image(character_id: int, body: PortraitRequest):
    character = db.get_character(character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    try:
        result = generate_character_portrait(character_id, body.prompt)
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
    ))


@app.post("/characters/{character_id}/generate/voice", dependencies=[Depends(require_api_key)])
def generate_voice(character_id: int, body: VoiceLineRequest):
    character = db.get_character(character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    try:
        result = generate_character_voice_line(character_id, body.text)
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
    ))
