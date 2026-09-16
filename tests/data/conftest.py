import hashlib
import shutil
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from storeops_contracts.models import (
    Currency,
    Location,
    Product,
    Store,
    Type1,
    Workspace,
)

from apps.api.adapters.blob.local_fs import LocalFileSystemBlobRepository
from apps.api.adapters.state.in_memory import InMemoryStateRepository
from apps.api.analytics.duckdb import DuckDBAnalyticsRepository
from apps.api.core.auth import set_state_repository
from apps.api.main import app
from apps.api.modules.catalog.dependencies import (
    set_blob_repository,
    set_catalog_repository,
)
from apps.api.modules.catalog.repository import InMemoryCatalogRepository
from apps.api.modules.catalog.router import router as catalog_router
from apps.api.modules.imports.dependencies import (
    set_analytics_repository,
    set_import_repository,
)
from apps.api.modules.imports.repository import ImportRepository
from apps.api.modules.imports.router import router as imports_router
from apps.api.ports.clock import SystemClock

# Mount routers on app for data testing if not already present
if not any(getattr(route, "path", None) == "/stores" for route in app.routes):
    app.include_router(catalog_router)

if not any(getattr(route, "path", None) == "/imports" for route in app.routes):
    app.include_router(imports_router)


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
def import_repo():
    repo = ImportRepository()
    set_import_repository(repo)
    return repo


@pytest.fixture
def analytics_repo():
    repo = DuckDBAnalyticsRepository()
    set_analytics_repository(repo)
    return repo


@pytest_asyncio.fixture
async def state_repo():
    repo = InMemoryStateRepository()
    set_state_repository(repo)
    return repo


@pytest_asyncio.fixture
async def client(state_repo, catalog_repo, blob_repo, import_repo, analytics_repo):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as test_client:
        yield test_client


@pytest_asyncio.fixture
async def data_setup(state_repo, catalog_repo, blob_repo, client):
    clock = SystemClock()
    now = clock.now_utc()
    ws_id = uuid4()
    admin_uid = "data-admin"
    rep_uid = "data-rep"

    workspace = Workspace(
        id=ws_id,
        workspace_id=ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        name="Data Analytics Workspace",
        brand_name="StoreOps Retail",
        currency=Currency.SGD,
    )
    await state_repo.create_workspace_with_admin(
        workspace, uid=admin_uid, email="data_admin@example.com"
    )
    await state_repo.add_membership(
        ws_id, uid=rep_uid, role="REP", email="data_rep@example.com"
    )

    admin_headers = {
        "Authorization": f"Bearer {admin_uid}",
        "X-Workspace-Id": str(ws_id),
    }
    rep_headers = {
        "Authorization": f"Bearer {rep_uid}",
        "X-Workspace-Id": str(ws_id),
    }

    # Setup standard catalog:
    # 1. Distributor location
    dist_loc = Location(
        id=uuid4(),
        workspace_id=ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        code="DIST-01",
        name="Main Central Distributor",
        type=Type1.DISTRIBUTOR,
        store_id=None,
        active=True,
    )
    await catalog_repo.create_location(dist_loc)

    store_1_id = uuid4()

    # 2. Store 1 Backroom location
    store_1_loc = Location(
        id=uuid4(),
        workspace_id=ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        code="LOC-STR01",
        name="Store Orchard Backroom",
        type=Type1.BACKROOM,
        store_id=store_1_id,
        active=True,
    )

    # 3. Store 1
    store_1 = Store(
        id=store_1_id,
        workspace_id=ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        code="STR-01",
        name="Store Orchard",
        retailer="FairPrice",
        region="Central",
        format="Hypermarket",
        currency=Currency.SGD,
        timezone="Asia/Singapore",
        active=True,
        distributor_location_id=dist_loc.id,
        backroom_location_id=store_1_loc.id,
    )
    await catalog_repo.create_store_with_backroom(store_1, store_1_loc)

    # 4. Standard Product
    prod_coke = Product(
        id=uuid4(),
        workspace_id=ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        sku="SKU-COKE-330",
        name="Coca-Cola 330ml Can",
        case_units=24,
        reference_media_ids=[],
        active=True,
    )
    await catalog_repo.create_product(prod_coke)

    prod_sprite = Product(
        id=uuid4(),
        workspace_id=ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        sku="SKU-SPRITE-330",
        name="Sprite 330ml Can",
        case_units=24,
        reference_media_ids=[],
        active=True,
    )
    await catalog_repo.create_product(prod_sprite)

    async def upload_csv_media(csv_bytes: bytes) -> str:
        """Helper to create a READY media object for CSV import."""
        sha256 = hashlib.sha256(csv_bytes).hexdigest()
        init_res = await client.post(
            "/media",
            json={
                "kind": "IMPORT",
                "filename": "import.csv",
                "mime_type": "text/csv",
                "byte_size": len(csv_bytes),
                "sha256": sha256,
                "store_id": None,
                "visit_id": None,
                "product_id": None,
                "zone_id": None,
                "zone_kind": None,
                "captured_at": None,
            },
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        )
        assert init_res.status_code == 201, init_res.text
        media_data = init_res.json()
        media_id = media_data["media"]["id"]

        # Write bytes directly to blob repo
        path = blob_repo._file_path(UUID(media_id))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(csv_bytes)

        # Complete media
        comp_res = await client.post(
            f"/media/{media_id}/complete",
            json={"expected_version": 1},
            headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        )
        assert comp_res.status_code == 200, comp_res.text
        assert comp_res.json()["status"] == "READY"
        return media_id

    return {
        "workspace": workspace,
        "admin_headers": admin_headers,
        "rep_headers": rep_headers,
        "store_1": store_1,
        "store_1_loc": store_1_loc,
        "dist_loc": dist_loc,
        "prod_coke": prod_coke,
        "prod_sprite": prod_sprite,
        "upload_csv_media": upload_csv_media,
        "clock": clock,
    }
