"""PUT /media/upload/{id}: stores bytes via the BlobRepository port, with size and state guards.

Both byte routes require a signed URL; signature rules are covered in test_media_url_signing.py.
"""

from uuid import UUID, uuid4

import entity_factories as f
import pytest
from fastapi.testclient import TestClient
from storeops_contracts.models import Status1

from apps.api.adapters.blob.signing import (
    DOWNLOAD_METHOD,
    UPLOAD_METHOD,
    UPLOAD_URL_TTL_SECONDS,
    MediaUrlSigner,
)
from apps.api.main import app
from apps.api.modules.catalog import dependencies as catalog_deps
from apps.api.modules.catalog.repository import InMemoryCatalogRepository
from apps.api.modules.catalog.router import MAX_UPLOAD_BYTES


class _RecordingBlobRepository:
    def __init__(self) -> None:
        self.stored: dict[UUID, bytes] = {}
        self.signer = MediaUrlSigner(b"route-test-key")

    async def prepare_upload(self, media_id, filename, mime_type):
        return self.signer.signed_url(
            "http://test/media", UPLOAD_METHOD, media_id, UPLOAD_URL_TTL_SECONDS
        )

    async def store_upload(self, media_id: UUID, data: bytes) -> None:
        self.stored[media_id] = data

    async def finalize_upload(self, media_id, raw_bytes=None):
        raise NotImplementedError

    async def read_bytes(self, media_id):
        if media_id not in self.stored:
            raise FileNotFoundError(str(media_id))
        return self.stored[media_id]

    async def get_download_url(self, media_id, expires_in_seconds=600):
        return self.signer.signed_url("http://test/media", DOWNLOAD_METHOD, media_id, expires_in_seconds)

    def verify_signed_url(self, method, media_id, expires, signature):
        return self.signer.verify(method, media_id, expires, signature)


class _FailingBlobRepository(_RecordingBlobRepository):
    async def store_upload(self, media_id: UUID, data: bytes) -> None:
        raise OSError("bucket unavailable")


def _upload_path(media_id: UUID) -> str:
    query = _SIGNER.query(UPLOAD_METHOD, media_id, UPLOAD_URL_TTL_SECONDS)
    return f"/media/upload/{media_id}?{query}"


def _download_path(media_id: UUID) -> str:
    return f"/media/download/{media_id}?{_SIGNER.query(DOWNLOAD_METHOD, media_id, 600)}"


_SIGNER = MediaUrlSigner(b"route-test-key")


@pytest.fixture
def blob_repo(monkeypatch):
    repo = _RecordingBlobRepository()
    monkeypatch.setattr(catalog_deps, "_blob_repository", repo)
    return repo


@pytest.fixture
def catalog(monkeypatch):
    repo = InMemoryCatalogRepository()
    monkeypatch.setattr(catalog_deps, "_catalog_repository", repo)
    return repo


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


async def _pending(catalog, byte_size: int = 13, status: Status1 = Status1.PENDING_UPLOAD):
    med = f.media(uuid4(), status=status, byte_size=byte_size)
    await catalog.create_media(med)
    return med


async def test_upload_stores_bytes_via_port(blob_repo, catalog, client):
    med = await _pending(catalog, byte_size=13)
    resp = client.put(_upload_path(med.id), content=b"payload-bytes")
    assert resp.status_code == 200
    assert blob_repo.stored == {med.id: b"payload-bytes"}


async def test_upload_smaller_than_declared_is_accepted(blob_repo, catalog, client):
    """Checksum validation at completion rejects mismatches; the route only caps size."""
    med = await _pending(catalog, byte_size=100)
    assert client.put(_upload_path(med.id), content=b"short").status_code == 200


async def test_upload_larger_than_declared_is_rejected(blob_repo, catalog, client):
    med = await _pending(catalog, byte_size=4)
    resp = client.put(_upload_path(med.id), content=b"12345")
    assert resp.status_code == 413
    assert resp.json()["code"] == "FILE_TOO_LARGE"
    assert blob_repo.stored == {}


async def test_upload_over_absolute_cap_is_rejected(blob_repo, catalog, client):
    med = await _pending(catalog, byte_size=MAX_UPLOAD_BYTES * 3)
    resp = client.put(_upload_path(med.id), content=b"x" * (MAX_UPLOAD_BYTES + 1))
    assert resp.status_code == 413
    assert blob_repo.stored == {}


def test_absolute_cap_is_20_mb():
    assert MAX_UPLOAD_BYTES == 20 * 1024 * 1024


async def test_upload_for_unknown_media_is_404(blob_repo, catalog, client):
    resp = client.put(_upload_path(uuid4()), content=b"x")
    assert resp.status_code == 404
    assert blob_repo.stored == {}


@pytest.mark.parametrize("status", [Status1.READY, Status1.REJECTED])
async def test_upload_for_non_pending_media_is_409(blob_repo, catalog, client, status):
    med = await _pending(catalog, byte_size=10, status=status)
    resp = client.put(_upload_path(med.id), content=b"x")
    assert resp.status_code == 409
    assert resp.json()["code"] == "INVALID_STATE"
    assert blob_repo.stored == {}


async def test_upload_does_not_report_success_when_store_fails(monkeypatch, catalog, client):
    monkeypatch.setattr(catalog_deps, "_blob_repository", _FailingBlobRepository())
    med = await _pending(catalog, byte_size=1)
    resp = client.put(_upload_path(med.id), content=b"x")
    assert resp.status_code >= 500


def test_download_route_reads_via_port(blob_repo, client):
    media_id = uuid4()
    blob_repo.stored[media_id] = b"abc"
    assert client.get(_download_path(media_id)).content == b"abc"
    assert client.get(_download_path(uuid4())).status_code == 404


async def test_download_route_serves_the_media_mime_type(blob_repo, catalog, client):
    med = await _pending(catalog, byte_size=3, status=Status1.READY)
    blob_repo.stored[med.id] = b"abc"
    resp = client.get(_download_path(med.id))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(med.mime_type)
