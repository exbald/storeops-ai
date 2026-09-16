import hashlib
import io
import os
from pathlib import Path
from uuid import UUID

from PIL import Image, ImageOps

from apps.api.ports.blob import BlobRepository


class LocalFileSystemBlobRepository(BlobRepository):
    def __init__(self, base_dir: str | Path = ".local_storage/media", base_url: str = "http://localhost:8000/media") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url.rstrip("/")

    def _file_path(self, media_id: UUID) -> Path:
        return self.base_dir / f"{media_id}.bin"

    async def prepare_upload(self, media_id: UUID, filename: str, mime_type: str) -> str:
        # Return local upload endpoint or path
        return f"{self.base_url}/upload/{media_id}"

    async def finalize_upload(
        self, media_id: UUID, raw_bytes: bytes | None = None
    ) -> tuple[str, int, tuple[int, int] | None]:
        path = self._file_path(media_id)
        if raw_bytes is None:
            if not path.exists():
                raise FileNotFoundError(f"Media file for {media_id} not uploaded")
            raw_bytes = path.read_bytes()

        size = len(raw_bytes)
        dimensions: tuple[int, int] | None = None

        # Try image processing if looks like JPEG or PNG
        if raw_bytes.startswith(b"\xff\xd8") or raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            if size > 5 * 1024 * 1024:
                raise ValueError("Image exceeds maximum allowed size of 5 MB")
            try:
                with Image.open(io.BytesIO(raw_bytes)) as img:
                    # Normalize orientation using EXIF transpose
                    transposed = ImageOps.exif_transpose(img)
                    dimensions = transposed.size
                    width, height = dimensions
                    if max(width, height) > 2048:
                        raise ValueError(f"Image long edge ({max(width, height)}px) exceeds 2048px limit")
                    # Strip EXIF by saving cleanly to buffer
                    out_buf = io.BytesIO()
                    img_format = img.format or "JPEG"
                    transposed.save(out_buf, format=img_format)
                    raw_bytes = out_buf.getvalue()
                    size = len(raw_bytes)
            except Exception as e:
                if "exceeds" in str(e):
                    raise
                # Non-image or corrupted
                pass
        elif raw_bytes.startswith(b"%PDF"):
            if size > 10 * 1024 * 1024:
                raise ValueError("PDF exceeds maximum allowed size of 10 MB")
        else:
            # CSV or generic data limit
            if size > 10 * 1024 * 1024:
                raise ValueError("Asset exceeds maximum allowed size of 10 MB")

        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        path.write_bytes(raw_bytes)
        return sha256, size, dimensions

    async def read_bytes(self, media_id: UUID) -> bytes:
        path = self._file_path(media_id)
        if not path.exists():
            raise FileNotFoundError(f"Media {media_id} not found")
        return path.read_bytes()

    async def get_download_url(self, media_id: UUID, expires_in_seconds: int = 600) -> str:
        return f"{self.base_url}/{media_id}?expires={expires_in_seconds}"
