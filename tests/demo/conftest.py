"""Shared test fixtures for demo seed test suite (tests/demo/)."""

from pathlib import Path

import pytest
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

from apps.api.adapters.blob.local_fs import LocalFileSystemBlobRepository
from apps.api.adapters.state.in_memory import InMemoryStateRepository
from apps.api.analytics.duckdb import DuckDBAnalyticsRepository
from apps.api.core.auth import set_state_repository
from apps.api.main import app
from apps.api.modules.catalog.dependencies import (
    get_blob_repository,
    get_catalog_repository,
)
from apps.api.modules.catalog.repository import InMemoryCatalogRepository
from apps.api.modules.imports.dependencies import (
    get_analytics_repository,
)
from apps.api.modules.policies.dependencies import (
    get_policy_repository,
)
from apps.api.modules.policies.repository import InMemoryPolicyRepository
from apps.api.modules.verification.dependencies import (
    get_verification_repository,
)
from apps.api.modules.verification.repository import InMemoryVerificationRepository
from apps.api.modules.visits.dependencies import (
    get_visit_repository,
)
from apps.api.modules.visits.repository import InMemoryVisitRepository

# Ensure media upload test route is present
if not any(getattr(route, "path", None) == "/media/upload/{media_id}" for route in app.routes):
    @app.put("/media/upload/{media_id}")
    async def _test_upload_media_bytes(request: StarletteRequest) -> StarletteResponse:
        from apps.api.modules.catalog.dependencies import get_blob_repository
        media_id = request.path_params["media_id"]
        raw = await request.body()
        getter = app.dependency_overrides.get(get_blob_repository, get_blob_repository)
        blob_repo = getter()
        path = blob_repo._file_path(media_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return StarletteResponse(status_code=200)


@pytest.fixture(autouse=True)
def init_demo_test_environment(tmp_path: Path):
    """Autouse fixture to wire up repositories and clean in-memory state."""
    state_repo = InMemoryStateRepository()
    set_state_repository(state_repo)

    visit_repo = InMemoryVisitRepository()
    verification_repo = InMemoryVerificationRepository()
    catalog_repo = InMemoryCatalogRepository()
    policy_repo = InMemoryPolicyRepository()
    blob_repo = LocalFileSystemBlobRepository(base_dir=tmp_path / "demo_blobs")
    analytics_repo = DuckDBAnalyticsRepository(db_path=":memory:")

    app.dependency_overrides[get_visit_repository] = lambda: visit_repo
    app.dependency_overrides[get_verification_repository] = lambda: verification_repo
    app.dependency_overrides[get_catalog_repository] = lambda: catalog_repo
    app.dependency_overrides[get_policy_repository] = lambda: policy_repo
    app.dependency_overrides[get_blob_repository] = lambda: blob_repo
    app.dependency_overrides[get_analytics_repository] = lambda: analytics_repo

    yield

    app.dependency_overrides.clear()
