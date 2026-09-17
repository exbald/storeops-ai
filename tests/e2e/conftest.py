"""E2E browser workflow integration fixtures."""

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
from apps.api.core.auth import UserContext, set_state_repository
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


class FrozenClock(Clock):
    def __init__(self, fixed_now: datetime | None = None) -> None:
        self._now = fixed_now or datetime.now(UTC)

    def now_utc(self) -> datetime:
        return self._now

    def advance(self, td: timedelta) -> None:
        self._now += td


@pytest.fixture
def test_workspace_id() -> UUID:
    return uuid4()


@pytest.fixture
def rep_user() -> UserContext:
    return UserContext(uid="test-rep-token", email="rep@storeops.test")


@pytest.fixture
def admin_user() -> UserContext:
    return UserContext(uid="test-admin-token", email="admin@storeops.test")


@pytest.fixture
def frozen_clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC))


@pytest.fixture
def memory_visit_repo() -> InMemoryVisitRepository:
    return InMemoryVisitRepository()


@pytest.fixture
def memory_verification_repo() -> InMemoryVerificationRepository:
    return InMemoryVerificationRepository()


@pytest.fixture
def memory_catalog_repo() -> InMemoryCatalogRepository:
    return InMemoryCatalogRepository()


@pytest.fixture
def memory_policy_repo() -> InMemoryPolicyRepository:
    return InMemoryPolicyRepository()


@pytest.fixture
def memory_blob_repo(tmp_path: Path) -> LocalFileSystemBlobRepository:
    return LocalFileSystemBlobRepository(base_dir=tmp_path / "blobs")


@pytest.fixture
def memory_analytics_repo() -> DuckDBAnalyticsRepository:
    return DuckDBAnalyticsRepository(db_path=":memory:")


import re
from typing import Any

from apps.api.ai.gateway import ModelSchemaError
from apps.api.ai.schemas import (
    Alternative,
    AnalysisProposal,
    ImageObservation,
    ProposedAction,
    ProposedCheck,
    ProposedClaim,
    VerificationProposal,
)


class ConfigurableE2EGateway(DeterministicModelGateway):
    def __init__(self) -> None:
        super().__init__()
        self.call_history: list[dict[str, Any]] = []

    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[Any],
        images: list[bytes] | None = None,
        pdfs: list[bytes] | None = None,
        thinking_budget: str | None = None,
    ) -> Any:
        self.call_history.append(
            {
                "prompt": prompt,
                "response_schema": response_schema,
                "images_count": len(images) if images else 0,
                "pdfs_count": len(pdfs) if pdfs else 0,
                "thinking_budget": thinking_budget,
            }
        )

        if response_schema in self._registry:
            resp = self._registry[response_schema]
            if callable(resp):
                return resp(prompt)
            if isinstance(resp, Exception):
                raise resp
            return resp

        if response_schema.__name__ == "AnalysisProposal":
            # Extract evidence IDs
            ev_match = re.search(
                r"<available_evidence_ids>(.*?)</available_evidence_ids>",
                prompt,
                re.DOTALL,
            )
            evidence_ids: list[UUID] = []
            if ev_match:
                for raw_id in re.findall(
                    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                    ev_match.group(1),
                ):
                    try:
                        evidence_ids.append(UUID(raw_id))
                    except ValueError:
                        pass

            rule_ids: list[UUID] = []
            for match in re.finditer(r'"rule_id":\s*"([^"]+)"', prompt):
                try:
                    rule_ids.append(UUID(match.group(1)))
                except ValueError:
                    pass
            if not rule_ids:
                for match in re.finditer(r'"id":\s*"([^"]+)"', prompt):
                    try:
                        rule_ids.append(UUID(match.group(1)))
                    except ValueError:
                        pass

            eid = evidence_ids[0] if evidence_ids else uuid4()
            return AnalysisProposal(
                hypothesis="EXECUTION",
                summary="Detected facing shortfall against approved policy rule.",
                claims=[
                    ProposedClaim(
                        claim_key="c1",
                        kind="OBSERVATION",
                        text="Facing count on eye-level shelf is below required minimum.",
                        evidence_ids=[eid],
                    )
                ],
                alternatives=[
                    Alternative(
                        hypothesis="SUPPLY_CONSTRAINT",
                        reason="Potential warehouse depletion.",
                        evidence_ids=[eid],
                    )
                ],
                actions=[
                    ProposedAction(
                        kind="RESTORE_FACINGS",
                        rule_ids=rule_ids,
                        claim_keys=["c1"],
                        evidence_ids=[eid],
                        instruction="Restore product facings to 3 on eye-level shelf.",
                        required_zone_ids=["shelf-1"],
                    )
                ],
                unresolved_questions=[],
            )

        if response_schema.__name__ == "ImageObservation":
            med_match = re.search(r'"media_id":\s*"([^"]+)"', prompt)
            mid = UUID(med_match.group(1)) if med_match else uuid4()
            return ImageObservation(
                media_id=mid,
                zone_id="shelf-main",
                zone_kind="SHELF",
                quality="CLEAR",
                coverage="FULL",
                occluded=False,
                detections=[],
                display="PRESENT",
                limitations=[],
            )

        if response_schema.__name__ == "VerificationProposal":
            rule_ids = []
            for match in re.finditer(r'"rule_id":\s*"([^"]+)"', prompt):
                try:
                    rule_ids.append(UUID(match.group(1)))
                except ValueError:
                    pass

            ev_ids = []
            ev_match = re.search(
                r"Valid Evidence IDs:\s*\[(.*?)\]", prompt, re.DOTALL
            )
            if ev_match:
                for raw_id in re.findall(
                    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                    ev_match.group(1),
                ):
                    try:
                        ev_ids.append(UUID(raw_id))
                    except ValueError:
                        pass
            if not ev_ids:
                for match in re.finditer(r'"media_id":\s*"([^"]+)"', prompt):
                    try:
                        ev_ids.append(UUID(match.group(1)))
                    except ValueError:
                        pass

            target_ev = ev_ids[:1] if ev_ids else []
            checks = [
                ProposedCheck(
                    rule_id=rid,
                    result="PASS",
                    evidence_ids=target_ev,
                    explanation="Observed full compliance in verification imagery.",
                )
                for rid in rule_ids
            ]
            return VerificationProposal(checks=checks, requested_retakes=[])

        raise ModelSchemaError(
            f"No deterministic response registered for schema {response_schema.__name__} in ConfigurableE2EGateway."
        )


@pytest.fixture
def deterministic_gateway() -> ConfigurableE2EGateway:
    return ConfigurableE2EGateway()


@pytest_asyncio.fixture
async def memory_state_repo(test_workspace_id: UUID) -> InMemoryStateRepository:
    repo = InMemoryStateRepository()
    now = datetime.now(UTC)
    workspace = Workspace(
        id=test_workspace_id,
        workspace_id=test_workspace_id,
        version=1,
        created_at=now,
        updated_at=now,
        name="E2E Test Workspace",
        brand_name="Test Brand",
        currency=Currency.SGD,
    )
    await repo.create_workspace_with_admin(
        workspace, uid="test-admin-token", email="admin@test.com"
    )
    await repo.add_membership(
        test_workspace_id, uid="test-rep-token", role="REP", email="rep@test.com"
    )
    set_state_repository(repo)
    return repo


@pytest.fixture
def auth_headers(test_workspace_id: UUID) -> dict[str, str]:
    return {
        "Authorization": "Bearer test-rep-token",
        "X-Workspace-Id": str(test_workspace_id),
    }


@pytest.fixture
def admin_headers(test_workspace_id: UUID) -> dict[str, str]:
    return {
        "Authorization": "Bearer test-admin-token",
        "X-Workspace-Id": str(test_workspace_id),
    }


@pytest_asyncio.fixture
async def e2e_client(
    memory_state_repo: InMemoryStateRepository,
    memory_visit_repo: InMemoryVisitRepository,
    memory_verification_repo: InMemoryVerificationRepository,
    memory_catalog_repo: InMemoryCatalogRepository,
    memory_policy_repo: InMemoryPolicyRepository,
    memory_blob_repo: LocalFileSystemBlobRepository,
    memory_analytics_repo: DuckDBAnalyticsRepository,
    deterministic_gateway: DeterministicModelGateway,
    frozen_clock: FrozenClock,
):
    app.dependency_overrides[get_visit_repository] = lambda: memory_visit_repo
    app.dependency_overrides[get_verification_repository] = lambda: (
        memory_verification_repo
    )
    app.dependency_overrides[get_catalog_repository] = lambda: memory_catalog_repo
    app.dependency_overrides[get_policy_repository] = lambda: memory_policy_repo
    app.dependency_overrides[get_blob_repository] = lambda: memory_blob_repo

    set_clock(frozen_clock)
    set_verification_repository(memory_verification_repo)
    set_visit_repository(memory_visit_repo)
    set_catalog_repository(memory_catalog_repo)
    set_policy_repository(memory_policy_repo)
    set_blob_repository(memory_blob_repo)
    set_analytics_repository(memory_analytics_repo)
    set_model_gateway(deterministic_gateway)
    set_verification_model_gateway(deterministic_gateway)
    set_policy_model_gateway(deterministic_gateway)

    async def _test_upload_media_bytes(
        request: StarletteRequest,
    ) -> StarletteResponse:
        from uuid import UUID

        media_id = UUID(request.path_params["media_id"])
        raw = await request.body()
        await memory_blob_repo.finalize_upload(media_id, raw_bytes=raw)
        return StarletteResponse(status_code=200)

    upload_route = Route(
        "/media/upload/{media_id}",
        _test_upload_media_bytes,
        methods=["PUT"],
    )
    app.routes.insert(0, upload_route)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as test_client:
            yield test_client
    finally:
        if upload_route in app.routes:
            app.routes.remove(upload_route)
        app.dependency_overrides.clear()
