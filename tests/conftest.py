import os
import shutil
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from storeops_contracts.models import Currency, Workspace
from datetime import datetime, timezone

from apps.api.adapters.blob.local_fs import LocalFileSystemBlobRepository
from apps.api.adapters.state.in_memory import InMemoryStateRepository
from apps.api.core.auth import set_state_repository
from apps.api.main import app


@pytest.fixture
def temp_media_dir():
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def blob_repo(temp_media_dir):
    return LocalFileSystemBlobRepository(base_dir=temp_media_dir)


@pytest.fixture
def state_repo():
    repo = InMemoryStateRepository()
    set_state_repository(repo)
    return repo


@pytest_asyncio.fixture
async def api_client(state_repo):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def bootstrapped_workspace(state_repo):
    now = datetime.now(timezone.utc)
    ws_id = uuid4()
    admin_uid = "admin-test-uid"
    workspace = Workspace(
        id=ws_id,
        workspace_id=ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        name="Test Ops Workspace",
        brand_name="Test Brand",
        currency=Currency.SGD,
    )
    membership = await state_repo.create_workspace_with_admin(
        workspace=workspace,
        uid=admin_uid,
        email="admin@test.com",
    )
    return {
        "workspace": workspace,
        "admin_uid": admin_uid,
        "membership": membership,
    }
