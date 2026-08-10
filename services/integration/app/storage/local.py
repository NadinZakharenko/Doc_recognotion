from pathlib import Path

import aiofiles
import aiofiles.os

from app.storage.base import StorageBackend


class LocalStorage(StorageBackend):
    """Fallback MVP storage on local disk / mounted SMB."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _abs(self, path: str) -> Path:
        rel = path.lstrip("/").replace("\\", "/")
        return self.root / rel

    async def ensure_dir(self, path: str) -> None:
        await aiofiles.os.makedirs(self._abs(path), exist_ok=True)

    async def put_bytes(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        target = self._abs(path)
        await aiofiles.os.makedirs(target.parent, exist_ok=True)
        async with aiofiles.open(target, "wb") as f:
            await f.write(data)
        return path

    async def get_bytes(self, path: str) -> bytes:
        async with aiofiles.open(self._abs(path), "rb") as f:
            return await f.read()
