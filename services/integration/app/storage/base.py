from abc import ABC, abstractmethod
from pathlib import PurePosixPath


def build_packet_path(
    disk_root: str,
    org_id: str,
    warehouse_id: str,
    user_label: str,
    date_str: str,
    packet_id: str,
) -> str:
    """Personal catalog layout from concept design."""
    root = disk_root.rstrip("/")
    return str(
        PurePosixPath(root)
        / org_id
        / warehouse_id
        / user_label
        / date_str
        / packet_id
    )


class StorageBackend(ABC):
    @abstractmethod
    async def ensure_dir(self, path: str) -> None: ...

    @abstractmethod
    async def put_bytes(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload file; return storage key/path."""

    @abstractmethod
    async def get_bytes(self, path: str) -> bytes: ...


def get_storage():
    from app.config import get_settings

    settings = get_settings()
    if settings.storage_backend == "yandex":
        from app.storage.yandex import YandexDiskStorage

        return YandexDiskStorage(settings)
    from app.storage.local import LocalStorage

    return LocalStorage(settings.local_storage_root)
