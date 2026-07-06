from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import db
from app.config import CORS_ORIGINS
from app.pipelines import generate_character_portrait, generate_character_voice_line

app = FastAPI(title="Character Vault")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    db.init_db()


class CharacterCreate(BaseModel):
    name: str
    description: str = ""


class PortraitRequest(BaseModel):
    prompt: str


class VoiceLineRequest(BaseModel):
    text: str


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
    return character


@app.post("/characters/{character_id}/generate/image")
def generate_image(character_id: int, body: PortraitRequest):
    character = db.get_character(character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    try:
        result = generate_character_portrait(character_id, body.prompt)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Image generation failed: {exc}")
    return db.add_asset(
        character_id=character_id,
        kind="image",
        url=result["url"],
        sha256=result["sha256"],
        mime_type=result["mime_type"],
        prompt=body.prompt,
        manifest_verified=result["manifest_verified"],
    )


@app.post("/characters/{character_id}/generate/voice")
def generate_voice(character_id: int, body: VoiceLineRequest):
    character = db.get_character(character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    try:
        result = generate_character_voice_line(character_id, body.text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Voice generation failed: {exc}")
    return db.add_asset(
        character_id=character_id,
        kind="voice",
        url=result["url"],
        sha256=result["sha256"],
        mime_type=result["mime_type"],
        prompt=body.text,
        manifest_verified=result["manifest_verified"],
    )
