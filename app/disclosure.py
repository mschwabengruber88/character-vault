"""AI-provenance disclosure for generated images.

Two modes, chosen per generation:

- "invisible": the genblaze provenance manifest is embedded into the
  PNG itself (via genblaze's PngHandler), invisible to the eye but
  readable/verifiable by tools.
- "visible": additionally burns a small "AI" badge into the corner of
  the image (Gemini-style), so the disclosure survives screenshots.

Both modes keep the untouched original in B2 next to the disclosed
copy, so the manifest's hash chain over the original stays intact.
"""

import io
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

from genblaze_core.media import PngHandler
from PIL import Image, ImageDraw, ImageFont

from app.config import B2_BUCKET_NAME, B2_REGION
from app.storage import _s3_client

DISCLOSURE_MODES = ("visible", "invisible")


def _badge_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def _star_points(cx: float, cy: float, outer: float, inner: float) -> list[tuple[float, float]]:
    # four-point sparkle: alternate outer tips (N/E/S/W) and inner diagonals
    return [
        (cx, cy - outer), (cx + inner, cy - inner),
        (cx + outer, cy), (cx + inner, cy + inner),
        (cx, cy + outer), (cx - inner, cy + inner),
        (cx - outer, cy), (cx - inner, cy - inner),
    ]


def stamp_visible_badge(png_bytes: bytes) -> bytes:
    image = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    width, height = image.size
    scale = max(width, height) / 1024

    font = _badge_font(max(12, int(34 * scale)))
    label = "AI"
    measure = ImageDraw.Draw(image)
    bbox = measure.textbbox((0, 0), label, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]

    star_r = text_h * 0.62
    gap = int(10 * scale)
    pad_x, pad_y = int(20 * scale), int(12 * scale)
    margin = int(24 * scale)

    badge_w = pad_x + int(star_r * 2) + gap + text_w + pad_x
    badge_h = text_h + 2 * pad_y
    x0 = width - margin - badge_w
    y0 = height - margin - badge_h

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle(
        [x0, y0, x0 + badge_w, y0 + badge_h],
        radius=badge_h // 2,
        fill=(12, 12, 14, 165),
    )
    star_cx = x0 + pad_x + star_r
    star_cy = y0 + badge_h / 2
    draw.polygon(_star_points(star_cx, star_cy, star_r, star_r * 0.28), fill=(255, 255, 255, 235))
    draw.text(
        (x0 + pad_x + star_r * 2 + gap - bbox[0], y0 + pad_y - bbox[1]),
        label,
        font=font,
        fill=(255, 255, 255, 235),
    )

    out = Image.alpha_composite(image, overlay)
    buffer = io.BytesIO()
    out.save(buffer, format="PNG")
    return buffer.getvalue()


def _bucket_key(url: str) -> str:
    path = urlparse(url).path.lstrip("/")
    prefix = f"{B2_BUCKET_NAME}/"
    if not path.startswith(prefix):
        raise ValueError(f"URL is not in bucket {B2_BUCKET_NAME}: {url}")
    return path[len(prefix):]


def apply_image_disclosure(original_url: str, manifest, mode: str) -> str:
    """Produce a disclosed copy of the original next to it in B2.

    Returns the plain object URL of the disclosed copy.
    """
    if mode not in DISCLOSURE_MODES:
        raise ValueError(f"Unknown disclosure mode: {mode}")

    client = _s3_client()
    key = _bucket_key(original_url)
    data = client.get_object(Bucket=B2_BUCKET_NAME, Key=key)["Body"].read()

    if mode == "visible":
        data = stamp_visible_badge(data)

    with TemporaryDirectory() as tmp:
        source = Path(tmp) / "asset.png"
        source.write_bytes(data)
        embedded = PngHandler().embed(source, manifest)
        data = embedded.read_bytes()

    stem, _, _ = key.rpartition(".")
    disclosed_key = f"{stem}.{mode}.png"
    client.put_object(
        Bucket=B2_BUCKET_NAME,
        Key=disclosed_key,
        Body=data,
        ContentType="image/png",
    )
    return f"https://s3.{B2_REGION}.backblazeb2.com/{B2_BUCKET_NAME}/{disclosed_key}"
