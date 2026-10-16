"""Adapter selection from settings: cloud adapters on CLOUD config, local otherwise, no silent fallback."""

from typing import Any
from uuid import uuid4

import pytest

from apps.api.adapters.blob.gcs import GCSBlobRepository
from apps.api.adapters.blob.local_fs import LocalFileSystemBlobRepository
from apps.api.adapters.state.firestore_imports import FirestoreImportRepository
from apps.api.analytics.bigquery import BigQueryAnalyticsRepository
from apps.api.analytics.duckdb import DuckDBAnalyticsRepository
from apps.api.core.config import ConfigurationError, Settings
from apps.api.modules.catalog.dependencies import build_blob_repository
from apps.api.modules.imports.dependencies import (
    build_analytics_repository,
    build_import_repository,
)
from apps.api.modules.imports.repository import ImportRepository


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "app_env": "development",
        "profile": "LOCAL",
        "ai_mode": "STUB",
        "state_backend": "in_memory",
        "data_backend": "LOCAL",
        "media_bucket": None,
        "gcp_project": None,
        "bigquery_dataset": None,
    }
    return Settings(**{**base, **overrides})


def _cloud(**overrides: Any) -> Settings:
    return _settings(
        **{
            "profile": "CLOUD",
            "ai_mode": "LIVE",
            "state_backend": "firestore",
            "data_backend": "CLOUD",
            "media_bucket": "storeops-test-media",
            "gcp_project": "storeops-ai",
            "bigquery_dataset": "storeops_dev",
            "media_url_signing_key": "s" * 32,
            **overrides,
        }
    )


class _Recorder:
    def __init__(self, client: Any) -> None:
        self.client = client
        self.projects: list[str | None] = []

    def __call__(self, project: str | None) -> Any:
        self.projects.append(project)
        return self.client


# ---------------------------------------------------------------- settings


def test_settings_read_cloud_env_vars(monkeypatch):
    monkeypatch.setenv("DATA_BACKEND", "CLOUD")
    monkeypatch.setenv("MEDIA_BUCKET", "bucket-from-env")
    monkeypatch.setenv("GCP_PROJECT", "proj-from-env")
    monkeypatch.setenv("BIGQUERY_DATASET", "ds_from_env")
    monkeypatch.setenv("MEDIA_URL_SIGNING_KEY", "key-from-env")
    s = Settings()
    assert s.media_url_signing_key == "key-from-env"
    assert "key-from-env" not in repr(s)
    assert (s.data_backend, s.media_bucket, s.gcp_project, s.bigquery_dataset) == (
        "CLOUD",
        "bucket-from-env",
        "proj-from-env",
        "ds_from_env",
    )


# ---------------------------------------------------------------- blob


def test_blob_local_by_default(tmp_path):
    repo = build_blob_repository(_settings(media_storage_dir=str(tmp_path)))
    assert isinstance(repo, LocalFileSystemBlobRepository)
    assert repo.base_dir == tmp_path


def test_blob_gcs_when_firestore_and_bucket(fake_storage_client):
    factory = _Recorder(fake_storage_client)
    repo = build_blob_repository(_cloud(), storage_client_factory=factory)
    assert isinstance(repo, GCSBlobRepository)
    assert repo.bucket_name == "storeops-test-media"
    assert factory.projects == ["storeops-ai"]


def test_blob_local_when_bucket_set_but_state_in_memory(tmp_path):
    repo = build_blob_repository(
        _settings(media_bucket="some-bucket", media_storage_dir=str(tmp_path))
    )
    assert isinstance(repo, LocalFileSystemBlobRepository)


def test_blob_cloud_profile_without_bucket_raises(fake_storage_client):
    with pytest.raises(ConfigurationError, match="MEDIA_BUCKET"):
        build_blob_repository(
            _cloud(media_bucket=None), storage_client_factory=_Recorder(fake_storage_client)
        )


def test_blob_cloud_profile_without_signing_key_raises(fake_storage_client):
    with pytest.raises(ConfigurationError, match="MEDIA_URL_SIGNING_KEY"):
        build_blob_repository(
            _cloud(media_url_signing_key=None),
            storage_client_factory=_Recorder(fake_storage_client),
        )


def test_blob_repository_signs_with_configured_key(tmp_path):
    from apps.api.adapters.blob.signing import UPLOAD_METHOD, MediaUrlSigner

    repo = build_blob_repository(
        _settings(media_storage_dir=str(tmp_path), media_url_signing_key="configured-key")
    )
    media_id = uuid4()
    issued = MediaUrlSigner(b"configured-key").query(UPLOAD_METHOD, media_id, 60)
    params = dict(pair.split("=") for pair in issued.split("&"))
    assert repo.verify_signed_url(UPLOAD_METHOD, media_id, params["expires"], params["sig"])


# ---------------------------------------------------------------- analytics


def test_analytics_duckdb_by_default():
    assert isinstance(build_analytics_repository(_settings()), DuckDBAnalyticsRepository)


def test_analytics_bigquery_when_data_backend_cloud(fake_bigquery_client):
    factory = _Recorder(fake_bigquery_client)
    repo = build_analytics_repository(_cloud(), bigquery_client_factory=factory)
    assert isinstance(repo, BigQueryAnalyticsRepository)
    assert (repo.project_id, repo.dataset_id) == ("storeops-ai", "storeops_dev")
    assert repo._client is fake_bigquery_client
    assert factory.projects == ["storeops-ai"]


@pytest.mark.parametrize("missing", ["gcp_project", "bigquery_dataset"])
def test_analytics_cloud_missing_config_raises(missing, fake_bigquery_client):
    env_name = {"gcp_project": "GCP_PROJECT", "bigquery_dataset": "BIGQUERY_DATASET"}[missing]
    with pytest.raises(ConfigurationError, match=env_name):
        build_analytics_repository(
            _cloud(**{missing: None}), bigquery_client_factory=_Recorder(fake_bigquery_client)
        )


def test_analytics_cloud_profile_with_local_data_backend_raises():
    with pytest.raises(ConfigurationError, match="DATA_BACKEND=CLOUD"):
        build_analytics_repository(_cloud(data_backend="LOCAL"))


def test_analytics_client_failure_propagates():
    def failing_factory(project: str | None) -> Any:
        raise RuntimeError("no credentials")

    with pytest.raises(RuntimeError, match="no credentials"):
        build_analytics_repository(_cloud(), bigquery_client_factory=failing_factory)


def test_analytics_production_dataset_allowed_only_in_production(fake_bigquery_client):
    factory = _Recorder(fake_bigquery_client)
    with pytest.raises(ValueError, match="production-like dataset"):
        build_analytics_repository(
            _cloud(bigquery_dataset="storeops_production"), bigquery_client_factory=factory
        )
    repo = build_analytics_repository(
        _cloud(bigquery_dataset="storeops_production", app_env="production"),
        bigquery_client_factory=factory,
    )
    assert repo.dataset_id == "storeops_production"


# ---------------------------------------------------------------- imports


def test_imports_in_memory_by_default():
    assert isinstance(build_import_repository(_settings()), ImportRepository)


def test_imports_firestore_when_state_backend_firestore(fake_firestore):
    factory = _Recorder(fake_firestore)
    repo = build_import_repository(_cloud(), firestore_client_factory=factory)
    assert isinstance(repo, FirestoreImportRepository)
    assert factory.projects == [_cloud().firebase_project_id]
