"""Shared test fixtures for demo seed test suite (tests/demo/)."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse
from starlette.routing import Route
from storeops_contracts.models import Currency, Workspace

from apps.api.adapters.blob.local_fs import LocalFileSystemBlobRepository
from apps.api.adapters.state.in_memory import InMemoryStateRepository
from apps.api.analytics.duckdb import DuckDBAnalyticsRepository
from apps.api.core.auth import get_state_repository, set_state_repository
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


@pytest.fixture(autouse=True)
def init_demo_test_environment(tmp_path: Path):
    """Autouse fixture to wire up repositories and clean in-memory state with strict save/restore."""
    prev_overrides = dict(app.dependency_overrides)

    state_repo = InMemoryStateRepository()
    set_state_repository(state_repo)

    visit_repo = InMemoryVisitRepository()
    verification_repo = InMemoryVerificationRepository()
    catalog_repo = InMemoryCatalogRepository()
    policy_repo = InMemoryPolicyRepository()
    blob_dir = tmp_path / "demo_blobs"
    blob_dir.mkdir(parents=True, exist_ok=True)
    blob_repo = LocalFileSystemBlobRepository(base_dir=blob_dir)
    analytics_repo = DuckDBAnalyticsRepository(db_path=":memory:")

    app.dependency_overrides[get_visit_repository] = lambda: visit_repo
    app.dependency_overrides[get_verification_repository] = lambda: verification_repo
    app.dependency_overrides[get_catalog_repository] = lambda: catalog_repo
    app.dependency_overrides[get_policy_repository] = lambda: policy_repo
    app.dependency_overrides[get_blob_repository] = lambda: blob_repo
    app.dependency_overrides[get_analytics_repository] = lambda: analytics_repo

    async def _test_upload_media_bytes(request: StarletteRequest) -> StarletteResponse:
        media_id = request.path_params["media_id"]
        raw = await request.body()
        getter = app.dependency_overrides.get(get_blob_repository, get_blob_repository)
        repo = getter()
        path = repo._file_path(media_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return StarletteResponse(status_code=200)

    upload_route = Route("/media/upload/{media_id}", _test_upload_media_bytes, methods=["PUT"])
    app.routes.insert(0, upload_route)

    yield

    if upload_route in app.routes:
        app.routes.remove(upload_route)
    app.dependency_overrides = prev_overrides


@pytest.fixture
async def demo_client():
    """Async test client wired to StoreOps FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def provision_demo_workspace(workspace_id: UUID, currency: str = "USD") -> None:
    """Helper to provision a test workspace with admin and rep memberships."""
    now = datetime.now(UTC)
    state_repo = get_state_repository()
    curr = Currency.USD if currency == "USD" else (Currency.SGD if currency == "SGD" else Currency.AUD)
    ws_model = Workspace(
        id=workspace_id,
        workspace_id=workspace_id,
        version=1,
        created_at=now,
        updated_at=now,
        name="Retail Demo Workspace",
        brand_name="AquaPure",
        currency=curr,
    )
    await state_repo.create_workspace_with_admin(
        ws_model, uid="demo-admin", email="demo-admin@storeops.test"
    )
    await state_repo.add_membership(
        workspace_id, uid="demo-rep", role="REP", email="demo-rep@storeops.test"
    )
