"""Google Cloud Storage implementation of BlobRepository (CLOUD profile).

Bytes still arrive through the API-mediated route (PUT /media/upload/{id}), so web
and seed clients are unchanged; this adapter only replaces where they are kept.
"""

import asyncio
from typing import Any
from uuid import UUID

from google.api_core.exceptions import NotFound

from apps.api.adapters.blob.processing import normalize_asset, resolve_media_base_url
from apps.api.ports.blob import BlobRepository

OCTET_STREAM = "application/octet-stream"
MAGIC_CONTENT_TYPES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"%PDF-", "application/pdf"),
)


def sniff_content_type(data: bytes) -> str:
    """Object metadata for direct bucket reads; the API serves the media record's MIME type."""
    for magic, content_type in MAGIC_CONTENT_TYPES:
        if data.startswith(magic):
            return content_type
    return OCTET_STREAM


class GCSBlobRepository(BlobRepository):
    def __init__(
        self,
        bucket_name: str,
        client: Any | None = None,
        project_id: str | None = None,
        base_url: str = "http://localhost:8000/media",
        prefix: str = "media",
    ) -> None:
        if not bucket_name:
            raise ValueError("GCSBlobRepository requires a bucket name (MEDIA_BUCKET)")
        if client is None:
            from google.cloud import storage

            client = storage.Client(project=project_id)
        self.bucket_name = bucket_name
        self.prefix = prefix.strip("/")
        self.base_url = resolve_media_base_url(base_url)
        self._bucket = client.bucket(bucket_name)

    def _blob(self, media_id: UUID) -> Any:
        return self._bucket.blob(f"{self.prefix}/{media_id}.bin")

    async def _upload(self, media_id: UUID, data: bytes) -> None:
        await asyncio.to_thread(
            self._blob(media_id).upload_from_string, data, content_type=sniff_content_type(data)
        )

    async def prepare_upload(self, media_id: UUID, filename: str, mime_type: str) -> str:
        return f"{self.base_url}/upload/{media_id}"

    async def store_upload(self, media_id: UUID, data: bytes) -> None:
        await self._upload(media_id, data)

    async def finalize_upload(
        self, media_id: UUID, raw_bytes: bytes | None = None
    ) -> tuple[str, int, tuple[int, int] | None]:
        if raw_bytes is None:
            try:
                raw_bytes = await self.read_bytes(media_id)
            except FileNotFoundError as e:
                raise FileNotFoundError(f"Media file for {media_id} not uploaded") from e

        asset = normalize_asset(raw_bytes)
        await self._upload(media_id, asset.data)
        return asset.sha256, asset.size, asset.dimensions

    async def read_bytes(self, media_id: UUID) -> bytes:
        try:
            return await asyncio.to_thread(self._blob(media_id).download_as_bytes)
        except NotFound as e:
            raise FileNotFoundError(f"Media {media_id} not found") from e

    async def get_download_url(self, media_id: UUID, expires_in_seconds: int = 600) -> str:
        return f"{self.base_url}/download/{media_id}?expires={expires_in_seconds}"
