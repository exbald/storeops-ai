"""Verification test fixtures and doubles."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from storeops_contracts.models import (
    Action,
    Claim,
    Currency,
    Diagnosis,
    Hypothesis,
    Investigation,
    Kind,
    Kind4,
    Kind5,
    Kind6,
    Kind7,
    Location,
    Media,
    PolicySource,
    PolicyVersion,
    Product,
    Promotion,
    RequiredZoneId,
    Rule,
    State,
    Status1,
    Status5,
    Status6,
    Store,
    Support,
    Type1,
    Visit,
    Workspace,
    ZoneKind,
)

from apps.api.adapters.blob.local_fs import LocalFileSystemBlobRepository
from apps.api.adapters.state.in_memory import InMemoryStateRepository
from apps.api.ai.gateway import DeterministicModelGateway, ModelSchemaError
from apps.api.core.auth import (
    UserContext,
    set_state_repository,
)
from apps.api.main import app
from apps.api.modules.catalog.dependencies import (
    get_blob_repository,
    get_catalog_repository,
)
from apps.api.modules.catalog.repository import InMemoryCatalogRepository
from apps.api.modules.policies.dependencies import get_policy_repository
from apps.api.modules.policies.repository import InMemoryPolicyRepository
from apps.api.modules.verification.dependencies import (
    get_verification_repository,
    set_clock,
    set_verification_repository,
)
from apps.api.modules.verification.repository import InMemoryVerificationRepository
from apps.api.modules.verification.router import router as verification_router
from apps.api.modules.visits.dependencies import (
    get_visit_repository,
    set_visit_repository,
)
from apps.api.modules.visits.repository import InMemoryVisitRepository

# Mount verification router in test app if not already mounted
if not any(
    getattr(r, "path", None) == "/investigations/{investigation_id}/verify"
    for r in app.routes
):
    app.include_router(verification_router)


class FrozenClock:
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
        name="Verification Test Workspace",
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
async def client(
    memory_state_repo: InMemoryStateRepository,
    memory_visit_repo: InMemoryVisitRepository,
    memory_verification_repo: InMemoryVerificationRepository,
    memory_catalog_repo: InMemoryCatalogRepository,
    memory_policy_repo: InMemoryPolicyRepository,
    memory_blob_repo: LocalFileSystemBlobRepository,
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

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def sample_store(
    test_workspace_id: UUID, memory_catalog_repo: InMemoryCatalogRepository
) -> Store:
    now = datetime.now(UTC)
    store_id = uuid4()
    backroom_id = uuid4()

    backroom = Location(
        id=backroom_id,
        workspace_id=test_workspace_id,
        version=1,
        created_at=now,
        updated_at=now,
        name="Backroom Storage",
        code="BR-01",
        type=Type1.BACKROOM,
        store_id=store_id,
        active=True,
    )

    store = Store(
        id=store_id,
        workspace_id=test_workspace_id,
        version=1,
        created_at=now,
        updated_at=now,
        code="STR-001",
        name="Jurong East Superstore",
        retailer="FairPrice",
        region="SG-West",
        format="HYPERMARKET",
        timezone="Asia/Singapore",
        currency=Currency.SGD,
        backroom_location_id=backroom_id,
        distributor_location_id=None,
        active=True,
    )
    saved_store, _ = await memory_catalog_repo.create_store_with_backroom(
        store, backroom
    )
    return saved_store


@pytest_asyncio.fixture
async def sample_product(
    test_workspace_id: UUID, memory_catalog_repo: InMemoryCatalogRepository
) -> Product:
    now = datetime.now(UTC)
    prod = Product(
        id=uuid4(),
        workspace_id=test_workspace_id,
        sku="SKU-CHIPS-01",
        name="Sea Salt Chips 150g",
        case_units=12,
        reference_media_ids=[],
        created_at=now,
        updated_at=now,
        version=1,
        active=True,
    )
    return await memory_catalog_repo.create_product(prod)


@pytest_asyncio.fixture
async def sample_promotion_and_policy(
    test_workspace_id: UUID,
    sample_store: Store,
    sample_product: Product,
    memory_policy_repo: InMemoryPolicyRepository,
) -> tuple[Promotion, PolicyVersion]:
    now = datetime.now(UTC)
    promo_id = uuid4()
    pol_ver_id = uuid4()

    rule1 = Rule(
        rule_id=uuid4(),
        kind=Kind5.MIN_FACINGS,
        product_id=sample_product.id,
        zone_id="zone-shelf-1",
        zone_kind=ZoneKind.SHELF,
        min_facings=3,
        source=PolicySource(
            kind=Kind4.DOCUMENT,
            page=1,
            quote="Product must have at least 3 front facings on main eye-level shelf.",
            media_id=None,
            reviewer_note=None,
        ),
    )
    rule2 = Rule(
        rule_id=uuid4(),
        kind=Kind5.REQUIRED_DISPLAY,
        product_id=sample_product.id,
        zone_id="zone-endcap-1",
        zone_kind=ZoneKind.DISPLAY,
        min_facings=None,
        source=PolicySource(
            kind=Kind4.DOCUMENT,
            page=2,
            quote="Endcap promotional feature display must be installed.",
            media_id=None,
            reviewer_note=None,
        ),
    )

    pol_ver = PolicyVersion(
        id=pol_ver_id,
        promotion_id=promo_id,
        version=1,
        rules=[rule1, rule2],
        catalog_product_ids=[sample_product.id],
        store_ids=[sample_store.id],
        starts_on=date(2026, 8, 1),
        ends_on=date(2026, 8, 31),
        approved_at=now,
        approved_by="admin-user",
        content_sha256="d" * 64,
    )
    await memory_policy_repo.create_policy_version(test_workspace_id, pol_ver)

    promo = Promotion(
        id=promo_id,
        workspace_id=test_workspace_id,
        version=1,
        created_at=now,
        updated_at=now,
        name="Autumn Snack Promo 2026",
        starts_on=date(2026, 8, 1),
        ends_on=date(2026, 8, 31),
        store_ids=[sample_store.id],
        agreement_media_id=None,
        archived=False,
        draft_revision=1,
        extracted_rules=[],
        extraction_gaps=[],
        approved_policy=pol_ver,
    )
    await memory_policy_repo.create_promotion(test_workspace_id, promo)
    return promo, pol_ver


@pytest_asyncio.fixture
async def sample_before_media(
    test_workspace_id: UUID,
    sample_store: Store,
    frozen_clock: FrozenClock,
    memory_catalog_repo: InMemoryCatalogRepository,
    memory_blob_repo: LocalFileSystemBlobRepository,
) -> Media:
    now = frozen_clock.now_utc() - timedelta(minutes=10)
    mid = uuid4()
    raw_b = b"before image data bytes " + str(mid).encode()
    path = memory_blob_repo._file_path(mid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw_b)

    media = Media(
        id=mid,
        workspace_id=test_workspace_id,
        version=1,
        created_at=now,
        updated_at=now,
        kind=Kind.VISIT_BEFORE,
        filename="before.jpg",
        mime_type="image/jpeg",
        status=Status1.READY,
        store_id=sample_store.id,
        visit_id=None,
        product_id=None,
        zone_id="zone-shelf-1",
        zone_kind=ZoneKind.SHELF,
        captured_at=now,
        original_sha256="1" * 64,
        normalized_sha256="1" * 64,
        byte_size=len(raw_b),
        width=1000,
        height=800,
        rejection=None,
        download_url=None,
        download_url_expires_at=None,
    )
    return await memory_catalog_repo.create_media(media)


@pytest_asyncio.fixture
async def sample_visit(
    test_workspace_id: UUID,
    sample_store: Store,
    sample_before_media: Media,
    frozen_clock: FrozenClock,
    memory_visit_repo: InMemoryVisitRepository,
    memory_catalog_repo: InMemoryCatalogRepository,
) -> Visit:
    now = frozen_clock.now_utc() - timedelta(minutes=15)
    visit = Visit(
        id=uuid4(),
        workspace_id=test_workspace_id,
        version=1,
        created_at=now,
        updated_at=now,
        store_id=sample_store.id,
        status=Status5.OPEN,
        before_media_ids=[sample_before_media.id],
        after_media_ids=[],
        active_investigation_id=None,
        report_ids=[],
        visit_started_at=now,
        notes="Routine promotional compliance check",
    )
    return await memory_visit_repo.create_visit(test_workspace_id, visit)


@pytest_asyncio.fixture
async def sample_investigation_accepted(
    test_workspace_id: UUID,
    sample_store: Store,
    sample_visit: Visit,
    sample_promotion_and_policy: tuple[Promotion, PolicyVersion],
    frozen_clock: FrozenClock,
    memory_visit_repo: InMemoryVisitRepository,
) -> tuple[Investigation, list[Action]]:
    promo, pol_ver = sample_promotion_and_policy
    now = frozen_clock.now_utc() - timedelta(minutes=5)
    inv_id = uuid4()
    snapshot_id = uuid4()

    claim_id1 = uuid4()
    claim_id2 = uuid4()
    evidence_id = uuid4()

    claim1 = Claim(
        id=claim_id1,
        kind=Kind6.OBSERVATION,
        text="Shelf out of compliance",
        evidence_ids=[evidence_id],
    )
    claim2 = Claim(
        id=claim_id2,
        kind=Kind6.OBSERVATION,
        text="Endcap display missing",
        evidence_ids=[evidence_id],
    )

    action1 = Action(
        id=uuid4(),
        kind=Kind7.RESTORE_FACINGS,
        rule_ids=[pol_ver.rules[0].rule_id],
        claim_ids=[claim_id1],
        evidence_ids=[evidence_id],
        instruction="Restore 3 front facings on eye level shelf",
        required_zone_ids=[RequiredZoneId(root="zone-shelf-1")],
        status=Status6.CLAIMED_DONE,
    )
    action2 = Action(
        id=uuid4(),
        kind=Kind7.INSTALL_DISPLAY,
        rule_ids=[pol_ver.rules[1].rule_id],
        claim_ids=[claim_id2],
        evidence_ids=[evidence_id],
        instruction="Assemble and install endcap feature display",
        required_zone_ids=[RequiredZoneId(root="zone-endcap-1")],
        status=Status6.CLAIMED_DONE,
    )

    diagnosis = Diagnosis(
        hypothesis=Hypothesis.EXECUTION,
        support=Support.SUPPORTED,
        summary="Shelf out of compliance and endcap missing",
        claims=[claim1, claim2],
        alternatives=[],
        unresolved_questions=[],
    )

    inv = Investigation(
        id=inv_id,
        workspace_id=test_workspace_id,
        version=2,
        created_at=now,
        updated_at=now,
        store_id=sample_store.id,
        visit_id=sample_visit.id,
        promotion_id=promo.id,
        policy_version_id=pol_ver.id,
        snapshot_id=snapshot_id,
        snapshot_at=now,
        metrics=None,
        state=State.ACCEPTED,
        plan_revision=1,
        diagnosis=diagnosis,
        actions=[action1, action2],
        latest_verification_id=None,
        current_job_id=uuid4(),
        accepted_at=now,
        accepted_by="rep-user-1",
        policy_stale=False,
    )
    saved_inv = await memory_visit_repo.create_investigation(test_workspace_id, inv)

    sample_visit.active_investigation_id = inv_id
    sample_visit.version += 1
    sample_visit.updated_at = now
    await memory_visit_repo.update_visit(test_workspace_id, sample_visit)

    return saved_inv, [action1, action2]


@pytest.fixture
def make_after_media(
    test_workspace_id: UUID,
    sample_store: Store,
    sample_visit: Visit,
    frozen_clock: FrozenClock,
    memory_catalog_repo: InMemoryCatalogRepository,
    memory_blob_repo: LocalFileSystemBlobRepository,
):
    async def _make(
        visit_id: UUID | None = None,
        store_id: UUID | None = None,
        captured_at: datetime | None = None,
        sha256: str = "2" * 64,
        filename: str = "after.jpg",
        zone_id: str = "zone-shelf-1",
        zone_kind: ZoneKind = ZoneKind.SHELF,
        image_bytes: bytes | None = None,
    ) -> Media:
        now = frozen_clock.now_utc()
        mid = uuid4()
        raw_b = image_bytes or (b"test image data bytes " + str(mid).encode())
        path = memory_blob_repo._file_path(mid)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw_b)

        m = Media(
            id=mid,
            workspace_id=test_workspace_id,
            version=1,
            created_at=now,
            updated_at=now,
            kind=Kind.VISIT_AFTER,
            filename=filename,
            mime_type="image/jpeg",
            status=Status1.READY,
            store_id=store_id if store_id is not None else sample_store.id,
            visit_id=visit_id if visit_id is not None else sample_visit.id,
            product_id=None,
            zone_id=zone_id,
            zone_kind=zone_kind,
            captured_at=captured_at if captured_at is not None else now,
            original_sha256=sha256,
            normalized_sha256=sha256,
            byte_size=len(raw_b),
            width=1920,
            height=1080,
            rejection=None,
            download_url=None,
            download_url_expires_at=None,
        )
        return await memory_catalog_repo.create_media(m)

    return _make


class ScenarioModelGateway(DeterministicModelGateway):
    """Deterministic gateway supporting sequenced or schema-registered responses."""

    def __init__(self) -> None:
        super().__init__()
        self._queues: dict[type[Any], list[Any]] = {}

    def register_queue(self, schema_type: type[Any], responses: list[Any]) -> None:
        self._queues[schema_type] = list(responses)

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
        if self._queues.get(response_schema):
            resp = self._queues[response_schema].pop(0)
            if isinstance(resp, Exception):
                raise resp
            return resp
        if response_schema in self._registry:
            resp = self._registry[response_schema]
            if isinstance(resp, Exception):
                raise resp
            return resp
        raise ModelSchemaError(
            f"No deterministic response registered for schema {response_schema.__name__} in ScenarioModelGateway."
        )
