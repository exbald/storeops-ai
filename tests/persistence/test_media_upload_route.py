"""PUT /media/upload/{id} stores bytes through the BlobRepository port for every adapter."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.modules.catalog import dependencies as catalog_deps


class _RecordingBlobRepository:
    def __init__(self) -> None:
        self.stored: dict[UUID, bytes] = {}

    async def prepare_upload(self, media_id, filename, mime_type):
        return f"http://test/media/upload/{media_id}"

    async def store_upload(self, media_id: UUID, data: bytes) -> None:
        self.stored[media_id] = data

    async def finalize_upload(self, media_id, raw_bytes=None):
        raise NotImplementedError

    async def read_bytes(self, media_id):
        if media_id not in self.stored:
            raise FileNotFoundError(str(media_id))
        return self.stored[media_id]

    async def get_download_url(self, media_id, expires_in_seconds=600):
        return f"http://test/media/{media_id}"


class _FailingBlobRepository(_RecordingBlobRepository):
    async def store_upload(self, media_id: UUID, data: bytes) -> None:
        raise OSError("bucket unavailable")


@pytest.fixture
def swap_blob_repo():
    previous = catalog_deps._blob_repository

    def _swap(repo):
        catalog_deps.set_blob_repository(repo)
        return repo

    yield _swap
    catalog_deps._blob_repository = previous


def test_upload_route_stores_bytes_via_port(swap_blob_repo):
    repo = swap_blob_repo(_RecordingBlobRepository())
    media_id = uuid4()
    with TestClient(app) as client:
        resp = client.put(f"/media/upload/{media_id}", content=b"payload-bytes")
    assert resp.status_code == 200
    assert repo.stored == {media_id: b"payload-bytes"}


def test_upload_route_does_not_report_success_when_store_fails(swap_blob_repo):
    swap_blob_repo(_FailingBlobRepository())
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.put(f"/media/upload/{uuid4()}", content=b"x")
    assert resp.status_code >= 500


def test_download_route_reads_via_port(swap_blob_repo):
    repo = swap_blob_repo(_RecordingBlobRepository())
    media_id = uuid4()
    repo.stored[media_id] = b"abc"
    with TestClient(app) as client:
        assert client.get(f"/media/download/{media_id}").content == b"abc"
        assert client.get(f"/media/download/{uuid4()}").status_code == 404
