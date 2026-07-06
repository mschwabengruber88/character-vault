import tempfile

from genblaze_core import KeyStrategy, Modality, ObjectStorageSink, Pipeline, StepStatus
from genblaze_elevenlabs import ElevenLabsTTSProvider
from genblaze_openai import DalleProvider
from genblaze_s3 import S3StorageBackend

from app.config import B2_BUCKET_NAME, B2_REGION, ELEVENLABS_VOICE_ID

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


def generate_character_portrait(character_id: int, prompt: str) -> dict:
    result = (
        Pipeline(f"character-{character_id}-portrait")
        .step(
            DalleProvider(),
            model="gpt-image-1",
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
            ElevenLabsTTSProvider(output_dir=tempfile.gettempdir()),
            model="eleven_v3",
            prompt=text,
            modality=Modality.AUDIO,
            voice_id=ELEVENLABS_VOICE_ID,
        )
        .run(sink=get_storage_sink(), timeout=120)
    )
    return _asset_result(result)
