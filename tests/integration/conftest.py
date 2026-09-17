"""Shared fixtures for integration and regression test suites."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse
from starlette.routing import Route
from storeops_contracts.models import Currency, Workspace

from apps.api.adapters.blob.local_fs import LocalFileSystemBlobRepository
from apps.api.adapters.state.in_memory import InMemoryStateRepository
from apps.api.ai.gateway import DeterministicModelGateway
from apps.api.analytics.duckdb import DuckDBAnalyticsRepository
from apps.api.core.auth import set_state_repository
from apps.api.main import app
from apps.api.modules.catalog.dependencies import (
    get_blob_repository,
    get_catalog_repository,
    set_blob_repository,
    set_catalog_repository,
)
from apps.api.modules.catalog.repository import InMemoryCatalogRepository
from apps.api.modules.imports.dependencies import (
    set_analytics_repository,
)
from apps.api.modules.policies.dependencies import (
    get_policy_repository,
    set_policy_repository,
)
from apps.api.modules.policies.dependencies import (
    set_model_gateway as set_policy_model_gateway,
)
from apps.api.modules.policies.repository import InMemoryPolicyRepository
from apps.api.modules.verification.dependencies import (
    get_verification_repository,
    set_clock,
    set_verification_repository,
)
from apps.api.modules.verification.dependencies import (
    set_model_gateway as set_verification_model_gateway,
)
from apps.api.modules.verification.repository import InMemoryVerificationRepository
from apps.api.modules.visits.dependencies import (
    get_visit_repository,
    set_model_gateway,
    set_visit_repository,
)
from apps.api.modules.visits.repository import InMemoryVisitRepository
from apps.api.ports.clock import Clock


class IntegrationFrozenClock(Clock):
    def __init__(self, fixed_now: datetime | None = None) -> None:
        self._now = fixed_now or datetime.now(UTC)

    def now_utc(self) -> datetime:
        return self._now

    def advance(self, td: timedelta) -> None:
        self._now += td


@pytest.fixture
def frozen_clock() -> IntegrationFrozenClock:
    return IntegrationFrozenClock(datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC))


@pytest.fixture
def workspace_a_id() -> UUID:
    return uuid4()


@pytest.fixture
def workspace_b_id() -> UUID:
    return uuid4()


@pytest.fixture
def int_visit_repo() -> InMemoryVisitRepository:
    return InMemoryVisitRepository()


@pytest.fixture
def int_verification_repo() -> InMemoryVerificationRepository:
    return InMemoryVerificationRepository()


@pytest.fixture
def int_catalog_repo() -> InMemoryCatalogRepository:
    return InMemoryCatalogRepository()


@pytest.fixture
def int_policy_repo() -> InMemoryPolicyRepository:
    return InMemoryPolicyRepository()


@pytest.fixture
def int_blob_repo(tmp_path: Path) -> LocalFileSystemBlobRepository:
    return LocalFileSystemBlobRepository(base_dir=tmp_path / "int_blobs")


@pytest.fixture
def int_analytics_repo() -> DuckDBAnalyticsRepository:
    return DuckDBAnalyticsRepository(db_path=":memory:")


@pytest.fixture
def int_gateway():
    from tests.visits.conftest import ConfigurableModelGateway

    return ConfigurableModelGateway()


@pytest_asyncio.fixture
async def int_state_repo(workspace_a_id: UUID, workspace_b_id: UUID) -> InMemoryStateRepository:
    repo = InMemoryStateRepository()
    now = datetime.now(UTC)

    # Workspace A
    ws_a = Workspace(
        id=workspace_a_id,
        workspace_id=workspace_a_id,
        version=1,
        created_at=now,
        updated_at=now,
        name="Workspace Alpha",
        brand_name="Alpha Brand",
        currency=Currency.SGD,
    )
    await repo.create_workspace_with_admin(ws_a, uid="user-admin-a", email="admin-a@storeops.test")
    await repo.add_membership(workspace_a_id, uid="user-rep-a", role="REP", email="rep-a@storeops.test")

    # Workspace B
    ws_b = Workspace(
        id=workspace_b_id,
        workspace_id=workspace_b_id,
        version=1,
        created_at=now,
        updated_at=now,
        name="Workspace Beta",
        brand_name="Beta Brand",
        currency=Currency.USD,
    )
    await repo.create_workspace_with_admin(ws_b, uid="user-admin-b", email="admin-b@storeops.test")
    await repo.add_membership(workspace_b_id, uid="user-rep-b", role="REP", email="rep-b@storeops.test")

    set_state_repository(repo)
    return repo


@pytest.fixture
def admin_a_headers(workspace_a_id: UUID) -> dict[str, str]:
    return {
        "Authorization": "Bearer user-admin-a",
        "X-Workspace-Id": str(workspace_a_id),
    }


@pytest.fixture
def rep_a_headers(workspace_a_id: UUID) -> dict[str, str]:
    return {
        "Authorization": "Bearer user-rep-a",
        "X-Workspace-Id": str(workspace_a_id),
    }


@pytest.fixture
def admin_b_headers(workspace_b_id: UUID) -> dict[str, str]:
    return {
        "Authorization": "Bearer user-admin-b",
        "X-Workspace-Id": str(workspace_b_id),
    }


@pytest.fixture
def rep_b_headers(workspace_b_id: UUID) -> dict[str, str]:
    return {
        "Authorization": "Bearer user-rep-b",
        "X-Workspace-Id": str(workspace_b_id),
    }


@pytest_asyncio.fixture
async def integration_client(
    int_state_repo: InMemoryStateRepository,
    int_visit_repo: InMemoryVisitRepository,
    int_verification_repo: InMemoryVerificationRepository,
    int_catalog_repo: InMemoryCatalogRepository,
    int_policy_repo: InMemoryPolicyRepository,
    int_blob_repo: LocalFileSystemBlobRepository,
    int_analytics_repo: DuckDBAnalyticsRepository,
    int_gateway: DeterministicModelGateway,
    frozen_clock: IntegrationFrozenClock,
):
    app.dependency_overrides[get_visit_repository] = lambda: int_visit_repo
    app.dependency_overrides[get_verification_repository] = lambda: int_verification_repo
    app.dependency_overrides[get_catalog_repository] = lambda: int_catalog_repo
    app.dependency_overrides[get_policy_repository] = lambda: int_policy_repo
    app.dependency_overrides[get_blob_repository] = lambda: int_blob_repo

    set_clock(frozen_clock)
    set_verification_repository(int_verification_repo)
    set_visit_repository(int_visit_repo)
    set_catalog_repository(int_catalog_repo)
    set_policy_repository(int_policy_repo)
    set_blob_repository(int_blob_repo)
    set_analytics_repository(int_analytics_repo)
    set_model_gateway(int_gateway)
    set_verification_model_gateway(int_gateway)
    set_policy_model_gateway(int_gateway)

    async def _test_upload_media_bytes(request: StarletteRequest) -> StarletteResponse:
        from uuid import UUID

        media_id = UUID(request.path_params["media_id"])
        raw = await request.body()
        await int_blob_repo.finalize_upload(media_id, raw_bytes=raw)
        return StarletteResponse(status_code=200)

    upload_route = Route(
        "/media/upload/{media_id}",
        _test_upload_media_bytes,
        methods=["PUT"],
    )
    app.routes.insert(0, upload_route)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            yield test_client
    finally:
        if upload_route in app.routes:
            app.routes.remove(upload_route)
        app.dependency_overrides.clear()
