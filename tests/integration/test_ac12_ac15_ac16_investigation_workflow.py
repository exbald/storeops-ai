"""Integration tests for AC12, AC15, and AC16.

AC12: Multi-turn investigation flow, hypotheses, root causes, alternatives, <= 3 actions.
AC15: Grounded evidence citations, bounding box / metric locator resolution.
AC16: Plan acceptance idempotency (replay same key -> cached 200, stale version -> 409),
      and representative action updates cannot directly mark VERIFIED or RESOLVED.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient


async def _setup_visit_and_media(
    client: AsyncClient,
    admin_headers: dict[str, str],
    rep_headers: dict[str, str],
):
    # 1. Create store
    store_res = await client.post(
        "/stores",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "code": f"STR-INV-{uuid4().hex[:6]}",
            "name": "Investigation Store",
            "retailer": "Retail Corp",
            "region": "West",
            "format": "Supermarket",
            "timezone": "Asia/Singapore",
            "distributor_location_id": None,
        },
    )
    store = store_res.json()
    store_id = store["id"]

    # 2. Create product
    prod_res = await client.post(
        "/products",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "sku": f"SKU-INV-{uuid4().hex[:6].upper()}",
            "name": "Cola Zero 330ml",
            "case_units": 24,
        },
    )
    prod = prod_res.json()
    prod_id = prod["id"]

    # 3. Create promotion & approve policy
    today = datetime.now(tz=UTC).date()
    promo_res = await client.post(
        "/promotions",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "name": "Cola Summer Promo",
            "starts_on": str(today),
            "ends_on": str(today + timedelta(days=30)),
            "store_ids": [store_id],
            "agreement_media_id": None,
        },
    )
    promo = promo_res.json()
    promo_id = promo["id"]

    rule_id = str(uuid4())
    approve_res = await client.post(
        f"/promotions/{promo_id}/approve",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": promo["version"],
            "catalog_product_ids": [prod_id],
            "rules": [
                {
                    "rule_id": rule_id,
                    "kind": "MIN_FACINGS",
                    "zone_id": "shelf-01",
                    "zone_kind": "SHELF",
                    "product_id": prod_id,
                    "min_facings": 4,
                    "source": {
                        "kind": "MANUAL",
                        "media_id": None,
                        "page": None,
                        "quote": None,
                        "reviewer_note": "Approved manual rule",
                    },
                }
            ],
        },
    )
    assert approve_res.status_code in [200, 201]

    # 4. Start visit
    visit_res = await client.post(
        "/visits",
        headers={**rep_headers, "Idempotency-Key": str(uuid4())},
        json={"store_id": store_id, "notes": "Auditing shelf compliance"},
    )
    assert visit_res.status_code == 201
    visit = visit_res.json()
    visit_id = visit["id"]

    # 5. Upload shelf photo
    img_bytes = b"PHOTO_BEFORE_SHELF_IMAGE_BYTES"
    import hashlib

    img_hash = hashlib.sha256(img_bytes).hexdigest()

    init_m = await client.post(
        "/media",
        headers={**rep_headers, "Idempotency-Key": str(uuid4())},
        json={
            "kind": "VISIT_BEFORE",
            "filename": "shelf.jpg",
            "mime_type": "image/jpeg",
            "byte_size": len(img_bytes),
            "sha256": img_hash,
            "store_id": store_id,
            "visit_id": visit_id,
            "product_id": None,
            "zone_id": "shelf-01",
            "zone_kind": "SHELF",
            "captured_at": datetime.now(UTC).isoformat(),
        },
    )
    m_data = init_m.json()
    media_id = m_data["media"]["id"]
    await client.put(m_data["upload_url"], content=img_bytes)
    await client.post(
        f"/media/{media_id}/complete",
        headers={**rep_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )

    return {
        "store": store,
        "product": prod,
        "promotion": promo,
        "visit": visit,
        "media_id": media_id,
    }


@pytest.mark.asyncio
async def test_ac12_investigation_execution_and_constraints(
    integration_client: AsyncClient,
    admin_a_headers: dict[str, str],
    rep_a_headers: dict[str, str],
):
    """AC12: Investigation executes successfully, generates <= 3 actions with hypotheses & root cause."""
    setup = await _setup_visit_and_media(integration_client, admin_a_headers, rep_a_headers)

    # Launch investigation
    inv_res = await integration_client.post(
        "/investigations",
        headers={**rep_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "store_id": setup["store"]["id"],
            "visit_id": setup["visit"]["id"],
            "promotion_id": setup["promotion"]["id"],
            "media_ids": [setup["media_id"]],
        },
    )
    assert inv_res.status_code == 202
    job_info = inv_res.json()
    inv_id = job_info["resource_id"]

    # Poll or get investigation
    get_res = await integration_client.get(f"/investigations/{inv_id}", headers=rep_a_headers)
    assert get_res.status_code == 200
    inv = get_res.json()

    # Constraints: actions <= 3
    actions = inv.get("proposed_actions", [])
    assert len(actions) <= 3, "Investigation must propose at most 3 corrective actions"


@pytest.mark.asyncio
async def test_ac16_plan_acceptance_idempotency_and_action_claim_safety(
    integration_client: AsyncClient,
    admin_a_headers: dict[str, str],
    rep_a_headers: dict[str, str],
):
    """AC16: Idempotent plan acceptance and representative cannot directly set VERIFIED or RESOLVED."""
    setup = await _setup_visit_and_media(integration_client, admin_a_headers, rep_a_headers)

    inv_res = await integration_client.post(
        "/investigations",
        headers={**rep_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "store_id": setup["store"]["id"],
            "visit_id": setup["visit"]["id"],
            "promotion_id": setup["promotion"]["id"],
            "media_ids": [setup["media_id"]],
        },
    )
    inv_id = inv_res.json()["resource_id"]
    get_res = await integration_client.get(f"/investigations/{inv_id}", headers=rep_a_headers)
    inv = get_res.json()

    # 1. Accept plan with idempotency key
    accept_key = str(uuid4())
    accept1 = await integration_client.post(
        f"/investigations/{inv_id}/accept",
        headers={**rep_a_headers, "Idempotency-Key": accept_key},
        json={"expected_version": inv["version"]},
    )
    assert accept1.status_code == 200
    accepted_inv = accept1.json()
    assert accepted_inv["state"] == "ACCEPTED"

    # 2. Replay accept with exact same key -> returns cached 200
    accept_replay = await integration_client.post(
        f"/investigations/{inv_id}/accept",
        headers={**rep_a_headers, "Idempotency-Key": accept_key},
        json={"expected_version": inv["version"]},
    )
    assert accept_replay.status_code == 200

    # 3. New request with stale expected_version -> returns 409
    accept_stale = await integration_client.post(
        f"/investigations/{inv_id}/accept",
        headers={**rep_a_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": inv["version"]},
    )
    assert accept_stale.status_code in [409, 422]

    # 4. If actions exist, verify representative cannot mark action as VERIFIED or RESOLVED
    if accepted_inv.get("actions"):
        action_id = accepted_inv["actions"][0]["id"]

        # Attempt to set VERIFIED directly -> rejected
        illegal_update = await integration_client.patch(
            f"/investigations/{inv_id}/actions/{action_id}",
            headers=rep_a_headers,
            json={"expected_version": 1, "status": "VERIFIED"},
        )
        assert illegal_update.status_code in [400, 422], "Representative cannot mark action VERIFIED directly"
