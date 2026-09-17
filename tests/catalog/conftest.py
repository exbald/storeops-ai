import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse
from storeops_contracts.models import Currency, Workspace

from apps.api.adapters.blob.local_fs import LocalFileSystemBlobRepository
from apps.api.adapters.state.in_memory import InMemoryStateRepository
from apps.api.core.auth import set_state_repository
from apps.api.main import app
from apps.api.modules.catalog.dependencies import (
    set_blob_repository,
    set_catalog_repository,
)
from apps.api.modules.catalog.repository import InMemoryCatalogRepository
from apps.api.modules.catalog.router import router as catalog_router

# Mount catalog router on main app for catalog testing if not present
if not any(getattr(route, "path", None) == "/stores" for route in app.routes):
    app.include_router(catalog_router)

# Mount test-only byte upload simulation route for testing blob storage
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


@pytest.fixture
def temp_media_dir():
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def catalog_blob_repo(temp_media_dir):
    repo = LocalFileSystemBlobRepository(base_dir=temp_media_dir)
    set_blob_repository(repo)
    return repo


@pytest.fixture
def catalog_repo():
    repo = InMemoryCatalogRepository()
    set_catalog_repository(repo)
    return repo


@pytest_asyncio.fixture
async def catalog_state_repo():
    repo = InMemoryStateRepository()
    set_state_repository(repo)
    return repo


@pytest_asyncio.fixture
async def client(catalog_state_repo, catalog_repo, catalog_blob_repo):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


@pytest_asyncio.fixture
async def workspace_setup(catalog_state_repo):
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
        name="Flagship Workspace",
        brand_name="Nordic Retail",
        currency=Currency.SGD,
    )
    await catalog_state_repo.create_workspace_with_admin(
        workspace, uid=admin_uid, email="admin@example.com"
    )
    await catalog_state_repo.add_membership(
        ws_id, uid=rep_uid, role="REP", email="rep@example.com"
    )

    # Secondary foreign workspace
    foreign_ws_id = uuid4()
    foreign_ws = Workspace(
        id=foreign_ws_id,
        workspace_id=foreign_ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        name="Foreign Workspace",
        brand_name="Other Brand",
        currency=Currency.USD,
    )
    foreign_admin_uid = "foreign-admin"
    await catalog_state_repo.create_workspace_with_admin(
        foreign_ws, uid=foreign_admin_uid, email="foreign@example.com"
    )

    return {
        "workspace": workspace,
        "workspace_id": ws_id,
        "admin_uid": admin_uid,
        "admin_headers": {
            "Authorization": f"Bearer {admin_uid}",
            "X-Workspace-Id": str(ws_id),
        },
        "rep_uid": rep_uid,
        "rep_headers": {
            "Authorization": f"Bearer {rep_uid}",
            "X-Workspace-Id": str(ws_id),
        },
        "foreign_workspace_id": foreign_ws_id,
        "foreign_headers": {
            "Authorization": f"Bearer {foreign_admin_uid}",
            "X-Workspace-Id": str(foreign_ws_id),
        },
    }
