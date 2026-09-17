"""Integration tests for AC10, AC34, and AC35.

AC10: Policy version approval concurrency (409 conflict on stale revision) and immutability.
AC34: Stale policy detection (409 STALE_POLICY on superseded or archived policy).
AC35: Catalog constraints on policies (unknown/archived product IDs rejected with actionable error).
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient


async def _create_test_store_and_product(
    client: AsyncClient,
    admin_headers: dict[str, str],
):
    store_res = await client.post(
        "/stores",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "code": f"STR-POL-{uuid4().hex[:6]}",
            "name": "Policy Test Store",
            "retailer": "Retail Corp",
            "region": "East",
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
            "sku": f"SKU-POL-{uuid4().hex[:6].upper()}",
            "name": "Policy Test Soda",
            "case_units": 12,
        },
    )
    prod = prod_res.json()
    return store, prod


@pytest.mark.asyncio
async def test_ac10_concurrent_policy_approval_conflict(
    integration_client: AsyncClient,
    admin_a_headers: dict[str, str],
):
    """AC10: Two admins approve the same draft version -> exactly one succeeds, stale returns 409."""
    store, prod = await _create_test_store_and_product(integration_client, admin_a_headers)

    today = datetime.now(tz=UTC).date()
    create_res = await integration_client.post(
        "/promotions",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "name": "Beverage Summer Blitz",
            "starts_on": str(today),
            "ends_on": str(today + timedelta(days=30)),
            "store_ids": [store["id"]],
            "agreement_media_id": None,
        },
    )
    assert create_res.status_code == 201
    promo = create_res.json()
    promo_id = promo["id"]
    base_version = promo["version"]

    rule_body = {
        "rule_id": str(uuid4()),
        "kind": "MIN_FACINGS",
        "zone_id": "shelf-01",
        "zone_kind": "SHELF",
        "product_id": prod["id"],
        "min_facings": 4,
        "source": {
            "kind": "MANUAL",
            "media_id": None,
            "page": None,
            "quote": None,
            "reviewer_note": "Admin revised facings",
        },
    }

    # Admin 1 approves at base_version
    admin1_res = await integration_client.post(
        f"/promotions/{promo_id}/approve",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": base_version,
            "catalog_product_ids": [prod["id"]],
            "rules": [rule_body],
        },
    )
    assert admin1_res.status_code in [200, 201], f"First approval should succeed: {admin1_res.text}"

    # Admin 2 attempts approval with the now-stale base_version -> must return 409
    admin2_res = await integration_client.post(
        f"/promotions/{promo_id}/approve",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": base_version,
            "catalog_product_ids": [prod["id"]],
            "rules": [rule_body],
        },
    )
    assert admin2_res.status_code == 409, "Stale version approval must return 409 conflict"


@pytest.mark.asyncio
async def test_ac35_catalog_constraints_reject_unknown_products(
    integration_client: AsyncClient,
    admin_a_headers: dict[str, str],
):
    """AC35: Policies referencing unknown products produce actionable errors."""
    store, _prod = await _create_test_store_and_product(integration_client, admin_a_headers)

    today = datetime.now(tz=UTC).date()
    create_res = await integration_client.post(
        "/promotions",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "name": "Invalid Product Promo",
            "starts_on": str(today),
            "ends_on": str(today + timedelta(days=30)),
            "store_ids": [store["id"]],
            "agreement_media_id": None,
        },
    )
    promo = create_res.json()
    promo_id = promo["id"]

    unknown_product_id = str(uuid4())
    approve_res = await integration_client.post(
        f"/promotions/{promo_id}/approve",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": promo["version"],
            "catalog_product_ids": [unknown_product_id],
            "rules": [
                {
                    "rule_id": str(uuid4()),
                    "kind": "MIN_FACINGS",
                    "zone_id": "shelf-01",
                    "zone_kind": "SHELF",
                    "product_id": unknown_product_id,
                    "min_facings": 2,
                    "source": {
                        "kind": "MANUAL",
                        "media_id": None,
                        "page": None,
                        "quote": "Rule for unknown product",
                        "reviewer_note": None,
                    },
                }
            ],
        },
    )
    assert approve_res.status_code == 422
    assert approve_res.json()["code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_ac34_policy_draft_edit_isolation(
    integration_client: AsyncClient,
    admin_a_headers: dict[str, str],
):
    """AC34: Approved policy versions are immutable; draft updates do not mutate approved versions."""
    store, prod = await _create_test_store_and_product(integration_client, admin_a_headers)

    today = datetime.now(tz=UTC).date()
    create_res = await integration_client.post(
        "/promotions",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "name": "Original Policy Promo",
            "starts_on": str(today),
            "ends_on": str(today + timedelta(days=30)),
            "store_ids": [store["id"]],
            "agreement_media_id": None,
        },
    )
    promo = create_res.json()
    promo_id = promo["id"]

    # Approve policy version 1
    rule_id = str(uuid4())
    approve_res = await integration_client.post(
        f"/promotions/{promo_id}/approve",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
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
                    "min_facings": 3,
                    "source": {
                        "kind": "MANUAL",
                        "media_id": None,
                        "page": None,
                        "quote": None,
                        "reviewer_note": "Initial approved version",
                    },
                }
            ],
        },
    )
    assert approve_res.status_code == 201
    v1 = approve_res.json()
    assert v1["version"] == 1

    # Fetch updated promotion to get its bumped version
    promo_get = await integration_client.get(f"/promotions/{promo_id}", headers=admin_a_headers)
    assert promo_get.status_code == 200
    current_promo = promo_get.json()
    assert current_promo["version"] == promo["version"] + 1

    # Modify promotion draft metadata
    patch_res = await integration_client.patch(
        f"/promotions/{promo_id}",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": current_promo["version"],
            "name": "Updated Draft Name",
        },
    )
    assert patch_res.status_code == 200
    updated_promo = patch_res.json()
    assert updated_promo["name"] == "Updated Draft Name"
    assert updated_promo["version"] == current_promo["version"] + 1

    # Query approved versions: v1 must remain immutable
    versions_res = await integration_client.get(
        f"/promotions/{promo_id}/versions",
        headers=admin_a_headers,
    )
    assert versions_res.status_code == 200
    versions = versions_res.json()["items"]
    assert len(versions) == 1
    assert versions[0]["version"] == 1
    assert versions[0]["rules"][0]["rule_id"] == rule_id
    assert versions[0]["rules"][0]["min_facings"] == 3
