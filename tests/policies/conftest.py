import hashlib
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from storeops_contracts.models import (
    Currency,
    Kind,
    Location,
    Media,
    Product,
    Status1,
    Store,
    Type1,
    Workspace,
)

from apps.api.adapters.blob.local_fs import LocalFileSystemBlobRepository
from apps.api.adapters.state.in_memory import InMemoryStateRepository
from apps.api.ai.gateway import DeterministicModelGateway
from apps.api.core.auth import set_state_repository
from apps.api.main import app
from apps.api.modules.catalog.dependencies import (
    set_blob_repository,
    set_catalog_repository,
)
from apps.api.modules.catalog.repository import InMemoryCatalogRepository
from apps.api.modules.catalog.router import router as catalog_router
from apps.api.modules.policies.dependencies import (
    set_model_gateway,
    set_policy_repository,
)
from apps.api.modules.policies.repository import InMemoryPolicyRepository
from apps.api.modules.policies.router import router as policy_router

# Mount catalog router if not present
if not any(getattr(route, "path", None) == "/stores" for route in app.routes):
    app.include_router(catalog_router)

# Mount policy router if not present
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
def model_gateway():
    gateway = DeterministicModelGateway()
    set_model_gateway(gateway)
    return gateway


@pytest_asyncio.fixture
async def state_repo():
    repo = InMemoryStateRepository()
    set_state_repository(repo)
    return repo


@pytest_asyncio.fixture
async def client(state_repo, catalog_repo, policy_repo, blob_repo, model_gateway):
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
        name="Nordic Retail Workspace",
        brand_name="Nordic Retail",
        currency=Currency.SGD,
    )
    await state_repo.create_workspace_with_admin(
        workspace, uid=admin_uid, email="admin@example.com"
    )
    await state_repo.add_membership(
        ws_id, uid=rep_uid, role="REP", email="rep@example.com"
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
        code="LOC-BACKROOM-1",
        name="Main Backroom",
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
        name="Downtown Flagship",
        code="STORE-101",
        retailer="Nordic Mart",
        region="North",
        format="HYPERMARKET",
        currency=Currency.SGD,
        timezone="Europe/Stockholm",
        distributor_location_id=None,
        backroom_location_id=backroom_id,
        active=True,
    )
    await catalog_repo.create_store_with_backroom(store, backroom)
    return store


@pytest_asyncio.fixture
async def sample_products(catalog_repo, workspace_setup):
    ws_id = workspace_setup["workspace_id"]
    now = datetime.now(UTC)
    products = []
    for i in range(1, 4):
        p = Product(
            id=uuid4(),
            workspace_id=ws_id,
            version=1,
            created_at=now,
            updated_at=now,
            sku=f"COFFEE-00{i}",
            name=f"Premium Coffee Blend {i}",
            case_units=12,
            reference_media_ids=[],
            active=True,
        )
        created = await catalog_repo.create_product(p)
        products.append(created)
    return products


@pytest_asyncio.fixture
async def sample_agreement_media(catalog_repo, blob_repo, workspace_setup):
    ws_id = workspace_setup["workspace_id"]
    now = datetime.now(UTC)
    media_id = uuid4()
    pdf_content = b"%PDF-1.4 Mock Vendor Agreement content for testing"
    sha256_hash = hashlib.sha256(pdf_content).hexdigest()

    # Save to blob storage
    await blob_repo.finalize_upload(media_id, pdf_content)

    media = Media(
        id=media_id,
        workspace_id=ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        kind=Kind.AGREEMENT,
        filename="vendor_agreement_2026.pdf",
        mime_type="application/pdf",
        status=Status1.READY,
        store_id=None,
        visit_id=None,
        product_id=None,
        zone_id=None,
        zone_kind=None,
        captured_at=None,
        original_sha256=sha256_hash,
        normalized_sha256=sha256_hash,
        byte_size=len(pdf_content),
        width=None,
        height=None,
        rejection=None,
        download_url=None,
        download_url_expires_at=None,
    )
    return await catalog_repo.create_media(media)
