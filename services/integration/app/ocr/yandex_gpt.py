"""Yandex Cloud: Vision OCR + YandexGPT → structured ТОРГ-12 / УПД JSON."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx

from app.config import Settings
from app.ocr.image_normalize import to_jpeg_bytes
from app.ocr.openai_vision import SYSTEM_PROMPT, USER_INSTRUCTION, _extract_json

logger = logging.getLogger(__name__)

OCR_URL = "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText"
COMPLETION_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
CHAT_URL = "https://llm.api.cloud.yandex.net/v1/chat/completions"


def _auth_headers(settings: Settings) -> dict[str, str]:
    api_key = settings.yandex_cloud_api_key
    if not api_key:
        raise RuntimeError("YANDEX_CLOUD_API_KEY is empty")
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }
    if settings.yandex_folder_id:
        headers["x-folder-id"] = settings.yandex_folder_id
    return headers


def _model_uri(settings: Settings) -> str:
    folder = settings.yandex_folder_id
    model = settings.yandex_gpt_model or "yandexgpt/latest"
    if model.startswith("gpt://"):
        return model
    if not folder:
        raise RuntimeError("YANDEX_FOLDER_ID is required for modelUri")
    return f"gpt://{folder}/{model.lstrip('/')}"


def _mime_to_ocr(mime: str) -> str:
    m = mime.lower()
    if "png" in m:
        return "PNG"
    if "pdf" in m:
        return "PDF"
    if "webp" in m:
        return "WEBP"
    return "JPEG"


async def _ocr_image(settings: Settings, data: bytes, mime: str) -> str:
    payload = {
        "mimeType": _mime_to_ocr(mime),
        "languageCodes": ["ru", "en"],
        "model": settings.yandex_ocr_model or "table",
        "content": base64.standard_b64encode(data).decode("ascii"),
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(OCR_URL, headers=_auth_headers(settings), json=payload)
        if resp.status_code >= 400:
            logger.error("Yandex OCR error %s: %s", resp.status_code, resp.text[:800])
            resp.raise_for_status()
        body = resp.json()

    # Sync recognizeText shapes vary; collect fullText aggressively
    texts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("fullText"), str) and node["fullText"].strip():
                texts.append(node["fullText"])
            if isinstance(node.get("text"), str) and node["text"].strip() and len(node["text"]) > 3:
                texts.append(node["text"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(body)
    # Prefer longest unique chunks
    uniq: list[str] = []
    seen: set[str] = set()
    for t in sorted(texts, key=len, reverse=True):
        key = t.strip()
        if key and key not in seen:
            seen.add(key)
            uniq.append(key)
        if len(uniq) >= 5:
            break
    joined = "\n\n".join(uniq).strip()
    if not joined:
        raise RuntimeError(f"Yandex OCR returned empty text: {str(body)[:400]}")
    return joined


async def _gpt_structure(settings: Settings, ocr_text: str) -> dict[str, Any]:
    user_text = (
        f"{USER_INSTRUCTION}\n\n"
        "Ниже текст, полученный OCR с фото документа. Извлеки JSON.\n\n"
        f"--- OCR TEXT ---\n{ocr_text[:30000]}\n--- END ---"
    )
    payload = {
        "modelUri": _model_uri(settings),
        "completionOptions": {
            "stream": False,
            "temperature": 0.0,
            "maxTokens": "8000",
        },
        "messages": [
            {"role": "system", "text": SYSTEM_PROMPT},
            {"role": "user", "text": user_text},
        ],
    }
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(COMPLETION_URL, headers=_auth_headers(settings), json=payload)
        if resp.status_code >= 400:
            logger.error("YandexGPT error %s: %s", resp.status_code, resp.text[:800])
            resp.raise_for_status()
        body = resp.json()

    try:
        raw = body["result"]["alternatives"][0]["message"]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected YandexGPT response: {str(body)[:500]}") from exc

    parsed = _extract_json(raw)
    parsed["ocr_provider"] = f"yandexgpt:{settings.yandex_gpt_model or 'yandexgpt/latest'}+ocr:{settings.yandex_ocr_model or 'table'}"
    parsed.setdefault("warnings", [])
    parsed.setdefault("overall_confidence", 0.5)
    parsed["markdown"] = ocr_text[:5000]
    return parsed


async def _vision_gemma(settings: Settings, files: list[dict[str, Any]]) -> dict[str, Any]:
    """Optional single-step vision via AI Studio OpenAI-compatible chat (gemma-3-27b-it)."""
    folder = settings.yandex_folder_id
    if not folder:
        raise RuntimeError("YANDEX_FOLDER_ID required for vision model")
    model = settings.yandex_vision_model or f"gpt://{folder}/gemma-3-27b-it/latest"
    if not model.startswith("gpt://"):
        model = f"gpt://{folder}/{model}"

    content: list[dict[str, Any]] = [{"type": "text", "text": f"{SYSTEM_PROMPT}\n\n{USER_INSTRUCTION}"}]
    for f in files:
        data, mime = to_jpeg_bytes(f["data"])
        b64 = base64.standard_b64encode(data).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            }
        )

    payload = {
        "model": model,
        "temperature": 0,
        "messages": [{"role": "user", "content": content}],
    }
    headers = _auth_headers(settings)
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(CHAT_URL, headers=headers, json=payload)
        if resp.status_code >= 400:
            logger.error("Yandex vision chat error %s: %s", resp.status_code, resp.text[:800])
            resp.raise_for_status()
        body = resp.json()
    raw = body["choices"][0]["message"]["content"]
    if isinstance(raw, list):
        raw = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in raw)
    parsed = _extract_json(raw)
    parsed["ocr_provider"] = f"yandex-vision:{model}"
    parsed.setdefault("warnings", [])
    parsed.setdefault("overall_confidence", 0.5)
    parsed.setdefault("markdown", "")
    return parsed


async def recognize_with_yandexgpt(settings: Settings, files: list[dict[str, Any]]) -> dict[str, Any]:
    mode = (settings.yandex_recognize_mode or "ocr_gpt").lower()
    if mode in ("vision", "gemma"):
        return await _vision_gemma(settings, files)

    ocr_parts: list[str] = []
    for i, f in enumerate(files, start=1):
        name = f.get("filename") or f"file_{i}.jpg"
        data, mime = to_jpeg_bytes(f["data"])
        text = await _ocr_image(settings, data, mime)
        ocr_parts.append(f"=== PAGE {i} ({name}) ===\n{text}")

    if not ocr_parts:
        raise RuntimeError("No images for Yandex OCR")
    return await _gpt_structure(settings, "\n\n".join(ocr_parts))
