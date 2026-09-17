from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from storeops_contracts.models import (
    Currency,
    Kind,
    Location,
    Media,
    Status1,
    Status5,
    Store,
    Type1,
    ZoneKind,
)


@pytest.mark.asyncio
async def test_ac11_create_visit_and_restore(client, workspace_setup, sample_store):
    headers = {
        **workspace_setup["rep_headers"],
        "Idempotency-Key": f"visit-create-{uuid4()}",
    }
    payload = {
        "store_id": str(sample_store.id),
        "notes": "Initial visit setup for August campaign.",
    }

    # 1. Create visit
    res = await client.post("/visits", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    created = res.json()
    visit_id = created["id"]
    assert created["store_id"] == str(sample_store.id)
    assert created["status"] == "OPEN"
    assert created["version"] == 1
    assert created["notes"] == "Initial visit setup for August campaign."
    assert created["before_media_ids"] == []
    assert created["after_media_ids"] == []
    assert created["active_investigation_id"] is None
    assert created["report_ids"] == []

    # 2. Idempotent replay with same key
    res_replay = await client.post("/visits", json=payload, headers=headers)
    assert res_replay.status_code == 201
    assert res_replay.json()["id"] == visit_id

    # 3. Refresh / restore visit
    res_get = await client.get(
        f"/visits/{visit_id}", headers=workspace_setup["rep_headers"]
    )
    assert res_get.status_code == 200
    restored = res_get.json()
    assert restored["id"] == visit_id
    assert restored["notes"] == "Initial visit setup for August campaign."
    assert restored["version"] == 1


@pytest.mark.asyncio
async def test_ac11_update_visit_notes_and_occ(client, workspace_setup, sample_store):
    headers = {
        **workspace_setup["rep_headers"],
        "Idempotency-Key": f"visit-create-{uuid4()}",
    }
    payload = {
        "store_id": str(sample_store.id),
        "notes": "Original notes",
    }
    res = await client.post("/visits", json=payload, headers=headers)
    assert res.status_code == 201
    visit = res.json()
    visit_id = visit["id"]

    # 1. Update notes with expected_version = 1
    update_payload = {
        "expected_version": 1,
        "notes": "Updated observations: Shelf 3 has empty facings.",
    }
    res_patch = await client.patch(
        f"/visits/{visit_id}",
        json=update_payload,
        headers=workspace_setup["rep_headers"],
    )
    assert res_patch.status_code == 200
    updated = res_patch.json()
    assert updated["version"] == 2
    assert updated["notes"] == "Updated observations: Shelf 3 has empty facings."

    # 2. OCC Conflict: submitting with stale expected_version = 1 returns 409
    res_stale = await client.patch(
        f"/visits/{visit_id}",
        json=update_payload,
        headers=workspace_setup["rep_headers"],
    )
    assert res_stale.status_code == 409
    assert res_stale.json()["code"] == "VERSION_CONFLICT"


@pytest.mark.asyncio
async def test_ac11_media_store_and_visit_scoping(
    client, catalog_repo, workspace_setup, sample_store, sample_promotion_with_policy
):
    ws_id = workspace_setup["workspace_id"]
    now = datetime.now(UTC)
    promo, _policy_ver, _rule = sample_promotion_with_policy

    # Create visit 1 on sample_store
    res = await client.post(
        "/visits",
        json={"store_id": str(sample_store.id), "notes": "Visit 1"},
        headers={
            **workspace_setup["rep_headers"],
            "Idempotency-Key": f"key-{uuid4()}",
        },
    )
    assert res.status_code == 201
    visit1_id = res.json()["id"]

    # Create visit 2 on sample_store
    res = await client.post(
        "/visits",
        json={"store_id": str(sample_store.id), "notes": "Visit 2"},
        headers={
            **workspace_setup["rep_headers"],
            "Idempotency-Key": f"key-{uuid4()}",
        },
    )
    assert res.status_code == 201
    visit2_id = res.json()["id"]

    other_store_id = uuid4()
    other_backroom_id = uuid4()
    other_backroom = Location(
        id=other_backroom_id,
        workspace_id=ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        name="Other Backroom",
        code="OBR-01",
        type=Type1.BACKROOM,
        store_id=other_store_id,
        active=True,
    )
    other_store = Store(
        id=other_store_id,
        workspace_id=ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        code="STR-002",
        name="Tampines Mall",
        retailer="FairPrice",
        region="SG-East",
        format="SUPERMARKET",
        timezone="Asia/Singapore",
        currency=Currency.SGD,
        backroom_location_id=other_backroom_id,
        distributor_location_id=None,
        active=True,
    )
    await catalog_repo.create_store_with_backroom(other_store, other_backroom)

    # Media belonging to other store
    foreign_store_media = Media(
        id=uuid4(),
        workspace_id=ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        kind=Kind.VISIT_BEFORE,
        filename="foreign.jpg",
        mime_type="image/jpeg",
        status=Status1.READY,
        store_id=other_store_id,
        visit_id=uuid4(),
        product_id=None,
        zone_id="shelf-1",
        zone_kind=ZoneKind.SHELF,
        captured_at=now,
        original_sha256="a" * 64,
        normalized_sha256="a" * 64,
        byte_size=1000,
        width=1920,
        height=1080,
        rejection=None,
        download_url=None,
        download_url_expires_at=None,
    )
    await catalog_repo.create_media(foreign_store_media)

    # Media belonging to visit 2, not visit 1
    v2_id = UUID(visit2_id)
    visit2_media = Media(
        id=uuid4(),
        workspace_id=ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        kind=Kind.VISIT_BEFORE,
        filename="visit2.jpg",
        mime_type="image/jpeg",
        status=Status1.READY,
        store_id=sample_store.id,
        visit_id=v2_id,
        product_id=None,
        zone_id="shelf-1",
        zone_kind=ZoneKind.SHELF,
        captured_at=now,
        original_sha256="b" * 64,
        normalized_sha256="b" * 64,
        byte_size=1000,
        width=1920,
        height=1080,
        rejection=None,
        download_url=None,
        download_url_expires_at=None,
    )
    await catalog_repo.create_media(visit2_media)

    # Attempt to start investigation on visit 1 with media from other store -> 422 MEDIA_STORE_MISMATCH
    res_err1 = await client.post(
        "/investigations",
        json={
            "store_id": str(sample_store.id),
            "visit_id": visit1_id,
            "promotion_id": str(promo.id),
            "media_ids": [str(foreign_store_media.id)],
        },
        headers={
            **workspace_setup["rep_headers"],
            "Idempotency-Key": f"key-{uuid4()}",
        },
    )
    assert res_err1.status_code == 422
    assert res_err1.json()["code"] == "MEDIA_STORE_MISMATCH"

    # Attempt to start investigation on visit 1 with media from visit 2 -> 422 MEDIA_VISIT_MISMATCH
    res_err2 = await client.post(
        "/investigations",
        json={
            "store_id": str(sample_store.id),
            "visit_id": visit1_id,
            "promotion_id": str(promo.id),
            "media_ids": [str(visit2_media.id)],
        },
        headers={
            **workspace_setup["rep_headers"],
            "Idempotency-Key": f"key-{uuid4()}",
        },
    )
    assert res_err2.status_code == 422
    assert res_err2.json()["code"] == "MEDIA_VISIT_MISMATCH"


@pytest.mark.asyncio
async def test_ac11_list_visits_with_filtering_and_pagination(
    client, workspace_setup, sample_store
):
    headers = workspace_setup["rep_headers"]

    # Create 3 visits
    for i in range(3):
        res = await client.post(
            "/visits",
            json={
                "store_id": str(sample_store.id),
                "notes": f"Visit note {i}",
            },
            headers={**headers, "Idempotency-Key": f"list-test-{i}-{uuid4()}"},
        )
        assert res.status_code == 201

    # List with limit 2
    res_list = await client.get(
        "/visits",
        params={"store_id": str(sample_store.id), "limit": 2},
        headers=headers,
    )
    assert res_list.status_code == 200
    data = res_list.json()
    assert len(data["items"]) == 2
    assert data["next_cursor"] is not None

    # Fetch next page
    res_page2 = await client.get(
        "/visits",
        params={
            "store_id": str(sample_store.id),
            "cursor": data["next_cursor"],
            "limit": 2,
        },
        headers=headers,
    )
    assert res_page2.status_code == 200
    data2 = res_page2.json()
    assert len(data2["items"]) == 1
    assert data2["next_cursor"] is None

    # Invalid cursor returns 422 INVALID_CURSOR
    res_bad = await client.get(
        "/visits",
        params={"cursor": "not-a-valid-base64-cursor"},
        headers=headers,
    )
    assert res_bad.status_code == 422
    assert res_bad.json()["code"] == "INVALID_CURSOR"


def test_prod_app_exposes_visits_and_investigations_routes():
    from apps.api.main import app

    paths = app.openapi()["paths"]
    assert "/visits" in paths
    assert "/investigations" in paths
    assert "/investigations/{investigation_id}" in paths
    assert "/investigations/{investigation_id}/evidence" in paths
    assert "/reports/{report_id}" in paths


@pytest.mark.asyncio
async def test_ac11_closed_visit_patch_returns_409(
    client,
    workspace_setup,
    sample_store,
    visit_repo,
):
    ws_id = workspace_setup["workspace_id"]
    headers = workspace_setup["rep_headers"]

    res = await client.post(
        "/visits",
        json={"store_id": str(sample_store.id), "notes": "Active visit"},
        headers={**headers, "Idempotency-Key": f"key-{uuid4()}"},
    )
    assert res.status_code == 201
    visit_id = UUID(res.json()["id"])

    # Directly close the visit in repo
    visit = await visit_repo.get_visit(ws_id, visit_id)
    visit.status = Status5.CLOSED
    await visit_repo.update_visit(ws_id, visit)

    # Attempt to patch notes on closed visit
    res_patch = await client.patch(
        f"/visits/{visit_id}",
        json={"expected_version": visit.version, "notes": "Attempt update on closed"},
        headers=headers,
    )
    assert res_patch.status_code == 409
    assert res_patch.json()["code"] == "VISIT_CLOSED"

