import hashlib
import io
import struct
from pathlib import Path
from uuid import UUID

from PIL import Image

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
        if raw_bytes.startswith((b"\xff\xd8", b"\x89PNG\r\n\x1a\n")):
            if size > 5 * 1024 * 1024:
                raise ValueError("Image exceeds maximum allowed size of 5 MB")

            # Extract dimensions for PNG
            if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n") and len(raw_bytes) >= 24:
                dimensions = struct.unpack(">II", raw_bytes[16:24])
            elif raw_bytes.startswith(b"\xff\xd8"):
                try:
                    with Image.open(io.BytesIO(raw_bytes)) as img:
                        dimensions = img.size
                except (OSError, ValueError):
                    pass
                if dimensions is None:
                    # JPEG SOF marker parser
                    idx = 2
                    while idx < len(raw_bytes) - 8:
                        if raw_bytes[idx] != 0xFF:
                            idx += 1
                            continue
                        marker = raw_bytes[idx + 1]
                        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                            h, w = struct.unpack(">HH", raw_bytes[idx + 5 : idx + 9])
                            dimensions = (w, h)
                            break
                        length = struct.unpack(">H", raw_bytes[idx + 2 : idx + 4])[0]
                        idx += 2 + length

            if dimensions:
                width, height = dimensions
                if max(width, height) > 2048:
                    raise ValueError(f"Image long edge ({max(width, height)}px) exceeds 2048px limit")
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
