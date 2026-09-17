import shutil
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from storeops_contracts.models import (
    Currency,
    Kind4,
    Kind5,
    Location,
    PolicySource,
    PolicyVersion,
    Product,
    Promotion,
    Rule,
    Store,
    Type1,
    Workspace,
    ZoneKind,
)

from apps.api.adapters.blob.local_fs import LocalFileSystemBlobRepository
from apps.api.adapters.state.in_memory import InMemoryStateRepository
from apps.api.ai.gateway import DeterministicModelGateway
from apps.api.analytics.duckdb import DuckDBAnalyticsRepository
from apps.api.core.auth import set_state_repository
from apps.api.main import app
from apps.api.modules.catalog.dependencies import (
    set_blob_repository,
    set_catalog_repository,
)
from apps.api.modules.catalog.repository import InMemoryCatalogRepository
from apps.api.modules.catalog.router import router as catalog_router
from apps.api.modules.imports.dependencies import set_analytics_repository
from apps.api.modules.policies.dependencies import (
    set_model_gateway as set_policy_model_gateway,
)
from apps.api.modules.policies.dependencies import (
    set_policy_repository,
)
from apps.api.modules.policies.repository import InMemoryPolicyRepository
from apps.api.modules.policies.router import router as policy_router
from apps.api.modules.visits.dependencies import (
    set_model_gateway,
    set_visit_repository,
)
from apps.api.modules.visits.repository import InMemoryVisitRepository

# Include routers if not yet registered in main app
if not any(getattr(route, "path", None) == "/stores" for route in app.routes):
    app.include_router(catalog_router)

if not any(getattr(route, "path", None) == "/promotions" for route in app.routes):
    app.include_router(policy_router)


@pytest.fixture
def temp_media_dir():
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def blob_repo(temp_media_dir):
    repo = LocalFileSystemBlobRepository(base_dir=temp_media_dir)
    set_blob_repository(repo)
    return repo


@pytest.fixture
def catalog_repo():
    repo = InMemoryCatalogRepository()
    set_catalog_repository(repo)
    return repo


@pytest.fixture
def policy_repo():
    repo = InMemoryPolicyRepository()
    set_policy_repository(repo)
    return repo


@pytest.fixture
def visit_repo():
    repo = InMemoryVisitRepository()
    set_visit_repository(repo)
    return repo


@pytest.fixture
def analytics_repo(tmp_path):
    repo = DuckDBAnalyticsRepository(db_path=str(tmp_path / "analytics.duckdb"))
    set_analytics_repository(repo)
    return repo


class ConfigurableModelGateway(DeterministicModelGateway):
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

        # Default smart synthesizer for AnalysisProposal in tests
        if response_schema.__name__ == "AnalysisProposal":
            import re

            from apps.api.ai.schemas import (
                Alternative,
                AnalysisProposal,
                ProposedAction,
                ProposedClaim,
            )

            # Find evidence_ids from <available_evidence_ids> block
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

            # Find rule_ids
            rule_ids: list[UUID] = []
            rule_match = re.search(r'"rule_id":\s*"([^"]+)"', prompt)
            if rule_match:
                try:
                    rule_ids.append(UUID(rule_match.group(1)))
                except ValueError:
                    pass
            if not rule_ids:
                rule_match2 = re.search(r'"id":\s*"([^"]+)"', prompt)
                if rule_match2:
                    try:
                        rule_ids.append(UUID(rule_match2.group(1)))
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

        from apps.api.ai.gateway import ModelSchemaError

        raise ModelSchemaError(
            f"No deterministic response registered for schema {response_schema.__name__} in DeterministicModelGateway."
        )


@pytest.fixture
def model_gateway():
    gateway = ConfigurableModelGateway()
    set_model_gateway(gateway)
    set_policy_model_gateway(gateway)
    return gateway


@pytest_asyncio.fixture
async def state_repo():
    repo = InMemoryStateRepository()
    set_state_repository(repo)
    return repo


@pytest_asyncio.fixture
async def client(
    state_repo,
    catalog_repo,
    policy_repo,
    visit_repo,
    blob_repo,
    model_gateway,
    analytics_repo,
):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as test_client:
        yield test_client


@pytest_asyncio.fixture
async def workspace_setup(state_repo):
    now = datetime.now(UTC)
    ws_id = uuid4()
    admin_uid = "admin-user"
    rep_uid = "rep-user"

    workspace = Workspace(
        id=ws_id,
        workspace_id=ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        name="Test Supermarket Workspace",
        brand_name="Test Brand",
        currency=Currency.SGD,
    )
    await state_repo.create_workspace_with_admin(
        workspace, uid=admin_uid, email="admin@test.com"
    )
    await state_repo.add_membership(
        ws_id, uid=rep_uid, role="REP", email="rep@test.com"
    )

    return {
        "workspace_id": ws_id,
        "admin_uid": admin_uid,
        "rep_uid": rep_uid,
        "admin_headers": {
            "Authorization": "Bearer admin-user",
            "X-Workspace-Id": str(ws_id),
        },
        "rep_headers": {
            "Authorization": "Bearer rep-user",
            "X-Workspace-Id": str(ws_id),
        },
    }


@pytest_asyncio.fixture
async def sample_store(catalog_repo, workspace_setup):
    ws_id = workspace_setup["workspace_id"]
    now = datetime.now(UTC)
    store_id = uuid4()
    backroom_id = uuid4()

    backroom = Location(
        id=backroom_id,
        workspace_id=ws_id,
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
        workspace_id=ws_id,
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
    saved_store, _ = await catalog_repo.create_store_with_backroom(store, backroom)
    return saved_store


@pytest_asyncio.fixture
async def sample_product(catalog_repo, workspace_setup):
    ws_id = workspace_setup["workspace_id"]
    now = datetime.now(UTC)
    product_id = uuid4()
    product = Product(
        id=product_id,
        workspace_id=ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        sku="SKU-CHOC-001",
        name="Artisan Dark Chocolate 100g",
        case_units=12,
        active=True,
        reference_media_ids=[],
    )
    return await catalog_repo.create_product(product)


@pytest_asyncio.fixture
async def sample_promotion_with_policy(
    policy_repo, sample_store, sample_product, workspace_setup
):
    ws_id = workspace_setup["workspace_id"]
    now = datetime.now(UTC)
    promo_id = uuid4()
    policy_ver_id = uuid4()
    rule_id = uuid4()

    rule = Rule(
        rule_id=rule_id,
        kind=Kind5.MIN_FACINGS,
        zone_id="shelf-1",
        zone_kind=ZoneKind.SHELF,
        product_id=sample_product.id,
        min_facings=3,
        source=PolicySource(
            kind=Kind4.DOCUMENT,
            media_id=uuid4(),
            page=1,
            quote="3 facings minimum on eye level shelf",
            reviewer_note=None,
        ),
    )

    policy_ver = PolicyVersion(
        id=policy_ver_id,
        promotion_id=promo_id,
        version=1,
        rules=[rule],
        catalog_product_ids=[sample_product.id],
        store_ids=[sample_store.id],
        starts_on=date(2026, 8, 1),
        ends_on=date(2026, 8, 31),
        approved_at=now,
        approved_by="admin-user",
        content_sha256="d" * 64,
    )
    await policy_repo.create_policy_version(ws_id, policy_ver)

    promo = Promotion(
        id=promo_id,
        workspace_id=ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        name="August Chocolate Extravaganza",
        starts_on=date(2026, 8, 1),
        ends_on=date(2026, 8, 31),
        store_ids=[sample_store.id],
        agreement_media_id=None,
        archived=False,
        draft_revision=1,
        extracted_rules=[],
        extraction_gaps=[],
        approved_policy=policy_ver,
    )
    await policy_repo.create_promotion(ws_id, promo)
    return promo, policy_ver, rule
