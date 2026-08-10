"""Recognition pipeline: anydoc (+ Firecrawl OCR for scans) → result.json fields."""

from __future__ import annotations

import io
import logging
from typing import Any

import anydoc
import img2pdf
from PIL import Image

from app.config import Settings
from app.ocr.anydoc_convert import bytes_to_markdown, is_anydoc_candidate
from app.ocr.firecrawl_parse import parse_pdf_ocr
from app.ocr.markdown_to_result import markdown_to_result_fields
from app.ocr.openai_vision import recognize_with_grok, recognize_with_openai
from app.ocr.yandex_gpt import recognize_with_yandexgpt

logger = logging.getLogger(__name__)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def _is_image(filename: str, content_type: str | None) -> bool:
    name = filename.lower()
    if any(name.endswith(ext) for ext in IMAGE_EXT):
        return True
    if content_type and content_type.lower().startswith("image/"):
        return True
    return False


def images_to_pdf(images: list[bytes]) -> bytes:
    """Build a PDF from image bytes (RGB JPEG pages)."""
    pages: list[bytes] = []
    for raw in images:
        img = Image.open(io.BytesIO(raw))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        elif img.mode == "L":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        pages.append(buf.getvalue())
    return img2pdf.convert(pages)


async def extract_markdown_from_files(
    settings: Settings,
    files: list[dict[str, Any]],
) -> tuple[str, str, list[dict[str, Any]]]:
    """
    files: [{filename, content_type, data: bytes}]
    Returns (markdown, provider, warnings)
    """
    warnings: list[dict[str, Any]] = []
    md_parts: list[str] = []
    provider = "anydoc"
    image_blobs: list[bytes] = []

    for f in files:
        name = f.get("filename") or "file.bin"
        ctype = f.get("content_type")
        data: bytes = f["data"]

        if _is_image(name, ctype):
            image_blobs.append(data)
            continue

        if is_anydoc_candidate(name, ctype) or anydoc.format_from_bytes(data):
            try:
                md_parts.append(bytes_to_markdown(data, name))
                continue
            except anydoc.ConvertError as exc:
                warnings.append(
                    {"code": "OTHER", "message": f"anydoc failed for {name}: {exc}", "line_no": None}
                )

        warnings.append(
            {"code": "UNREADABLE_REGION", "message": f"Unsupported file for anydoc: {name}", "line_no": None}
        )

    if image_blobs:
        pdf_bytes = images_to_pdf(image_blobs)
        # 1) try anydoc on PDF (works only for text PDFs; image-only → Unsupported)
        try:
            md_parts.append(bytes_to_markdown(pdf_bytes, "packet.pdf"))
            provider = "anydoc+img2pdf"
        except anydoc.ConvertError:
            # 2) Firecrawl Parse OCR (official companion for scanned pages)
            if settings.firecrawl_api_key:
                md = await parse_pdf_ocr(settings.firecrawl_api_key, pdf_bytes, "packet.pdf")
                md_parts.append(md)
                provider = "firecrawl-parse-ocr"
            else:
                warnings.append(
                    {
                        "code": "OTHER",
                        "message": (
                            "Фото/скан: anydoc не делает OCR. "
                            "Задайте FIRECRAWL_API_KEY для Firecrawl Parse OCR "
                            "(https://docs.firecrawl.dev/features/parse)."
                        ),
                        "line_no": None,
                    }
                )

    markdown = "\n\n".join(p for p in md_parts if p and p.strip())
    return markdown, provider, warnings


async def recognize_packet_files(
    settings: Settings,
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    mode = (settings.ocr_mode or "stub").lower()
    if mode in ("openai", "gpt"):
        return await recognize_with_openai(settings, files)
    if mode in ("grok", "xai"):
        return await recognize_with_grok(settings, files)
    if mode in ("yandexgpt", "yandex", "yc"):
        return await recognize_with_yandexgpt(settings, files)

    markdown, provider, pipe_warnings = await extract_markdown_from_files(settings, files)
    if not markdown.strip():
        return {
            "document_type": "unknown",
            "header": {"number": None, "date": None, "supplier": None, "buyer": None, "currency": "RUB"},
            "lines": [],
            "totals": {},
            "warnings": pipe_warnings
            or [{"code": "OTHER", "message": "Empty recognition output", "line_no": None}],
            "overall_confidence": 0.0,
            "ocr_provider": provider,
            "markdown": "",
        }

    fields = markdown_to_result_fields(markdown)
    fields["warnings"] = (fields.get("warnings") or []) + pipe_warnings
    fields["ocr_provider"] = provider
    fields["markdown"] = markdown
    return fields
