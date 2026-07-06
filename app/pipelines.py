from genblaze_core import KeyStrategy, Modality, ObjectStorageSink, Pipeline
from genblaze_elevenlabs import ElevenLabsTTSProvider
from genblaze_openai import DalleProvider
from genblaze_s3 import S3StorageBackend

from app.config import B2_BUCKET_NAME, ELEVENLABS_VOICE_ID

_sink: ObjectStorageSink | None = None


def get_storage_sink() -> ObjectStorageSink:
    global _sink
    if _sink is None:
        _sink = ObjectStorageSink(
            S3StorageBackend.for_backblaze(B2_BUCKET_NAME),
            key_strategy=KeyStrategy.HIERARCHICAL,
        )
    return _sink


def _asset_result(result) -> dict:
    asset = result.run.steps[0].assets[0]
    return {
        "url": asset.url,
        "sha256": asset.sha256,
        "mime_type": asset.mime_type,
        "manifest_verified": result.manifest.verify(),
    }


def generate_character_portrait(character_id: int, prompt: str) -> dict:
    result = (
        Pipeline(f"character-{character_id}-portrait")
        .step(
            DalleProvider(),
            model="dall-e-3",
            prompt=prompt,
            modality=Modality.IMAGE,
            size="1024x1024",
        )
        .run(sink=get_storage_sink(), timeout=120)
    )
    return _asset_result(result)


def generate_character_voice_line(character_id: int, text: str) -> dict:
    if not ELEVENLABS_VOICE_ID:
        raise ValueError("ELEVENLABS_VOICE_ID is not set")
    result = (
        Pipeline(f"character-{character_id}-voice-line")
        .step(
            ElevenLabsTTSProvider(output_dir="output/"),
            model="eleven_v3",
            prompt=text,
            modality=Modality.AUDIO,
            voice_id=ELEVENLABS_VOICE_ID,
        )
        .run(sink=get_storage_sink(), timeout=120)
    )
    return _asset_result(result)
