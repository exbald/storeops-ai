from uuid import uuid4
import pytest
from storeops_contracts.models import Me, Workspace

from apps.api.adapters.state.in_memory import InMemoryStateRepository
from apps.api.core.auth import set_state_repository
from scripts.bootstrap import bootstrap_workspace


@pytest.mark.asyncio
async def test_ac01_bootstrap_empty_workspace_and_identity_preservation(api_client):
    """AC01: Given an empty installation and known Firebase uid,

    bootstrap a workspace and verify only workspace/membership records exist,
    zero business records, and identity is preserved.
    """
    repo = InMemoryStateRepository()
    set_state_repository(repo)

    admin_uid = "firebase-user-ac01"

    # Step 1: Verify initially empty
    memberships_before = await repo.get_memberships_for_user(admin_uid)
    assert len(memberships_before) == 0

    # Step 2: Bootstrap workspace
    workspace, role = await bootstrap_workspace(
        repo=repo,
        workspace_name="Retail Alpha",
        brand_name="Brand Alpha",
        currency_str="SGD",
        admin_uid=admin_uid,
        admin_email="alpha@test.com",
    )
    assert role == "ADMIN"
    assert workspace.currency.value == "SGD"

    # Step 3: Verify only workspace and membership records exist (zero business fixtures)
    assert len(repo.workspaces) == 1
    assert len(repo.memberships) == 1
    assert len(repo.jobs) == 0

    # Step 4: Sign in and verify GET /me
    resp_me = await api_client.get(
        "/me",
        headers={"Authorization": f"Bearer {admin_uid}"},
    )
    assert resp_me.status_code == 200
    me_data = Me.model_validate(resp_me.json())
    assert me_data.uid == admin_uid
    assert len(me_data.memberships) == 1
    assert me_data.memberships[0].workspace_id == workspace.id
    assert me_data.memberships[0].role == "ADMIN"

    # Step 5: Read current workspace via GET /workspace
    resp_ws = await api_client.get(
        "/workspace",
        headers={
            "Authorization": f"Bearer {admin_uid}",
            "X-Workspace-Id": str(workspace.id),
        },
    )
    assert resp_ws.status_code == 200
    ws_data = Workspace.model_validate(resp_ws.json())
    assert ws_data.id == workspace.id
    assert ws_data.name == "Retail Alpha"
    assert ws_data.brand_name == "Brand Alpha"

    # Step 6: Verify restart / reload preserves identity and does not add fixtures
    reloaded_ws = await repo.get_workspace(workspace.id)
    assert reloaded_ws is not None
    assert reloaded_ws.id == workspace.id
    assert len(repo.workspaces) == 1
    assert len(repo.memberships) == 1
