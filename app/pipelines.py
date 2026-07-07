import tempfile

from genblaze_core import KeyStrategy, Modality, ObjectStorageSink, Pipeline, StepStatus
from genblaze_core.models.asset import Asset
from genblaze_elevenlabs import ElevenLabsTTSProvider
from genblaze_openai import DalleProvider, OpenAITTSProvider
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


IDENTITY_INSTRUCTION = (
    "Use the person from the reference image(s) and keep their identity exactly: "
    "same face, facial features, hair color and style, age, and build. "
    "Render that same person in a new scene: "
)


def generate_character_portrait(
    character_id: int,
    prompt: str,
    disclosure: str = "invisible",
    references: list[str] | None = None,
) -> dict:
    from app.disclosure import apply_image_disclosure
    from app.storage import presign_asset_url

    step_kwargs: dict = {}
    final_prompt = prompt
    if references:
        signed = [presign_asset_url(url) for url in references[:3]]
        step_kwargs["external_inputs"] = [
            Asset(url=u, media_type="image/png") for u in signed if u
        ]
        if step_kwargs["external_inputs"]:
            final_prompt = IDENTITY_INSTRUCTION + prompt

    result = (
        Pipeline(f"character-{character_id}-portrait")
        .step(
            DalleProvider(),
            model="gpt-image-1",
            prompt=final_prompt,
            modality=Modality.IMAGE,
            size="1024x1024",
            **step_kwargs,
        )
        .run(sink=get_storage_sink(), timeout=180)
    )
    asset = _asset_result(result)
    asset["original_url"] = asset["url"]
    asset["url"] = apply_image_disclosure(asset["url"], result.manifest, disclosure)
    asset["disclosure"] = disclosure
    return asset


def generate_character_voice_line(character_id: int, text: str) -> dict:
    if ELEVENLABS_VOICE_ID:
        try:
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
        except Exception:
            pass  # fall through to OpenAI TTS below

    result = (
        Pipeline(f"character-{character_id}-voice-line-openai")
        .step(
            OpenAITTSProvider(),
            model="gpt-4o-mini-tts",
            prompt=text,
            modality=Modality.AUDIO,
            voice="onyx",
        )
        .run(sink=get_storage_sink(), timeout=120)
    )
    return _asset_result(result)
