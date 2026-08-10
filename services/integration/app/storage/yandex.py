"""Yandex Disk REST adapter (personal 360 OAuth).

API docs: https://yandex.ru/dev/disk-api/doc/ru/
Upload flow: GET upload href → PUT file bytes.
"""

from __future__ import annotations

import logging

import httpx

from app.config import Settings
from app.storage.base import StorageBackend

logger = logging.getLogger(__name__)

TOKEN_URL = "https://oauth.yandex.ru/token"
DISK_API = "https://cloud-api.yandex.net/v1/disk"


class YandexDiskStorage(StorageBackend):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._access_token: str | None = None

    async def _refresh_access_token(self) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.settings.yandex_refresh_token,
                    "client_id": self.settings.yandex_client_id,
                    "client_secret": self.settings.yandex_client_secret,
                },
            )
            resp.raise_for_status()
            self._access_token = resp.json()["access_token"]
            return self._access_token

    async def _token(self) -> str:
        if self._access_token:
            return self._access_token
        return await self._refresh_access_token()

    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"OAuth {token}"}

    async def ensure_dir(self, path: str) -> None:
        token = await self._token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.put(
                f"{DISK_API}/resources",
                params={"path": path},
                headers=self._headers(token),
            )
            # 201 created, 409 already exists
            if resp.status_code not in (201, 409):
                resp.raise_for_status()

    async def put_bytes(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        # Ensure parent folders exist (best-effort, nested create)
        parts = path.strip("/").split("/")
        cur = ""
        for part in parts[:-1]:
            cur = f"{cur}/{part}"
            await self.ensure_dir(cur)

        token = await self._token()
        last_err: Exception | None = None
        # verify=False: Browsec/MITM often breaks TLS to Yandex upload hosts
        for verify in (True, False):
            try:
                async with httpx.AsyncClient(timeout=120, verify=verify) as client:
                    href_resp = await client.get(
                        f"{DISK_API}/resources/upload",
                        params={"path": path, "overwrite": "true"},
                        headers=self._headers(token),
                    )
                    href_resp.raise_for_status()
                    href = href_resp.json()["href"]
                    put_resp = await client.put(href, content=data, headers={"Content-Type": content_type})
                    put_resp.raise_for_status()
                return path
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning("Yandex put_bytes verify=%s failed for %s: %s", verify, path, exc)
        raise RuntimeError(f"Yandex Disk upload failed: {last_err}") from last_err

    async def get_bytes(self, path: str) -> bytes:
        token = await self._token()
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            meta = await client.get(
                f"{DISK_API}/resources/download",
                params={"path": path},
                headers=self._headers(token),
            )
            meta.raise_for_status()
            href = meta.json()["href"]
            file_resp = await client.get(href)
            file_resp.raise_for_status()
            return file_resp.content
