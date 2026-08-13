"""MAX Bot API client (platform-api2.max.ru) for pilot long-polling."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

DEFAULT_BASE = "https://platform-api2.max.ru"


class MaxClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.token = self.settings.max_bot_token
        self.base = (self.settings.max_api_base_url or DEFAULT_BASE).rstrip("/")
        if not self.token:
            raise RuntimeError("MAX_BOT_TOKEN is empty")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.token,
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout: float = 60,
    ) -> Any:
        url = f"{self.base}{path}"
        last_err: Exception | None = None
        # Corporate MITM / Минцифры CA quirks: try verify then insecure fallback
        for verify in (True, False):
            try:
                async with httpx.AsyncClient(timeout=timeout, verify=verify) as client:
                    resp = await client.request(
                        method,
                        url,
                        headers=self._headers(),
                        params=params,
                        json=json_body,
                    )
                    if resp.status_code >= 400:
                        logger.error("MAX %s %s -> %s %s", method, path, resp.status_code, resp.text[:500])
                        resp.raise_for_status()
                    if not resp.content:
                        return {}
                    return resp.json()
            except httpx.HTTPStatusError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning("MAX %s %s verify=%s failed: %s", method, path, verify, exc)
        raise RuntimeError(f"MAX API unreachable: {last_err}") from last_err

    async def get_me(self) -> dict[str, Any]:
        return await self._request("GET", "/me")

    async def list_subscriptions(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/subscriptions")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            subs = data.get("subscriptions") or data.get("list") or []
            return list(subs) if isinstance(subs, list) else []
        return []

    async def unsubscribe(self, url: str) -> None:
        await self._request("DELETE", "/subscriptions", params={"url": url})

    async def clear_webhook_subscriptions(self) -> int:
        """Long polling is disabled while a webhook subscription is active."""
        removed = 0
        for sub in await self.list_subscriptions():
            url = ""
            if isinstance(sub, dict):
                url = str(sub.get("url") or "")
            if not url:
                continue
            try:
                await self.unsubscribe(url)
                removed += 1
                logger.info("Unsubscribed MAX webhook %s", url)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to unsubscribe %s", url)
        return removed

    async def get_updates(
        self,
        *,
        marker: int | None = None,
        limit: int = 100,
        timeout: int = 30,
        types: list[str] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "timeout": timeout}
        if marker is not None:
            params["marker"] = marker
        if types:
            params["types"] = ",".join(types)
        # Long poll needs timeout > server timeout
        return await self._request("GET", "/updates", params=params, timeout=float(timeout) + 15)

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        *,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """Send text (+ optional inline keyboard). Prefer user_id for dialogs."""
        body: dict[str, Any] = {"text": text}
        if reply_markup:
            body["attachments"] = [_telegram_keyboard_to_max(reply_markup)]
        params: dict[str, Any] = {}
        if user_id is not None:
            params["user_id"] = user_id
        else:
            params["chat_id"] = chat_id
        return await self._request("POST", "/messages", params=params, json_body=body)

    async def answer_callback(self, callback_query_id: str, text: str | None = None) -> None:
        body: dict[str, Any] = {}
        if text:
            # One-shot notification if supported; otherwise no-op message change
            body["notification"] = text
        try:
            await self._request(
                "POST",
                "/answers",
                params={"callback_id": callback_query_id},
                json_body=body or None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("MAX answer_callback ignored: %s", exc)

    async def download_url(self, url: str) -> bytes:
        last_err: Exception | None = None
        for verify in (True, False):
            try:
                async with httpx.AsyncClient(timeout=120, verify=verify, follow_redirects=True) as client:
                    resp = await client.get(url, headers={"Authorization": self.token})
                    resp.raise_for_status()
                    return resp.content
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning("MAX download_url verify=%s failed: %s", verify, exc)
        raise RuntimeError(f"Failed to download MAX attachment: {last_err}") from last_err


def _telegram_keyboard_to_max(reply_markup: dict[str, Any]) -> dict[str, Any]:
    """Convert Telegram-style inline_keyboard to MAX inline_keyboard attachment."""
    rows = reply_markup.get("inline_keyboard") or []
    max_rows: list[list[dict[str, str]]] = []
    for row in rows:
        max_row: list[dict[str, str]] = []
        for btn in row:
            text = str(btn.get("text") or "")
            payload = str(btn.get("callback_data") or "noop")
            max_row.append({"type": "callback", "text": text, "payload": payload})
        if max_row:
            max_rows.append(max_row)
    return {"type": "inline_keyboard", "payload": {"buttons": max_rows}}


def describe_max_client() -> str:
    s = get_settings()
    return f"base={s.max_api_base_url} token={'yes' if s.max_bot_token else 'no'}"
