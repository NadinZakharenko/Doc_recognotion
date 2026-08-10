"""Firecrawl /v2/parse — OCR for scanned PDFs/images (companion to anydoc)."""

from __future__ import annotations

import json
import logging

import httpx

logger = logging.getLogger(__name__)

PARSE_URL = "https://api.firecrawl.dev/v2/parse"


async def parse_pdf_ocr(api_key: str, pdf_bytes: bytes, filename: str = "document.pdf") -> str:
    """Upload PDF and return markdown (OCR mode for scanned pages)."""
    options = {
        "formats": ["markdown"],
        "parsers": [{"type": "pdf", "mode": "ocr"}],
    }
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            PARSE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (filename, pdf_bytes, "application/pdf")},
            data={"options": json.dumps(options)},
        )
        if resp.status_code >= 400:
            logger.error("Firecrawl parse failed: %s %s", resp.status_code, resp.text[:500])
            resp.raise_for_status()
        payload = resp.json()
        # Response shapes vary; try common paths
        data = payload.get("data") or payload
        md = data.get("markdown")
        if not md and isinstance(data.get("data"), dict):
            md = data["data"].get("markdown")
        if not md:
            raise RuntimeError(f"Firecrawl parse returned no markdown: {str(payload)[:400]}")
        return md
