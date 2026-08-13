"""Detect image format by magic bytes and normalize to JPEG for Disk/OCR."""

from __future__ import annotations

import io
import logging

from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)


def detect_image_format(data: bytes) -> str | None:
    if len(data) < 12:
        return None
    if data[:3] == b"\xff\xd8\xff":
        return "JPEG"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "GIF"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    if data[:2] == b"BM":
        return "BMP"
    # ISO BMFF (HEIC/HEIF): ....ftyp....
    if data[4:8] == b"ftyp":
        brand = data[8:12].lower()
        if brand in (b"heic", b"heif", b"mif1", b"msf1", b"heix"):
            return "HEIC"
    return None


def to_jpeg_bytes(data: bytes, *, quality: int = 90) -> tuple[bytes, str]:
    """
    Return (bytes, content_type).
    Already-JPEG payloads are returned as-is; others are re-encoded to JPEG.
    """
    fmt = detect_image_format(data)
    if fmt == "JPEG":
        return data, "image/jpeg"

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except UnidentifiedImageError as exc:
        raise RuntimeError(
            f"Unsupported or corrupt image (detected={fmt or 'unknown'}, size={len(data)})"
        ) from exc

    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    out = buf.getvalue()
    logger.info(
        "Normalized image %s → JPEG (%s → %s bytes)",
        fmt or img.format or "unknown",
        len(data),
        len(out),
    )
    return out, "image/jpeg"
