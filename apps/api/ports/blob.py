from typing import Protocol
from uuid import UUID


class BlobRepository(Protocol):
    async def prepare_upload(self, media_id: UUID, filename: str, mime_type: str) -> str:
        """Prepare upload destination and return upload URL."""
        ...

    async def store_upload(self, media_id: UUID, data: bytes) -> None:
        """Persist raw bytes received by the API-mediated upload route."""
        ...

    async def finalize_upload(
        self, media_id: UUID, raw_bytes: bytes | None = None
    ) -> tuple[str, int, tuple[int, int] | None]:
        """Validate uploaded asset, stripping EXIF for images.

        Returns (sha256_hex, size_bytes, (width, height) or None).
        """
        ...

    async def read_bytes(self, media_id: UUID) -> bytes:
        """Read asset bytes."""
        ...

    async def get_download_url(self, media_id: UUID, expires_in_seconds: int = 600) -> str:
        """Generate expiring URL to download asset."""
        ...

    def verify_signed_url(
        self, method: str, media_id: UUID, expires: str | None, signature: str | None
    ) -> bool:
        """True when (expires, signature) is an unexpired grant this repository issued
        for `method` ("PUT" upload / "GET" download) on media_id."""
        ...
