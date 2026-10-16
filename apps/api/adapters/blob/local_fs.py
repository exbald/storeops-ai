from pathlib import Path
from uuid import UUID

from apps.api.adapters.blob.processing import normalize_asset, resolve_media_base_url
from apps.api.ports.blob import BlobRepository


class LocalFileSystemBlobRepository(BlobRepository):
    def __init__(
        self,
        base_dir: str | Path = ".local_storage/media",
        base_url: str = "http://localhost:8000/media",
    ) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = resolve_media_base_url(base_url)

    def _file_path(self, media_id: UUID) -> Path:
        return self.base_dir / f"{media_id}.bin"

    async def prepare_upload(self, media_id: UUID, filename: str, mime_type: str) -> str:
        return f"{self.base_url}/upload/{media_id}"

    async def store_upload(self, media_id: UUID, data: bytes) -> None:
        self._file_path(media_id).write_bytes(data)

    async def finalize_upload(
        self, media_id: UUID, raw_bytes: bytes | None = None
    ) -> tuple[str, int, tuple[int, int] | None]:
        path = self._file_path(media_id)
        if raw_bytes is None:
            if not path.exists():
                raise FileNotFoundError(f"Media file for {media_id} not uploaded")
            raw_bytes = path.read_bytes()

        asset = normalize_asset(raw_bytes)
        path.write_bytes(asset.data)
        return asset.sha256, asset.size, asset.dimensions

    async def read_bytes(self, media_id: UUID) -> bytes:
        path = self._file_path(media_id)
        if not path.exists():
            raise FileNotFoundError(f"Media {media_id} not found")
        return path.read_bytes()

    async def get_download_url(self, media_id: UUID, expires_in_seconds: int = 600) -> str:
        return f"{self.base_url}/download/{media_id}?expires={expires_in_seconds}"
