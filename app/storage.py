"""Presigned GET URLs for assets in the private B2 bucket.

Genblaze stores plain object URLs; the bucket is private, so browsers
get a 401 on them. This module re-signs those URLs on the way out.
"""

import hashlib
import uuid
from functools import lru_cache
from urllib.parse import urlparse

import boto3
from botocore.config import Config

from app.config import B2_APP_KEY, B2_BUCKET_NAME, B2_KEY_ID, B2_REGION

SIGNED_URL_TTL_SECONDS = 3600


@lru_cache(maxsize=1)
def _s3_client():
    endpoint = f"https://s3.{B2_REGION}.backblazeb2.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=B2_REGION,
        aws_access_key_id=B2_KEY_ID,
        aws_secret_access_key=B2_APP_KEY,
        config=Config(signature_version="s3v4"),
    )


def presign_asset_url(url: str) -> str | None:
    """Turn a stored plain object URL into a time-limited signed URL.

    Returns None if the URL doesn't point at our bucket (or creds are
    missing), so callers can fall back gracefully.
    """
    if not (B2_KEY_ID and B2_APP_KEY and B2_REGION):
        return None
    path = urlparse(url).path.lstrip("/")
    prefix = f"{B2_BUCKET_NAME}/"
    if not path.startswith(prefix):
        return None
    key = path[len(prefix):]
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": B2_BUCKET_NAME, "Key": key},
        ExpiresIn=SIGNED_URL_TTL_SECONDS,
    )


def with_signed_url(asset: dict) -> dict:
    try:
        asset["signed_url"] = presign_asset_url(asset["url"])
    except Exception:
        asset["signed_url"] = None
    return asset


def upload_bytes(key: str, data: bytes, content_type: str) -> tuple[str, str]:
    """Store arbitrary bytes in B2 at `key`. Returns (plain_url, sha256)."""
    _s3_client().put_object(
        Bucket=B2_BUCKET_NAME, Key=key, Body=data, ContentType=content_type
    )
    url = f"https://s3.{B2_REGION}.backblazeb2.com/{B2_BUCKET_NAME}/{key}"
    return url, hashlib.sha256(data).hexdigest()


def upload_path(key: str, path, content_type: str) -> tuple[str, str]:
    """Store a file already on disk, streaming it instead of loading it.

    An uploaded video runs to tens of megabytes, and `upload_bytes` would hold
    the whole thing in memory on top of whatever ffmpeg is doing — on the 1 GB
    fallback VM in DEPLOY.md that is the difference between an upload and an
    OOM kill. Returns (plain_url, sha256).
    """
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    with open(path, "rb") as fh:
        _s3_client().put_object(
            Bucket=B2_BUCKET_NAME, Key=key, Body=fh, ContentType=content_type
        )
    url = f"https://s3.{B2_REGION}.backblazeb2.com/{B2_BUCKET_NAME}/{key}"
    return url, digest.hexdigest()


def is_bucket_url(url: str) -> bool:
    """Whether a URL points at an object in our own bucket.

    Anything a client hands back to be used as an input — a soundtrack to lay
    under a cut, a clip to trim — has to pass this, or the endpoint becomes a
    relay that fetches arbitrary URLs on the server's behalf. Same reasoning as
    /assets/proxy, kept here so every caller shares one definition.
    """
    parsed = urlparse(url or "")
    return (
        parsed.scheme == "https"
        and parsed.netloc == f"s3.{B2_REGION}.backblazeb2.com"
        and parsed.path.startswith(f"/{B2_BUCKET_NAME}/")
    )


def download_bytes(url: str) -> bytes:
    """Fetch the raw bytes of one of our stored B2 objects by its plain URL."""
    path = urlparse(url).path.lstrip("/")
    key = path[len(f"{B2_BUCKET_NAME}/"):] if path.startswith(f"{B2_BUCKET_NAME}/") else path
    return _s3_client().get_object(Bucket=B2_BUCKET_NAME, Key=key)["Body"].read()


def upload_reference_image(character_id: int, data: bytes, content_type: str) -> tuple[str, str]:
    """Store a user-uploaded reference image in B2. Returns (plain_url, sha256)."""
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(content_type, "png")
    key = f"uploads/characters/{character_id}/{uuid.uuid4().hex}.{ext}"
    _s3_client().put_object(
        Bucket=B2_BUCKET_NAME, Key=key, Body=data, ContentType=content_type
    )
    url = f"https://s3.{B2_REGION}.backblazeb2.com/{B2_BUCKET_NAME}/{key}"
    return url, hashlib.sha256(data).hexdigest()
