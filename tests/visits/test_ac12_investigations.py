from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from storeops_contracts.models import (
    Kind,
    Media,
    Status1,
    ZoneKind,
)


@pytest.fixture
def sample_ready_media(catalog_repo, sample_store, workspace_setup):
    ws_id = workspace_setup["workspace_id"]
    now = datetime.now(UTC)

    async def _create(visit_id: UUID, filename: str = "shelf.jpg"):
        media = Media(
            id=uuid4(),
            workspace_id=ws_id,
            version=1,
            created_at=now,
            updated_at=now,
            kind=Kind.VISIT_BEFORE,
            filename=filename,
            mime_type="image/jpeg",
            status=Status1.READY,
            store_id=sample_store.id,
            visit_id=visit_id,
            product_id=None,
            zone_id="shelf-1",
            zone_kind=ZoneKind.SHELF,
            captured_at=now,
            original_sha256="c" * 64,
            normalized_sha256="c" * 64,
            byte_size=2048,
            width=1920,
            height=1080,
            rejection=None,
            download_url=None,
            download_url_expires_at=None,
        )
        return await catalog_repo.create_media(media)

    return _create


@pytest.mark.asyncio
async def test_ac12_start_investigation_and_proposal_structure(
    client,
    workspace_setup,
    sample_store,
    sample_promotion_with_policy,
    sample_ready_media,
    state_repo,
):
    headers = workspace_setup["rep_headers"]
    promo, policy_ver, _rule = sample_promotion_with_policy

    # 1. Create visit
    res_v = await client.post(
        "/visits",
        json={
            "store_id": str(sample_store.id),
            "notes": "Checking promotion compliance",
        },
        headers={**headers, "Idempotency-Key": f"key-{uuid4()}"},
    )
    assert res_v.status_code == 201
    visit = res_v.json()
    visit_id = UUID(visit["id"])

    # 2. Attach ready media to visit
    media = await sample_ready_media(visit_id)

    # 3. Start investigation
    inv_payload = {
        "store_id": str(sample_store.id),
        "visit_id": str(visit_id),
        "promotion_id": str(promo.id),
        "media_ids": [str(media.id)],
    }
    idempotency_key = f"inv-{uuid4()}"
    res_inv = await client.post(
        "/investigations",
        json=inv_payload,
        headers={**headers, "Idempotency-Key": idempotency_key},
    )
    assert res_inv.status_code == 202, res_inv.text
    job_data = res_inv.json()
    assert job_data["type"] == "INVESTIGATE"
    assert job_data["status"] == "SUCCEEDED"
    inv_id = job_data["resource_id"]

    # Fetch investigation
    res_get = await client.get(f"/investigations/{inv_id}", headers=headers)
    assert res_get.status_code == 200, res_get.text
    inv = res_get.json()
    assert inv["state"] == "PROPOSED"
    assert inv["store_id"] == str(sample_store.id)
    assert inv["visit_id"] == str(visit_id)
    assert inv["promotion_id"] == str(promo.id)
    assert inv["policy_version_id"] == str(policy_ver.id)
    assert inv["snapshot_id"] is not None

    # Diagnosis validation
    diagnosis = inv["diagnosis"]
    assert diagnosis is not None
    assert diagnosis["hypothesis"] == "EXECUTION"
    assert len(diagnosis["claims"]) >= 1
    assert len(inv["actions"]) <= 3
    for act in inv["actions"]:
        assert len(act["claim_ids"]) >= 1
        assert len(act["evidence_ids"]) >= 1
        assert act["status"] == "OPEN"

    # Job tracking in state_repo
    job = await state_repo.get_job(
        workspace_setup["workspace_id"], UUID(job_data["id"])
    )
    assert job is not None
    assert job.status.value == "SUCCEEDED"

    # Idempotency replay on POST /investigations
    res_replay = await client.post(
        "/investigations",
        json=inv_payload,
        headers={**headers, "Idempotency-Key": idempotency_key},
    )
    assert res_replay.status_code == 202
    assert res_replay.json()["id"] == job_data["id"]


@pytest.mark.asyncio
async def test_ac12_single_active_investigation_invariant(
    client,
    workspace_setup,
    sample_store,
    sample_promotion_with_policy,
    sample_ready_media,
):
    headers = workspace_setup["rep_headers"]
    promo, _policy_ver, _rule = sample_promotion_with_policy

    # Create visit
    res_v = await client.post(
        "/visits",
        json={"store_id": str(sample_store.id), "notes": "Compliance run"},
        headers={**headers, "Idempotency-Key": f"key-{uuid4()}"},
    )
    visit_id = UUID(res_v.json()["id"])
    media = await sample_ready_media(visit_id)

    # First investigation
    res_inv1 = await client.post(
        "/investigations",
        json={
            "store_id": str(sample_store.id),
            "visit_id": str(visit_id),
            "promotion_id": str(promo.id),
            "media_ids": [str(media.id)],
        },
        headers={**headers, "Idempotency-Key": f"inv1-{uuid4()}"},
    )
    assert res_inv1.status_code == 202

    # Second investigation on same visit while first is active -> 409 Conflict
    res_inv2 = await client.post(
        "/investigations",
        json={
            "store_id": str(sample_store.id),
            "visit_id": str(visit_id),
            "promotion_id": str(promo.id),
            "media_ids": [str(media.id)],
        },
        headers={**headers, "Idempotency-Key": f"inv2-{uuid4()}"},
    )
    assert res_inv2.status_code == 409
    assert res_inv2.json()["code"] == "ACTIVE_INVESTIGATION_EXISTS"


@pytest.mark.asyncio
async def test_ac12_list_investigations_pagination_and_invalid_cursor(
    client,
    workspace_setup,
    sample_store,
    sample_promotion_with_policy,
    sample_ready_media,
):
    headers = workspace_setup["rep_headers"]
    promo, _policy_ver, _rule = sample_promotion_with_policy

    # Create visit 1 and investigation 1
    res_v1 = await client.post(
        "/visits",
        json={"store_id": str(sample_store.id), "notes": "Visit 1"},
        headers={**headers, "Idempotency-Key": f"key-{uuid4()}"},
    )
    v1_id = UUID(res_v1.json()["id"])
    m1 = await sample_ready_media(v1_id, filename="m1.jpg")
    res_inv1 = await client.post(
        "/investigations",
        json={
            "store_id": str(sample_store.id),
            "visit_id": str(v1_id),
            "promotion_id": str(promo.id),
            "media_ids": [str(m1.id)],
        },
        headers={**headers, "Idempotency-Key": f"inv1-{uuid4()}"},
    )
    assert res_inv1.status_code == 202

    # Create visit 2 and investigation 2
    res_v2 = await client.post(
        "/visits",
        json={"store_id": str(sample_store.id), "notes": "Visit 2"},
        headers={**headers, "Idempotency-Key": f"key-{uuid4()}"},
    )
    v2_id = UUID(res_v2.json()["id"])
    m2 = await sample_ready_media(v2_id, filename="m2.jpg")
    res_inv2 = await client.post(
        "/investigations",
        json={
            "store_id": str(sample_store.id),
            "visit_id": str(v2_id),
            "promotion_id": str(promo.id),
            "media_ids": [str(m2.id)],
        },
        headers={**headers, "Idempotency-Key": f"inv2-{uuid4()}"},
    )
    assert res_inv2.status_code == 202

    # List page 1 with limit=1
    res_p1 = await client.get("/investigations?limit=1", headers=headers)
    assert res_p1.status_code == 200
    p1 = res_p1.json()
    assert len(p1["items"]) == 1
    assert p1["next_cursor"] is not None

    # List page 2 with next_cursor
    res_p2 = await client.get(
        f"/investigations?cursor={p1['next_cursor']}&limit=1", headers=headers
    )
    assert res_p2.status_code == 200
    p2 = res_p2.json()
    assert len(p2["items"]) == 1
    assert p2["items"][0]["id"] != p1["items"][0]["id"]

    # Malformed cursor returns 422 INVALID_CURSOR
    res_bad = await client.get(
        "/investigations?cursor=not_a_valid_base64_int!", headers=headers
    )
    assert res_bad.status_code == 422
    assert res_bad.json()["code"] == "INVALID_CURSOR"
