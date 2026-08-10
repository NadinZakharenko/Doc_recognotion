from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class TelegramClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.token = settings.telegram_bot_token
        self.base = f"https://api.telegram.org/bot{self.token}"
        self.file_base = f"https://api.telegram.org/file/bot{self.token}"

    async def _call(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        last_err: Exception | None = None
        # verify=False fallback: corporate VPN/MITM (e.g. Browsec) breaks TLS to api.telegram.org
        for verify in (True, False):
            try:
                async with httpx.AsyncClient(timeout=60, verify=verify) as client:
                    resp = await client.post(f"{self.base}/{method}", json=payload or {})
                    data = resp.json()
                    if not data.get("ok"):
                        logger.error("Telegram API %s failed: %s", method, data)
                        raise RuntimeError(f"Telegram API error: {data}")
                    return data["result"]
            except RuntimeError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning("Telegram %s verify=%s failed: %s", method, verify, exc)
        raise RuntimeError(f"Telegram API unreachable: {last_err}") from last_err

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return await self._call("sendMessage", payload)

    async def answer_callback(self, callback_query_id: str, text: str | None = None) -> None:
        """Acknowledge button press; never fail the business flow if Telegram rejects stale query."""
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        try:
            await self._call("answerCallbackQuery", payload)
        except RuntimeError as exc:
            logger.warning("answerCallbackQuery ignored: %s", exc)

    async def get_file(self, file_id: str) -> dict[str, Any]:
        return await self._call("getFile", {"file_id": file_id})

    async def download_file(self, file_path: str) -> bytes:
        url = f"{self.file_base}/{file_path}"
        last_err: Exception | None = None
        for verify in (True, False):
            try:
                async with httpx.AsyncClient(timeout=120, verify=verify) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    return resp.content
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning("download_file verify=%s failed: %s", verify, exc)
        raise RuntimeError(f"Failed to download Telegram file: {last_err}") from last_err
