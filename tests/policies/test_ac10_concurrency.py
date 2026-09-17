"""Acceptance test AC10: Policy version approval concurrency and immutability.

Given two admins reading the same draft version,
When both approve different revisions,
Then:
- Exactly one current-version approval succeeds.
- The stale approval returns 409.
- Approved versions and their rules remain immutable.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_ac10_concurrent_approvals(
    client,
    workspace_setup,
    sample_store,
    sample_products,
    sample_agreement_media,
):
    # 1. Create a draft promotion
    today = datetime.now(tz=UTC).date()
    create_payload = {
        "name": "Summer Promotional Blitz",
        "starts_on": str(today),
        "ends_on": str(today + timedelta(days=45)),
        "store_ids": [str(sample_store.id)],
        "agreement_media_id": str(sample_agreement_media.id),
    }
    create_res = await client.post(
        "/promotions",
        json=create_payload,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac10-promo-create",
        },
    )
    promo = create_res.json()
    promo_id = promo["id"]
    base_version = promo["version"]

    # 2. Both admins view the same draft at base_version
    admin1_payload = {
        "expected_version": base_version,
        "catalog_product_ids": [str(sample_products[0].id)],
        "rules": [
            {
                "rule_id": str(uuid4()),
                "kind": "MIN_FACINGS",
                "zone_id": "shelf-main",
                "zone_kind": "SHELF",
                "product_id": str(sample_products[0].id),
                "min_facings": 3,
                "source": {
                    "kind": "DOCUMENT",
                    "media_id": str(sample_agreement_media.id),
                    "page": 1,
                    "quote": "Rule 1: 3 facings required.",
                    "reviewer_note": None,
                },
            }
        ],
    }

    admin2_payload = {
        "expected_version": base_version,
        "catalog_product_ids": [str(sample_products[1].id)],
        "rules": [
            {
                "rule_id": str(uuid4()),
                "kind": "MIN_FACINGS",
                "zone_id": "shelf-secondary",
                "zone_kind": "SHELF",
                "product_id": str(sample_products[1].id),
                "min_facings": 4,
                "source": {
                    "kind": "DOCUMENT",
                    "media_id": str(sample_agreement_media.id),
                    "page": 2,
                    "quote": "Rule 2: 4 facings required.",
                    "reviewer_note": None,
                },
            }
        ],
    }

    # Admin 1 approves first -> succeeds with 201 Created
    res1 = await client.post(
        f"/promotions/{promo_id}/approve",
        json=admin1_payload,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac10-admin1-approve",
        },
    )
    assert res1.status_code == 201
    v1 = res1.json()
    assert v1["version"] == 1
    assert v1["rules"][0]["min_facings"] == 3

    # Admin 2 attempts to approve the stale draft with expected_version=base_version -> 409
    res2 = await client.post(
        f"/promotions/{promo_id}/approve",
        json=admin2_payload,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac10-admin2-approve",
        },
    )
    assert res2.status_code == 409
    err = res2.json()
    assert err["code"] == "VERSION_CONFLICT"

    # Verify approved version 1 remains immutable in history
    versions_res = await client.get(
        f"/promotions/{promo_id}/versions",
        headers=workspace_setup["admin_headers"],
    )
    assert versions_res.status_code == 200
    versions = versions_res.json()["items"]
    assert len(versions) == 1
    assert versions[0]["version"] == 1
    assert versions[0]["rules"][0]["min_facings"] == 3
    assert versions[0]["content_sha256"] is not None
    assert len(versions[0]["content_sha256"]) == 64


@pytest.mark.asyncio
async def test_ac10_approved_policy_immutability_across_reads_and_updates(
    client,
    workspace_setup,
    sample_store,
    sample_products,
    sample_agreement_media,
):
    """Assert full-rule equality plus content_sha256 stability across reads and promotion updates."""
    today = datetime.now(tz=UTC).date()
    create_res = await client.post(
        "/promotions",
        json={
            "name": "Immutability Promo",
            "starts_on": str(today),
            "ends_on": str(today + timedelta(days=30)),
            "store_ids": [str(sample_store.id)],
            "agreement_media_id": str(sample_agreement_media.id),
        },
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac10-immut-create",
        },
    )
    promo = create_res.json()
    promo_id = promo["id"]

    rule_id = str(uuid4())
    approve_payload = {
        "expected_version": promo["version"],
        "catalog_product_ids": [str(sample_products[0].id)],
        "rules": [
            {
                "rule_id": rule_id,
                "kind": "MIN_FACINGS",
                "zone_id": "shelf-main",
                "zone_kind": "SHELF",
                "product_id": str(sample_products[0].id),
                "min_facings": 5,
                "source": {
                    "kind": "DOCUMENT",
                    "media_id": str(sample_agreement_media.id),
                    "page": 1,
                    "quote": "Rule quote for immutability test.",
                    "reviewer_note": None,
                },
            }
        ],
    }
    app_res = await client.post(
        f"/promotions/{promo_id}/approve",
        json=approve_payload,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac10-immut-approve",
        },
    )
    assert app_res.status_code == 201
    approved_ver = app_res.json()
    original_sha = approved_ver["content_sha256"]
    original_rules = approved_ver["rules"]

    # 1. Read via GET /promotions/{id}
    promo_read_1 = (
        await client.get(
            f"/promotions/{promo_id}", headers=workspace_setup["admin_headers"]
        )
    ).json()
    assert promo_read_1["approved_policy"]["content_sha256"] == original_sha
    assert promo_read_1["approved_policy"]["rules"] == original_rules

    # 2. Read via GET /promotions/{id}/versions
    ver_read_1 = (
        await client.get(
            f"/promotions/{promo_id}/versions",
            headers=workspace_setup["admin_headers"],
        )
    ).json()["items"][0]
    assert ver_read_1["content_sha256"] == original_sha
    assert ver_read_1["rules"] == original_rules

    # 3. Update promotion metadata (e.g. name, dates)
    patch_res = await client.patch(
        f"/promotions/{promo_id}",
        json={
            "expected_version": promo_read_1["version"],
            "name": "Updated Immutability Promo Name",
        },
        headers=workspace_setup["admin_headers"],
    )
    assert patch_res.status_code == 200

    # 4. Assert policy version and rules are untouched
    ver_read_2 = (
        await client.get(
            f"/promotions/{promo_id}/versions",
            headers=workspace_setup["admin_headers"],
        )
    ).json()["items"][0]
    assert ver_read_2["content_sha256"] == original_sha
    assert ver_read_2["rules"] == original_rules
    assert ver_read_2["rules"][0]["min_facings"] == 5
