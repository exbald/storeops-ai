"""HMAC-signed, expiring media URLs: issued by blob adapters, enforced by the byte routes."""

from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import entity_factories as f
import pytest
from fastapi.testclient import TestClient
from storeops_contracts.models import Status1

from apps.api.adapters.blob.gcs import GCSBlobRepository
from apps.api.adapters.blob.local_fs import LocalFileSystemBlobRepository
from apps.api.adapters.blob.signing import (
    DOWNLOAD_METHOD,
    LOCAL_DEV_SIGNING_KEY,
    UPLOAD_METHOD,
    UPLOAD_URL_TTL_SECONDS,
    MediaUrlSigner,
    resolve_signing_key,
)
from apps.api.core.config import ConfigurationError
from apps.api.main import app
from apps.api.modules.catalog import dependencies as catalog_deps
from apps.api.modules.catalog.repository import InMemoryCatalogRepository

KEY = b"k" * 32
NOW = 1_800_000_000.0


def _rel(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path


def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


# ---------------------------------------------------------------- signer


def test_signed_query_carries_expiry_and_hex_signature():
    signer = MediaUrlSigner(KEY, clock=lambda: NOW)
    media_id = uuid4()
    query = _query("http://x/?" + signer.query(DOWNLOAD_METHOD, media_id, 600))
    assert query["expires"] == str(int(NOW) + 600)
    assert len(query["sig"]) == 64
    int(query["sig"], 16)
    assert signer.verify(DOWNLOAD_METHOD, media_id, query["expires"], query["sig"])


def test_signature_binds_method_media_and_expiry():
    signer = MediaUrlSigner(KEY, clock=lambda: NOW)
    media_id = uuid4()
    q = _query("http://x/?" + signer.query(UPLOAD_METHOD, media_id, 60))
    assert signer.verify(UPLOAD_METHOD, media_id, q["expires"], q["sig"])
    assert not signer.verify(DOWNLOAD_METHOD, media_id, q["expires"], q["sig"])
    assert not signer.verify(UPLOAD_METHOD, uuid4(), q["expires"], q["sig"])
    assert not signer.verify(UPLOAD_METHOD, media_id, str(int(q["expires"]) + 1), q["sig"])
    assert not MediaUrlSigner(b"x" * 32, clock=lambda: NOW).verify(
        UPLOAD_METHOD, media_id, q["expires"], q["sig"]
    )


@pytest.mark.parametrize(
    ("expires", "sig"),
    [(None, None), ("123", None), (None, "ab"), ("not-a-number", "ab"), ("", "")],
)
def test_missing_or_malformed_parameters_fail(expires, sig):
    assert not MediaUrlSigner(KEY).verify(UPLOAD_METHOD, uuid4(), expires, sig)


def test_expired_signature_fails():
    media_id = uuid4()
    issued = MediaUrlSigner(KEY, clock=lambda: NOW)
    q = _query("http://x/?" + issued.query(DOWNLOAD_METHOD, media_id, 600))
    later = MediaUrlSigner(KEY, clock=lambda: NOW + 601)
    assert not later.verify(DOWNLOAD_METHOD, media_id, q["expires"], q["sig"])


def test_signer_rejects_empty_key():
    with pytest.raises(ValueError):
        MediaUrlSigner(b"")


def test_cloud_profile_requires_signing_key():
    with pytest.raises(ConfigurationError, match="MEDIA_URL_SIGNING_KEY"):
        resolve_signing_key("CLOUD", None)
    with pytest.raises(ConfigurationError, match="MEDIA_URL_SIGNING_KEY"):
        resolve_signing_key("CLOUD", "too-short")
    assert resolve_signing_key("CLOUD", "s" * 32) == b"s" * 32


def test_local_profile_falls_back_to_fixed_dev_key():
    assert resolve_signing_key("LOCAL", None) == LOCAL_DEV_SIGNING_KEY
    assert resolve_signing_key("LOCAL", "custom-key") == b"custom-key"


# ---------------------------------------------------------------- adapters


@pytest.fixture
def adapters(tmp_path, fake_storage_client, monkeypatch):
    monkeypatch.setenv("MEDIA_BASE_URL", "https://api.example.test/media")
    signer = MediaUrlSigner(KEY, clock=lambda: NOW)
    return [
        LocalFileSystemBlobRepository(base_dir=tmp_path, signer=signer),
        GCSBlobRepository(bucket_name="b", client=fake_storage_client, signer=signer),
    ]


async def test_adapters_issue_signed_upload_urls_valid_for_15_minutes(adapters):
    media_id = uuid4()
    for repo in adapters:
        url = await repo.prepare_upload(media_id, "a.png", "image/png")
        assert url.startswith(f"https://api.example.test/media/upload/{media_id}?")
        q = _query(url)
        assert q["expires"] == str(int(NOW) + UPLOAD_URL_TTL_SECONDS)
        assert UPLOAD_URL_TTL_SECONDS == 15 * 60
        assert repo.verify_signed_url(UPLOAD_METHOD, media_id, q["expires"], q["sig"])


async def test_adapters_issue_signed_download_urls(adapters):
    media_id = uuid4()
    for repo in adapters:
        url = await repo.get_download_url(media_id, expires_in_seconds=300)
        assert url.startswith(f"https://api.example.test/media/download/{media_id}?")
        q = _query(url)
        assert q["expires"] == str(int(NOW) + 300)
        assert repo.verify_signed_url(DOWNLOAD_METHOD, media_id, q["expires"], q["sig"])
        assert not repo.verify_signed_url(UPLOAD_METHOD, media_id, q["expires"], q["sig"])


def test_gcs_adapter_requires_a_signer(fake_storage_client):
    with pytest.raises(TypeError):
        GCSBlobRepository(bucket_name="b", client=fake_storage_client)  # type: ignore[call-arg]


# ---------------------------------------------------------------- routes


@pytest.fixture
def blob_repo(tmp_path, monkeypatch):
    repo = LocalFileSystemBlobRepository(base_dir=tmp_path, signer=MediaUrlSigner(KEY))
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


async def _media(catalog, status=Status1.PENDING_UPLOAD):
    med = f.media(uuid4(), status=status, byte_size=10)
    await catalog.create_media(med)
    return med


def _assert_forbidden(resp):
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


async def test_upload_with_valid_signature_is_accepted(blob_repo, catalog, client):
    med = await _media(catalog)
    url = await blob_repo.prepare_upload(med.id, "a.png", "image/png")
    assert client.put(_rel(url), content=b"bytes").status_code == 200
    assert await blob_repo.read_bytes(med.id) == b"bytes"


async def test_upload_without_signature_is_forbidden(blob_repo, catalog, client):
    med = await _media(catalog)
    _assert_forbidden(client.put(f"/media/upload/{med.id}", content=b"x"))
    with pytest.raises(FileNotFoundError):
        await blob_repo.read_bytes(med.id)


async def test_upload_with_tampered_signature_is_forbidden(blob_repo, catalog, client):
    med = await _media(catalog)
    q = _query(await blob_repo.prepare_upload(med.id, "a.png", "image/png"))
    bad_sig = ("0" if q["sig"][0] != "0" else "1") + q["sig"][1:]
    resp = client.put(f"/media/upload/{med.id}?expires={q['expires']}&sig={bad_sig}", content=b"x")
    _assert_forbidden(resp)


async def test_upload_with_expired_signature_is_forbidden(blob_repo, catalog, client):
    med = await _media(catalog)
    stale = MediaUrlSigner(KEY, clock=lambda: 1_000.0)
    resp = client.put(
        f"/media/upload/{med.id}?{stale.query(UPLOAD_METHOD, med.id, UPLOAD_URL_TTL_SECONDS)}",
        content=b"x",
    )
    _assert_forbidden(resp)


async def test_signature_for_one_media_is_rejected_for_another(blob_repo, catalog, client):
    med, other = await _media(catalog), await _media(catalog)
    q = _query(await blob_repo.prepare_upload(med.id, "a.png", "image/png"))
    resp = client.put(f"/media/upload/{other.id}?expires={q['expires']}&sig={q['sig']}", content=b"x")
    _assert_forbidden(resp)


async def test_upload_signature_is_not_valid_for_download(blob_repo, catalog, client):
    med = await _media(catalog, status=Status1.READY)
    await blob_repo.store_upload(med.id, b"abc")
    q = _query(await blob_repo.prepare_upload(med.id, "a.png", "image/png"))
    _assert_forbidden(client.get(f"/media/download/{med.id}?expires={q['expires']}&sig={q['sig']}"))


async def test_download_signature_is_not_valid_for_upload(blob_repo, catalog, client):
    med = await _media(catalog)
    q = _query(await blob_repo.get_download_url(med.id))
    resp = client.put(f"/media/upload/{med.id}?expires={q['expires']}&sig={q['sig']}", content=b"x")
    _assert_forbidden(resp)


async def test_download_with_valid_signature_serves_bytes(blob_repo, catalog, client):
    med = await _media(catalog, status=Status1.READY)
    await blob_repo.store_upload(med.id, b"abc")
    resp = client.get(_rel(await blob_repo.get_download_url(med.id)))
    assert resp.status_code == 200
    assert resp.content == b"abc"


async def test_download_without_or_with_expired_signature_is_forbidden(blob_repo, catalog, client):
    med = await _media(catalog, status=Status1.READY)
    await blob_repo.store_upload(med.id, b"abc")
    _assert_forbidden(client.get(f"/media/download/{med.id}"))
    stale = MediaUrlSigner(KEY, clock=lambda: 1_000.0)
    _assert_forbidden(client.get(f"/media/download/{med.id}?{stale.query(DOWNLOAD_METHOD, med.id, 600)}"))
