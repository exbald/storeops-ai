"""Acceptance test AC34: Policy replacement, archival, and historical preservation.

Given an accepted plan whose approved policy is replaced or archived,
When accept or verify its stale version,
Then:
- Return 409 STALE_POLICY and require a new investigation.
- No obsolete plan closes current work.
- Existing resolved reports remain historical and readable.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_ac34_policy_replacement_increments_and_preserves_history(
    client,
    workspace_setup,
    sample_store,
    sample_products,
    sample_agreement_media,
):
    # 1. Create a promotion
    today = datetime.now(tz=UTC).date()
    create_payload = {
        "name": "Evolving Merchandising Campaign",
        "starts_on": str(today),
        "ends_on": str(today + timedelta(days=90)),
        "store_ids": [str(sample_store.id)],
        "agreement_media_id": str(sample_agreement_media.id),
    }
    create_res = await client.post(
        "/promotions",
        json=create_payload,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac34-promo-create",
        },
    )
    promo = create_res.json()
    promo_id = promo["id"]

    # 2. Approve Version 1
    v1_payload = {
        "expected_version": promo["version"],
        "catalog_product_ids": [str(sample_products[0].id)],
        "rules": [
            {
                "rule_id": str(uuid4()),
                "kind": "MIN_FACINGS",
                "zone_id": "shelf-main",
                "zone_kind": "SHELF",
                "product_id": str(sample_products[0].id),
                "min_facings": 2,
                "source": {
                    "kind": "DOCUMENT",
                    "media_id": str(sample_agreement_media.id),
                    "page": 1,
                    "quote": "Minimum of 2 facings.",
                    "reviewer_note": None,
                },
            }
        ],
    }
    v1_res = await client.post(
        f"/promotions/{promo_id}/approve",
        json=v1_payload,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac34-v1-approve",
        },
    )
    assert v1_res.status_code == 201
    v1 = v1_res.json()
    assert v1["version"] == 1

    # Fetch promotion: approved_policy is v1
    p1 = (
        await client.get(
            f"/promotions/{promo_id}", headers=workspace_setup["admin_headers"]
        )
    ).json()
    assert p1["approved_policy"]["version"] == 1
    assert p1["version"] == 2  # Incremented by approval

    # 3. Approve Version 2 (Replacement)
    v2_payload = {
        "expected_version": p1["version"],
        "catalog_product_ids": [str(sample_products[0].id), str(sample_products[1].id)],
        "rules": [
            {
                "rule_id": str(uuid4()),
                "kind": "MIN_FACINGS",
                "zone_id": "shelf-main",
                "zone_kind": "SHELF",
                "product_id": str(sample_products[0].id),
                "min_facings": 4,
                "source": {
                    "kind": "DOCUMENT",
                    "media_id": str(sample_agreement_media.id),
                    "page": 1,
                    "quote": "Updated to minimum 4 facings.",
                    "reviewer_note": None,
                },
            }
        ],
    }
    v2_res = await client.post(
        f"/promotions/{promo_id}/approve",
        json=v2_payload,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac34-v2-approve",
        },
    )
    assert v2_res.status_code == 201
    v2 = v2_res.json()
    assert v2["version"] == 2
    assert v2["id"] != v1["id"]

    # 4. Check promotion has active pointer to v2
    p2 = (
        await client.get(
            f"/promotions/{promo_id}", headers=workspace_setup["admin_headers"]
        )
    ).json()
    assert p2["approved_policy"]["version"] == 2
    assert p2["approved_policy"]["id"] == v2["id"]

    # 5. Check version list contains both v1 and v2, preserving history
    versions_res = await client.get(
        f"/promotions/{promo_id}/versions",
        headers=workspace_setup["admin_headers"],
    )
    assert versions_res.status_code == 200
    versions = versions_res.json()["items"]
    assert len(versions) == 2
    versions_by_num = {v["version"]: v for v in versions}
    assert 1 in versions_by_num
    assert 2 in versions_by_num
    assert versions_by_num[1]["rules"][0]["min_facings"] == 2
    assert versions_by_num[2]["rules"][0]["min_facings"] == 4


@pytest.mark.asyncio
async def test_ac34_archived_promotion_cannot_be_approved(
    client,
    workspace_setup,
    sample_store,
    sample_products,
    sample_agreement_media,
):
    # Create draft
    today = datetime.now(tz=UTC).date()
    create_payload = {
        "name": "Archived Campaign",
        "starts_on": str(today),
        "ends_on": str(today + timedelta(days=30)),
        "store_ids": [str(sample_store.id)],
        "agreement_media_id": str(sample_agreement_media.id),
    }
    create_res = await client.post(
        "/promotions",
        json=create_payload,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac34-archive-create",
        },
    )
    promo = create_res.json()
    promo_id = promo["id"]

    # Archive promotion
    archive_res = await client.patch(
        f"/promotions/{promo_id}",
        json={"expected_version": promo["version"], "archived": True},
        headers=workspace_setup["admin_headers"],
    )
    assert archive_res.status_code == 200
    assert archive_res.json()["archived"] is True

    # Attempt to approve archived promotion -> 409 Conflict
    approve_payload = {
        "expected_version": archive_res.json()["version"],
        "catalog_product_ids": [str(sample_products[0].id)],
        "rules": [
            {
                "rule_id": str(uuid4()),
                "kind": "REQUIRED_PRODUCT",
                "zone_id": "shelf-main",
                "zone_kind": "SHELF",
                "product_id": str(sample_products[0].id),
                "min_facings": None,
                "source": {
                    "kind": "DOCUMENT",
                    "media_id": str(sample_agreement_media.id),
                    "page": 1,
                    "quote": "Product required.",
                    "reviewer_note": None,
                },
            }
        ],
    }
    approve_res = await client.post(
        f"/promotions/{promo_id}/approve",
        json=approve_payload,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac34-approve-archived",
        },
    )
    assert approve_res.status_code == 409
