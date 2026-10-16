"""CLOUD profile resolves persistence adapters at startup so misconfiguration fails the boot."""

import pytest
from fastapi.testclient import TestClient

from apps.api.core.config import ConfigurationError, settings
from apps.api.main import app
from apps.api.modules.catalog import dependencies as catalog_deps
from apps.api.modules.imports import dependencies as imports_deps
from apps.api.modules.imports.repository import ImportRepository


def test_cloud_profile_startup_fails_on_missing_analytics_config(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "profile", "CLOUD")
    monkeypatch.setattr(settings, "data_backend", "LOCAL")
    monkeypatch.setattr(catalog_deps, "_blob_repository", object())
    monkeypatch.setattr(imports_deps, "_import_repository", ImportRepository())
    monkeypatch.setattr(imports_deps, "_analytics_repository", None)

    with pytest.raises(ConfigurationError, match="DATA_BACKEND=CLOUD"), TestClient(app):
        pass


def test_local_profile_startup_does_not_build_cloud_adapters(monkeypatch):
    monkeypatch.setattr(settings, "profile", "LOCAL")
    monkeypatch.setattr(imports_deps, "_analytics_repository", None)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
    assert imports_deps._analytics_repository is None
