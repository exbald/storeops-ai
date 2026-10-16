from pathlib import Path
from uuid import UUID

from apps.api.adapters.blob.processing import normalize_asset, resolve_media_base_url
from apps.api.adapters.blob.signing import (
    DOWNLOAD_METHOD,
    LOCAL_DEV_SIGNING_KEY,
    UPLOAD_METHOD,
    UPLOAD_URL_TTL_SECONDS,
    MediaUrlSigner,
)
from apps.api.ports.blob import BlobRepository


class LocalFileSystemBlobRepository(BlobRepository):
    def __init__(
        self,
        base_dir: str | Path = ".local_storage/media",
        base_url: str = "http://localhost:8000/media",
        signer: MediaUrlSigner | None = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        # LOCAL profile adapter: without an explicit signer it uses the fixed dev key.
        self.signer = signer or MediaUrlSigner(LOCAL_DEV_SIGNING_KEY)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = resolve_media_base_url(base_url)

    def _file_path(self, media_id: UUID) -> Path:
        return self.base_dir / f"{media_id}.bin"

    async def prepare_upload(self, media_id: UUID, filename: str, mime_type: str) -> str:
        return self.signer.signed_url(
            self.base_url, UPLOAD_METHOD, media_id, UPLOAD_URL_TTL_SECONDS
        )

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
        return self.signer.signed_url(self.base_url, DOWNLOAD_METHOD, media_id, expires_in_seconds)

    def verify_signed_url(
        self, method: str, media_id: UUID, expires: str | None, signature: str | None
    ) -> bool:
        return self.signer.verify(method, media_id, expires, signature)
