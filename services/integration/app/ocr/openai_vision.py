"""OpenAI-compatible Vision (OpenAI / xAI Grok) → structured ТОРГ-12 / УПД JSON."""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты извлекаешь данные из фото российских товарных накладных ТОРГ-12 и УПД.
Верни ТОЛЬКО валидный JSON без markdown-оформления.
Если поле не видно — null. Не выдумывай строки.
Даты в формате YYYY-MM-DD. Числа — number.
document_type: "torg12" | "upd" | "unknown".
warnings: массив {code, message, line_no|null}; code из:
LOW_CONFIDENCE, DOCUMENT_TYPE_UNCERTAIN, HEADER_INCOMPLETE, LINE_INCOMPLETE,
TOTALS_MISMATCH, POSSIBLE_DUPLICATE, UNREADABLE_REGION, OTHER.
overall_confidence: число 0..1.
"""

USER_INSTRUCTION = """Извлеки документ в JSON такой формы:
{
  "document_type": "torg12",
  "header": {
    "number": "string|null",
    "date": "YYYY-MM-DD|null",
    "supplier": {"name": "string|null", "inn": "string|null", "kpp": "string|null", "address": "string|null"},
    "buyer": {"name": "string|null", "inn": "string|null", "kpp": "string|null", "address": "string|null"},
    "consignee": {"name": "string|null", "inn": "string|null", "kpp": "string|null", "address": "string|null"},
    "currency": "RUB",
    "contract_number": null,
    "contract_date": null
  },
  "lines": [
    {
      "line_no": 1,
      "name": "string|null",
      "vendor_code": "string|null",
      "unit": "string|null",
      "quantity": 0,
      "price": 0,
      "amount": 0,
      "vat_rate": 20,
      "vat_amount": 0,
      "amount_with_vat": 0,
      "amount_includes_vat": false,
      "confidence": 0.0
    }
  ],
  "totals": {"lines_count": 0, "amount": 0, "vat_amount": 0, "amount_with_vat": 0},
  "warnings": [],
  "overall_confidence": 0.0
}
"""


def _guess_mime(filename: str, content_type: str | None) -> str:
    if content_type and content_type.startswith("image/"):
        return content_type
    name = filename.lower()
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith((".tif", ".tiff")):
        return "image/tiff"
    return "image/jpeg"


def _data_url(data: bytes, mime: str) -> str:
    b64 = base64.standard_b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _build_user_content(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{"type": "text", "text": USER_INSTRUCTION}]
    image_count = 0
    for f in files:
        name = f.get("filename") or "file.jpg"
        ctype = f.get("content_type")
        data: bytes = f["data"]
        mime = _guess_mime(name, ctype)
        if not mime.startswith("image/"):
            if not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"):
                continue
            mime = "image/jpeg" if data[:3] == b"\xff\xd8\xff" else "image/png"
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": _data_url(data, mime), "detail": "high"},
            }
        )
        image_count += 1
    if image_count == 0:
        raise RuntimeError("No images to send to Vision API")
    return content


async def recognize_openai_compatible(
    *,
    api_key: str,
    model: str,
    base_url: str,
    provider_label: str,
    files: list[dict[str, Any]],
    use_json_object_format: bool = True,
) -> dict[str, Any]:
    content = _build_user_content(files)
    payload: dict[str, Any] = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
    }
    if use_json_object_format:
        payload["response_format"] = {"type": "json_object"}

    url = base_url.rstrip("/") + "/chat/completions"
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if resp.status_code >= 400:
            # retry without response_format if provider rejects it
            if use_json_object_format and resp.status_code in (400, 422):
                logger.warning("%s rejected response_format, retrying plain", provider_label)
                return await recognize_openai_compatible(
                    api_key=api_key,
                    model=model,
                    base_url=base_url,
                    provider_label=provider_label,
                    files=files,
                    use_json_object_format=False,
                )
            logger.error("%s error %s: %s", provider_label, resp.status_code, resp.text[:800])
            resp.raise_for_status()
        body = resp.json()

    raw = body["choices"][0]["message"]["content"]
    if isinstance(raw, list):
        # some APIs return content parts
        raw = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in raw)
    parsed = _extract_json(raw)
    parsed["ocr_provider"] = f"{provider_label}:{model}"
    parsed.setdefault("warnings", [])
    parsed.setdefault("overall_confidence", 0.5)
    parsed.setdefault("markdown", "")
    return parsed


async def recognize_with_openai(settings: Settings, files: list[dict[str, Any]]) -> dict[str, Any]:
    api_key = settings.openai_api_key or settings.ocr_api_key
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is empty")
    model = settings.openai_vision_model or "gpt-4o"
    return await recognize_openai_compatible(
        api_key=api_key,
        model=model,
        base_url="https://api.openai.com/v1",
        provider_label="openai",
        files=files,
    )


async def recognize_with_grok(settings: Settings, files: list[dict[str, Any]]) -> dict[str, Any]:
    api_key = settings.xai_api_key
    if not api_key:
        raise RuntimeError("XAI_API_KEY is empty")
    model = settings.xai_vision_model or "grok-2-vision-1212"
    return await recognize_openai_compatible(
        api_key=api_key,
        model=model,
        base_url=settings.xai_base_url or "https://api.x.ai/v1",
        provider_label="grok",
        files=files,
    )
