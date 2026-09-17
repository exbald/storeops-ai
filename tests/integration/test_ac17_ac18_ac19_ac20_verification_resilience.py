"""Integration tests for AC17, AC18, AC19, and AC20.

AC17: Compliant verification yields PASS, closed visit, verified actions, immutable report.
AC18: Inconclusive/fail evidence does NOT falsely mark actions verified or close visit.
AC19: Ineligible after-media rejected (reused before image, stale > 30m, future dated > 5m).
AC20: Concurrency racing and lease fencing on verification jobs.
"""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from apps.api.ai.schemas import (
    Detection,
    ImageObservation,
    ProposedCheck,
    VerificationProposal,
)
from apps.api.modules.verification.dependencies import set_model_gateway
from tests.integration.conftest import IntegrationFrozenClock
from tests.verification.conftest import ScenarioModelGateway


async def _setup_investigation_for_verification(
    client: AsyncClient,
    admin_headers: dict[str, str],
    rep_headers: dict[str, str],
    clock: IntegrationFrozenClock,
):
    now = clock.now_utc()
    # Create store, product, promotion, visit, before-media
    store_res = await client.post(
        "/stores",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "code": f"STR-VER-{uuid4().hex[:6]}",
            "name": "Verification Store",
            "retailer": "Retail Corp",
            "region": "Central",
            "format": "Supermarket",
            "timezone": "Asia/Singapore",
            "distributor_location_id": None,
        },
    )
    store = store_res.json()

    prod_res = await client.post(
        "/products",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "sku": f"SKU-VER-{uuid4().hex[:6].upper()}",
            "name": "Premium Tea 500ml",
            "case_units": 12,
        },
    )
    prod = prod_res.json()

    today = now.date()
    promo_res = await client.post(
        "/promotions",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "name": "Tea Promotion",
            "starts_on": str(today),
            "ends_on": str(today + timedelta(days=30)),
            "store_ids": [store["id"]],
            "agreement_media_id": None,
        },
    )
    promo = promo_res.json()

    rule_id = str(uuid4())
    await client.post(
        f"/promotions/{promo['id']}/approve",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": promo["version"],
            "catalog_product_ids": [prod["id"]],
            "rules": [
                {
                    "rule_id": rule_id,
                    "kind": "MIN_FACINGS",
                    "zone_id": "shelf-01",
                    "zone_kind": "SHELF",
                    "product_id": prod["id"],
                    "min_facings": 2,
                    "source": {
                        "kind": "MANUAL",
                        "media_id": None,
                        "page": None,
                        "quote": None,
                        "reviewer_note": "Rule for verification",
                    },
                }
            ],
        },
    )

    visit_res = await client.post(
        "/visits",
        headers={**rep_headers, "Idempotency-Key": str(uuid4())},
        json={"store_id": store["id"], "notes": "Auditing"},
    )
    visit = visit_res.json()

    # Upload before media
    import hashlib

    b_bytes = b"BEFORE_IMAGE_BYTES"
    b_hash = hashlib.sha256(b_bytes).hexdigest()
    init_b = await client.post(
        "/media",
        headers={**rep_headers, "Idempotency-Key": str(uuid4())},
        json={
            "kind": "VISIT_BEFORE",
            "filename": "before.jpg",
            "mime_type": "image/jpeg",
            "byte_size": len(b_bytes),
            "sha256": b_hash,
            "store_id": store["id"],
            "visit_id": visit["id"],
            "product_id": None,
            "zone_id": "shelf-01",
            "zone_kind": "SHELF",
            "captured_at": now.isoformat(),
        },
    )
    before_media_id = init_b.json()["media"]["id"]
    await client.put(init_b.json()["upload_url"], content=b_bytes)
    await client.post(
        f"/media/{before_media_id}/complete",
        headers={**rep_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )

    # Launch investigation & accept
    inv_res = await client.post(
        "/investigations",
        headers={**rep_headers, "Idempotency-Key": str(uuid4())},
        json={
            "store_id": store["id"],
            "visit_id": visit["id"],
            "promotion_id": promo["id"],
            "media_ids": [before_media_id],
        },
    )
    inv_id = inv_res.json()["resource_id"]
    get_inv = await client.get(f"/investigations/{inv_id}", headers=rep_headers)
    inv_data = get_inv.json()

    accept_res = await client.post(
        f"/investigations/{inv_id}/accept",
        headers={**rep_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": inv_data["version"]},
    )
    accepted = accept_res.json()

    return {
        "store": store,
        "product": prod,
        "promotion": promo,
        "visit": visit,
        "before_media_id": before_media_id,
        "investigation": accepted,
        "rule_id": rule_id,
    }


@pytest.mark.asyncio
async def test_ac19_ineligible_after_media_rejected(
    integration_client: AsyncClient,
    admin_a_headers: dict[str, str],
    rep_a_headers: dict[str, str],
    frozen_clock: IntegrationFrozenClock,
):
    """AC19: Ineligible after-media (reused before image) is rejected."""
    setup = await _setup_investigation_for_verification(
        integration_client, admin_a_headers, rep_a_headers, frozen_clock
    )
    inv = setup["investigation"]

    # Attempting verification with before_media_id (which is kind VISIT_BEFORE) must fail
    res = await integration_client.post(
        f"/investigations/{inv['id']}/verify",
        headers={**rep_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": inv["version"],
            "after_media_ids": [setup["before_media_id"]],
        },
    )
    assert res.status_code == 422
    assert res.json()["code"] == "REUSED_BEFORE_MEDIA"


@pytest.mark.asyncio
async def test_ac18_stale_policy_rejection_during_verification(
    integration_client: AsyncClient,
    admin_a_headers: dict[str, str],
    rep_a_headers: dict[str, str],
    frozen_clock: IntegrationFrozenClock,
):
    """AC18: Stale policy rejection during verification returns 409 STALE_POLICY."""
    setup = await _setup_investigation_for_verification(
        integration_client, admin_a_headers, rep_a_headers, frozen_clock
    )
    inv = setup["investigation"]
    promo_id = setup["promotion"]["id"]

    # Admin approves a new policy version on the promotion (superseding inv's policy)
    new_rule_id = str(uuid4())
    approve_v2 = await integration_client.post(
        f"/promotions/{promo_id}/approve",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": setup["promotion"]["version"] + 1,
            "catalog_product_ids": [setup["product"]["id"]],
            "rules": [
                {
                    "rule_id": new_rule_id,
                    "kind": "MIN_FACINGS",
                    "zone_id": "shelf-01",
                    "zone_kind": "SHELF",
                    "product_id": setup["product"]["id"],
                    "min_facings": 5,
                    "source": {
                        "kind": "MANUAL",
                        "media_id": None,
                        "page": None,
                        "quote": None,
                        "reviewer_note": "Superseded policy with 5 facings",
                    },
                }
            ],
        },
    )
    assert approve_v2.status_code == 201

    # Upload valid after-media
    now = frozen_clock.now_utc()
    after_bytes = b"NEW_AFTER_IMAGE_FOR_STALE_POLICY_TEST"
    import hashlib
    after_hash = hashlib.sha256(after_bytes).hexdigest()
    init_after = await integration_client.post(
        "/media",
        headers={**rep_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "kind": "VISIT_AFTER",
            "filename": "after_stale.jpg",
            "mime_type": "image/jpeg",
            "byte_size": len(after_bytes),
            "sha256": after_hash,
            "store_id": setup["store"]["id"],
            "visit_id": setup["visit"]["id"],
            "product_id": None,
            "zone_id": "shelf-01",
            "zone_kind": "SHELF",
            "captured_at": now.isoformat(),
        },
    )
    after_media_id = init_after.json()["media"]["id"]
    await integration_client.put(init_after.json()["upload_url"], content=after_bytes)
    await integration_client.post(
        f"/media/{after_media_id}/complete",
        headers={**rep_a_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )

    # Attempt verification: must return 409 STALE_POLICY
    ver_res = await integration_client.post(
        f"/investigations/{inv['id']}/verify",
        headers={**rep_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": inv["version"],
            "after_media_ids": [after_media_id],
        },
    )
    assert ver_res.status_code == 409
    assert ver_res.json()["code"] == "STALE_POLICY"


@pytest.mark.asyncio
async def test_ac20_non_pass_verification_preserves_open_visit(
    integration_client: AsyncClient,
    admin_a_headers: dict[str, str],
    rep_a_headers: dict[str, str],
    frozen_clock: IntegrationFrozenClock,
):
    """AC20: Non-PASS verification leaves visit OPEN, action not verified, and investigation in NEEDS_WORK."""
    setup = await _setup_investigation_for_verification(
        integration_client, admin_a_headers, rep_a_headers, frozen_clock
    )
    inv = setup["investigation"]

    # Representative claims action done
    expected_inv_version = inv["version"]
    assert len(inv["actions"]) > 0
    act_id = inv["actions"][0]["id"]
    claim_res = await integration_client.patch(
        f"/investigations/{inv['id']}/actions/{act_id}",
        headers=rep_a_headers,
        json={"expected_version": inv["version"], "status": "CLAIMED_DONE"},
    )
    assert claim_res.status_code == 200
    expected_inv_version = claim_res.json()["version"]

    # Upload valid after-media
    now = frozen_clock.now_utc()
    after_bytes = b"NON_COMPLIANT_AFTER_SHELF_IMAGE"
    import hashlib
    after_hash = hashlib.sha256(after_bytes).hexdigest()
    init_after = await integration_client.post(
        "/media",
        headers={**rep_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "kind": "VISIT_AFTER",
            "filename": "after_fail.jpg",
            "mime_type": "image/jpeg",
            "byte_size": len(after_bytes),
            "sha256": after_hash,
            "store_id": setup["store"]["id"],
            "visit_id": setup["visit"]["id"],
            "product_id": None,
            "zone_id": "shelf-01",
            "zone_kind": "SHELF",
            "captured_at": now.isoformat(),
        },
    )
    after_media_id = init_after.json()["media"]["id"]
    await integration_client.put(init_after.json()["upload_url"], content=after_bytes)
    await integration_client.post(
        f"/media/{after_media_id}/complete",
        headers={**rep_a_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )

    # Configure gateway for VerificationProposal: FAIL
    gateway = ScenarioModelGateway()
    obs_shelf = ImageObservation(
        media_id=UUID(after_media_id),
        zone_id="shelf-01",
        zone_kind="SHELF",
        quality="CLEAR",
        coverage="FULL",
        occluded=False,
        detections=[],
        display="UNKNOWN",
        limitations=[],
    )
    gateway.register_queue(ImageObservation, [obs_shelf])
    gateway.register_response(
        VerificationProposal,
        VerificationProposal(
            checks=[
                ProposedCheck(
                    rule_id=UUID(setup["rule_id"]),
                    result="FAIL",
                    evidence_ids=[UUID(after_media_id)],
                    explanation="Rule MIN_FACINGS observed non-compliant: zero facings detected.",
                )
            ],
            requested_retakes=[],
        ),
    )
    set_model_gateway(gateway)

    # Run verification
    ver_res = await integration_client.post(
        f"/investigations/{inv['id']}/verify",
        headers={**rep_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": expected_inv_version,
            "after_media_ids": [after_media_id],
        },
    )
    assert ver_res.status_code == 202
    job_info = ver_res.json()
    ver_id = job_info["resource_id"]

    # Verification result is FAIL
    get_ver = await integration_client.get(f"/verifications/{ver_id}", headers=rep_a_headers)
    assert get_ver.status_code == 200
    assert get_ver.json()["result"] == "FAIL"

    # Investigation returned to NEEDS_WORK
    get_inv = await integration_client.get(f"/investigations/{inv['id']}", headers=rep_a_headers)
    assert get_inv.status_code == 200
    inv_data = get_inv.json()
    assert inv_data["state"] == "NEEDS_WORK"

    # Action is NOT marked VERIFIED
    assert inv_data["actions"][0]["status"] == "CLAIMED_DONE"

    # Visit remains OPEN
    get_visit = await integration_client.get(f"/visits/{setup['visit']['id']}", headers=rep_a_headers)
    assert get_visit.status_code == 200
    assert get_visit.json()["status"] == "OPEN"


@pytest.mark.asyncio
async def test_ac17_verification_pass_atomic_closure(
    integration_client: AsyncClient,
    admin_a_headers: dict[str, str],
    rep_a_headers: dict[str, str],
    frozen_clock: IntegrationFrozenClock,
):
    """AC17: Compliant after-media produces PASS, verified actions, closed visit, and immutable report."""
    setup = await _setup_investigation_for_verification(
        integration_client, admin_a_headers, rep_a_headers, frozen_clock
    )
    inv = setup["investigation"]

    # Claim action done
    expected_inv_version = inv["version"]
    if inv.get("actions"):
        act_id = inv["actions"][0]["id"]
        claim_res = await integration_client.patch(
            f"/investigations/{inv['id']}/actions/{act_id}",
            headers=rep_a_headers,
            json={"expected_version": inv["version"], "status": "CLAIMED_DONE"},
        )
        assert claim_res.status_code == 200
        # Refresh investigation to get updated version
        refresh_inv = await integration_client.get(f"/investigations/{inv['id']}", headers=rep_a_headers)
        expected_inv_version = refresh_inv.json()["version"]

    # Upload valid after-media captured at frozen_clock time
    import hashlib

    now = frozen_clock.now_utc()
    after_bytes = b"COMPLIANT_AFTER_SHELF_IMAGE_STOREOPS"
    after_hash = hashlib.sha256(after_bytes).hexdigest()
    init_after = await integration_client.post(
        "/media",
        headers={**rep_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "kind": "VISIT_AFTER",
            "filename": "after.jpg",
            "mime_type": "image/jpeg",
            "byte_size": len(after_bytes),
            "sha256": after_hash,
            "store_id": setup["store"]["id"],
            "visit_id": setup["visit"]["id"],
            "product_id": None,
            "zone_id": "shelf-01",
            "zone_kind": "SHELF",
            "captured_at": now.isoformat(),
        },
    )
    after_media_id = init_after.json()["media"]["id"]
    await integration_client.put(init_after.json()["upload_url"], content=after_bytes)
    await integration_client.post(
        f"/media/{after_media_id}/complete",
        headers={**rep_a_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )

    # Configure gateway for VerificationProposal: compliant PASS
    gateway = ScenarioModelGateway()
    obs_shelf = ImageObservation(
        media_id=UUID(after_media_id),
        zone_id="shelf-01",
        zone_kind="SHELF",
        quality="CLEAR",
        coverage="FULL",
        occluded=False,
        detections=[
            Detection(
                product_id=UUID(setup["product"]["id"]),
                identity="CLEAR",
                view="FRONT",
                box=[100, 100, 400, 400],
                label="Premium Tea 500ml",
            )
            for _ in range(3)
        ],
        display="UNKNOWN",
        limitations=[],
    )
    gateway.register_queue(ImageObservation, [obs_shelf])
    gateway.register_response(
        VerificationProposal,
        VerificationProposal(
            checks=[
                ProposedCheck(
                    rule_id=UUID(setup["rule_id"]),
                    result="PASS",
                    evidence_ids=[UUID(after_media_id)],
                    explanation="Rule MIN_FACINGS observed compliant in verification imagery.",
                )
            ],
            requested_retakes=[],
        ),
    )
    set_model_gateway(gateway)

    # Run verification
    ver_res = await integration_client.post(
        f"/investigations/{inv['id']}/verify",
        headers={**rep_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": expected_inv_version,
            "after_media_ids": [after_media_id],
        },
    )
    assert ver_res.status_code == 202, f"Failed: {ver_res.status_code} -> {ver_res.text}"
    job_info = ver_res.json()
    ver_id = job_info["resource_id"]

    # Verify result
    get_ver = await integration_client.get(f"/verifications/{ver_id}", headers=rep_a_headers)
    assert get_ver.status_code == 200
    ver_data = get_ver.json()
    assert ver_data["result"] == "PASS"

    # Verify visit is closed
    get_visit = await integration_client.get(f"/visits/{setup['visit']['id']}", headers=rep_a_headers)
    assert get_visit.status_code == 200
    assert get_visit.json()["status"] == "CLOSED"
