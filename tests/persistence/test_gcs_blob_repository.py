"""GCS BlobRepository adapter: API-mediated uploads persisted in Cloud Storage."""

import hashlib
import io
import threading
from uuid import uuid4

import pytest
from PIL import Image

from apps.api.adapters.blob.gcs import GCSBlobRepository
from apps.api.adapters.blob.local_fs import LocalFileSystemBlobRepository
from apps.api.adapters.blob.signing import (
    UPLOAD_METHOD,
    UPLOAD_URL_TTL_SECONDS,
    MediaUrlSigner,
)

BUCKET = "storeops-test-media"
NOW = 1_800_000_000.0


def _signer() -> MediaUrlSigner:
    return MediaUrlSigner(b"k" * 32, clock=lambda: NOW)


def _png_bytes(width: int = 64, height: int = 32) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_with_exif_orientation() -> bytes:
    img = Image.new("RGB", (40, 20), color=(200, 10, 10))
    exif = img.getexif()
    exif[0x0112] = 6  # rotate 90 CW on display
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


@pytest.fixture
def repo(fake_storage_client, monkeypatch) -> GCSBlobRepository:
    monkeypatch.delenv("MEDIA_BASE_URL", raising=False)
    monkeypatch.delenv("API_URL", raising=False)
    return GCSBlobRepository(
        bucket_name=BUCKET,
        signer=_signer(),
        client=fake_storage_client,
        base_url="https://api.example.test/media",
    )


def test_requires_bucket_name(fake_storage_client):
    with pytest.raises(ValueError, match="MEDIA_BUCKET"):
        GCSBlobRepository(bucket_name="", signer=_signer(), client=fake_storage_client)


async def test_prepare_upload_returns_signed_api_upload_route(repo):
    media_id = uuid4()
    url = await repo.prepare_upload(media_id, "shelf.png", "image/png")
    expected_query = _signer().query(UPLOAD_METHOD, media_id, UPLOAD_URL_TTL_SECONDS)
    assert url == f"https://api.example.test/media/upload/{media_id}?{expected_query}"


async def test_upload_url_matches_local_fs_shape(fake_storage_client, tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_BASE_URL", "https://api.run.app/media")
    media_id = uuid4()
    gcs = GCSBlobRepository(bucket_name=BUCKET, signer=_signer(), client=fake_storage_client)
    local = LocalFileSystemBlobRepository(base_dir=tmp_path, signer=_signer())
    assert await gcs.prepare_upload(media_id, "a.csv", "text/csv") == await local.prepare_upload(
        media_id, "a.csv", "text/csv"
    )
    assert await gcs.get_download_url(media_id, 600) == await local.get_download_url(media_id, 600)


async def test_store_upload_then_read_bytes_roundtrip(repo, fake_storage_client):
    media_id = uuid4()
    payload = b"sku,units\nA,1\n"
    await repo.store_upload(media_id, payload)

    bucket = fake_storage_client.buckets[BUCKET]
    assert bucket.objects == {f"media/{media_id}.bin": payload}
    assert await repo.read_bytes(media_id) == payload


async def test_blocking_calls_run_off_event_loop_thread(repo, fake_storage_client):
    media_id = uuid4()
    await repo.store_upload(media_id, b"x")
    await repo.read_bytes(media_id)
    loop_thread = threading.get_ident()
    thread_ids = fake_storage_client.buckets[BUCKET].thread_ids
    assert thread_ids and all(tid != loop_thread for tid in thread_ids)


async def test_read_missing_object_raises_file_not_found(repo):
    with pytest.raises(FileNotFoundError):
        await repo.read_bytes(uuid4())


async def test_finalize_missing_upload_raises_file_not_found(repo):
    with pytest.raises(FileNotFoundError):
        await repo.finalize_upload(uuid4())


async def test_finalize_png_returns_sha_size_and_dimensions(repo):
    media_id = uuid4()
    png = _png_bytes(64, 32)
    await repo.store_upload(media_id, png)

    sha, size, dims = await repo.finalize_upload(media_id)

    assert sha == hashlib.sha256(png).hexdigest()
    assert size == len(png)
    assert dims == (64, 32)


async def test_finalize_strips_exif_and_persists_normalized_bytes(repo):
    media_id = uuid4()
    raw = _jpeg_with_exif_orientation()
    await repo.store_upload(media_id, raw)

    sha, size, dims = await repo.finalize_upload(media_id)
    stored = await repo.read_bytes(media_id)

    assert dims == (20, 40)  # orientation applied
    assert stored != raw
    assert sha == hashlib.sha256(stored).hexdigest()
    assert size == len(stored)
    with Image.open(io.BytesIO(stored)) as img:
        assert not img.getexif()


async def test_finalize_matches_local_fs_results(repo, tmp_path):
    local = LocalFileSystemBlobRepository(base_dir=tmp_path)
    raw = _jpeg_with_exif_orientation()
    gcs_id, local_id = uuid4(), uuid4()
    await repo.store_upload(gcs_id, raw)
    await local.store_upload(local_id, raw)

    assert await repo.finalize_upload(gcs_id) == await local.finalize_upload(local_id)


async def test_finalize_rejects_oversized_image(repo):
    media_id = uuid4()
    oversized = b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024 + 1)
    await repo.store_upload(media_id, oversized)
    with pytest.raises(ValueError, match="5 MB"):
        await repo.finalize_upload(media_id)


async def test_finalize_rejects_long_edge_over_limit(repo):
    media_id = uuid4()
    await repo.store_upload(media_id, _png_bytes(2049, 10))
    with pytest.raises(ValueError, match="2048"):
        await repo.finalize_upload(media_id)


async def test_finalize_with_explicit_bytes_writes_them(repo):
    media_id = uuid4()
    payload = b"%PDF-1.4 agreement"
    sha, size, dims = await repo.finalize_upload(media_id, raw_bytes=payload)
    assert (sha, size, dims) == (hashlib.sha256(payload).hexdigest(), len(payload), None)
    assert await repo.read_bytes(media_id) == payload


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (_png_bytes(), "image/png"),
        (_jpeg_with_exif_orientation(), "image/jpeg"),
        (b"%PDF-1.7\n...", "application/pdf"),
        (b"\x00\x01binary", "application/octet-stream"),
    ],
    ids=["png", "jpeg", "pdf", "unknown"],
)
async def test_store_upload_sets_content_type_from_bytes(repo, fake_storage_client, payload, expected):
    media_id = uuid4()
    await repo.store_upload(media_id, payload)
    bucket = fake_storage_client.buckets[BUCKET]
    assert bucket.content_types[f"media/{media_id}.bin"] == expected
