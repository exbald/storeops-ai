"""Acceptance test AC35: Catalog constraints and rule predicate validation on policy approval.

Given policies referencing too many, archived or unknown products,
When approve/start an investigation,
Then:
- Catalog constraints produce actionable errors.
- No silent reference truncation or hardcoded SKU fallback occurs.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from storeops_contracts.models import Product


@pytest.mark.asyncio
async def test_ac35_rejects_unknown_product_id(
    client,
    workspace_setup,
    sample_store,
    sample_products,
    sample_agreement_media,
):
    today = datetime.now(tz=UTC).date()
    create_payload = {
        "name": "Unknown Product Policy",
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
            "Idempotency-Key": "ac35-unknown-prod-create",
        },
    )
    promo = create_res.json()
    promo_id = promo["id"]

    unknown_id = str(uuid4())
    approve_payload = {
        "expected_version": promo["version"],
        "catalog_product_ids": [unknown_id],
        "rules": [
            {
                "rule_id": str(uuid4()),
                "kind": "MIN_FACINGS",
                "zone_id": "shelf-main",
                "zone_kind": "SHELF",
                "product_id": unknown_id,
                "min_facings": 2,
                "source": {
                    "kind": "DOCUMENT",
                    "media_id": str(sample_agreement_media.id),
                    "page": 1,
                    "quote": "Rule quote.",
                    "reviewer_note": None,
                },
            }
        ],
    }
    res = await client.post(
        f"/promotions/{promo_id}/approve",
        json=approve_payload,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac35-unknown-prod-approve",
        },
    )
    assert res.status_code == 422
    data = res.json()
    # Must produce actionable error message identifying missing product
    assert (
        unknown_id in data["message"]
        or "unknown" in data["message"].lower()
        or "not found" in data["message"].lower()
    )


@pytest.mark.asyncio
async def test_ac35_rejects_archived_product_id(
    client,
    workspace_setup,
    catalog_repo,
    sample_store,
    sample_agreement_media,
):
    ws_id = workspace_setup["workspace_id"]
    now = datetime.now(UTC)
    # Create an archived product (active=False)
    archived_prod = Product(
        id=uuid4(),
        workspace_id=ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        sku="DISCONT-001",
        name="Discontinued Coffee Pods",
        case_units=6,
        reference_media_ids=[],
        active=False,
    )
    await catalog_repo.create_product(archived_prod)

    today = datetime.now(tz=UTC).date()
    create_payload = {
        "name": "Archived Product Campaign",
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
            "Idempotency-Key": "ac35-archived-prod-create",
        },
    )
    promo = create_res.json()
    promo_id = promo["id"]

    approve_payload = {
        "expected_version": promo["version"],
        "catalog_product_ids": [str(archived_prod.id)],
        "rules": [
            {
                "rule_id": str(uuid4()),
                "kind": "MIN_FACINGS",
                "zone_id": "shelf-main",
                "zone_kind": "SHELF",
                "product_id": str(archived_prod.id),
                "min_facings": 2,
                "source": {
                    "kind": "DOCUMENT",
                    "media_id": str(sample_agreement_media.id),
                    "page": 1,
                    "quote": "Rule quote.",
                    "reviewer_note": None,
                },
            }
        ],
    }
    res = await client.post(
        f"/promotions/{promo_id}/approve",
        json=approve_payload,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac35-archived-prod-approve",
        },
    )
    assert res.status_code == 422
    data = res.json()
    assert "archived" in data["message"].lower()


@pytest.mark.asyncio
async def test_ac35_rejects_rule_referencing_product_not_in_catalog_product_ids(
    client,
    workspace_setup,
    sample_store,
    sample_products,
    sample_agreement_media,
):
    today = datetime.now(tz=UTC).date()
    create_payload = {
        "name": "Mismatched Product Rule",
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
            "Idempotency-Key": "ac35-mismatch-create",
        },
    )
    promo = create_res.json()
    promo_id = promo["id"]

    # catalog_product_ids only contains sample_products[0], but rule references sample_products[1]
    approve_payload = {
        "expected_version": promo["version"],
        "catalog_product_ids": [str(sample_products[0].id)],
        "rules": [
            {
                "rule_id": str(uuid4()),
                "kind": "MIN_FACINGS",
                "zone_id": "shelf-main",
                "zone_kind": "SHELF",
                "product_id": str(sample_products[1].id),
                "min_facings": 2,
                "source": {
                    "kind": "DOCUMENT",
                    "media_id": str(sample_agreement_media.id),
                    "page": 1,
                    "quote": "Rule quote.",
                    "reviewer_note": None,
                },
            }
        ],
    }
    res = await client.post(
        f"/promotions/{promo_id}/approve",
        json=approve_payload,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac35-mismatch-approve",
        },
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_ac35_rule_predicate_validation(
    client,
    workspace_setup,
    sample_store,
    sample_products,
    sample_agreement_media,
):
    today = datetime.now(tz=UTC).date()
    create_payload = {
        "name": "Predicate Validation Test",
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
            "Idempotency-Key": "ac35-predicate-create",
        },
    )
    promo = create_res.json()
    promo_id = promo["id"]

    # 1. REQUIRED_PRODUCT must have zone_kind == SHELF and product_id != None
    bad_req_prod = {
        "expected_version": promo["version"],
        "catalog_product_ids": [str(sample_products[0].id)],
        "rules": [
            {
                "rule_id": str(uuid4()),
                "kind": "REQUIRED_PRODUCT",
                "zone_id": "display-front",
                "zone_kind": "DISPLAY",  # Violation: REQUIRED_PRODUCT requires SHELF
                "product_id": str(sample_products[0].id),
                "min_facings": None,
                "source": {
                    "kind": "DOCUMENT",
                    "media_id": str(sample_agreement_media.id),
                    "page": 1,
                    "quote": "Rule quote.",
                    "reviewer_note": None,
                },
            }
        ],
    }
    res1 = await client.post(
        f"/promotions/{promo_id}/approve",
        json=bad_req_prod,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac35-bad-req-prod",
        },
    )
    assert res1.status_code == 422

    # 2. REQUIRED_DISPLAY must have zone_kind == DISPLAY and product_id == None
    bad_req_disp = {
        "expected_version": promo["version"],
        "catalog_product_ids": [str(sample_products[0].id)],
        "rules": [
            {
                "rule_id": str(uuid4()),
                "kind": "REQUIRED_DISPLAY",
                "zone_id": "shelf-main",
                "zone_kind": "SHELF",  # Violation: REQUIRED_DISPLAY requires DISPLAY
                "product_id": None,
                "min_facings": None,
                "source": {
                    "kind": "DOCUMENT",
                    "media_id": str(sample_agreement_media.id),
                    "page": 1,
                    "quote": "Rule quote.",
                    "reviewer_note": None,
                },
            }
        ],
    }
    res2 = await client.post(
        f"/promotions/{promo_id}/approve",
        json=bad_req_disp,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac35-bad-req-disp",
        },
    )
    assert res2.status_code == 422

    # 3. MANUAL source must have reviewer_note and NO document fields
    bad_manual = {
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
                    "kind": "MANUAL",
                    "media_id": str(
                        sample_agreement_media.id
                    ),  # Violation: MANUAL must not have media_id
                    "page": 1,
                    "quote": "Fabricated quote",
                    "reviewer_note": "Note",
                },
            }
        ],
    }
    res3 = await client.post(
        f"/promotions/{promo_id}/approve",
        json=bad_manual,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac35-bad-manual",
        },
    )
    assert res3.status_code == 422


@pytest.mark.asyncio
async def test_ac35_rejects_duplicate_rule_ids(
    client,
    workspace_setup,
    sample_store,
    sample_products,
    sample_agreement_media,
):
    today = datetime.now(tz=UTC).date()
    create_res = await client.post(
        "/promotions",
        json={
            "name": "Duplicate Rules Test",
            "starts_on": str(today),
            "ends_on": str(today + timedelta(days=30)),
            "store_ids": [str(sample_store.id)],
            "agreement_media_id": str(sample_agreement_media.id),
        },
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac35-dup-rules-create",
        },
    )
    promo = create_res.json()
    promo_id = promo["id"]

    shared_rule_id = str(uuid4())
    approve_payload = {
        "expected_version": promo["version"],
        "catalog_product_ids": [str(sample_products[0].id), str(sample_products[1].id)],
        "rules": [
            {
                "rule_id": shared_rule_id,
                "kind": "MIN_FACINGS",
                "zone_id": "shelf-main",
                "zone_kind": "SHELF",
                "product_id": str(sample_products[0].id),
                "min_facings": 2,
                "source": {
                    "kind": "DOCUMENT",
                    "media_id": str(sample_agreement_media.id),
                    "page": 1,
                    "quote": "Quote 1.",
                    "reviewer_note": None,
                },
            },
            {
                "rule_id": shared_rule_id,  # DUPLICATE ID!
                "kind": "MIN_FACINGS",
                "zone_id": "shelf-main",
                "zone_kind": "SHELF",
                "product_id": str(sample_products[1].id),
                "min_facings": 3,
                "source": {
                    "kind": "DOCUMENT",
                    "media_id": str(sample_agreement_media.id),
                    "page": 1,
                    "quote": "Quote 2.",
                    "reviewer_note": None,
                },
            },
        ],
    }
    res = await client.post(
        f"/promotions/{promo_id}/approve",
        json=approve_payload,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac35-dup-rules-approve",
        },
    )
    assert res.status_code == 422
    assert "duplicate rule" in res.json()["message"].lower()


@pytest.mark.asyncio
async def test_ac35_rejects_document_source_with_wrong_media_id(
    client,
    workspace_setup,
    sample_store,
    sample_products,
    sample_agreement_media,
):
    today = datetime.now(tz=UTC).date()
    create_res = await client.post(
        "/promotions",
        json={
            "name": "Wrong Media Test",
            "starts_on": str(today),
            "ends_on": str(today + timedelta(days=30)),
            "store_ids": [str(sample_store.id)],
            "agreement_media_id": str(sample_agreement_media.id),
        },
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac35-wrong-media-create",
        },
    )
    promo = create_res.json()
    promo_id = promo["id"]

    foreign_media_id = str(uuid4())
    approve_payload = {
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
                    "media_id": foreign_media_id,  # Does not match promo.agreement_media_id
                    "page": 1,
                    "quote": "Quote citing wrong media.",
                    "reviewer_note": None,
                },
            }
        ],
    }
    res = await client.post(
        f"/promotions/{promo_id}/approve",
        json=approve_payload,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac35-wrong-media-approve",
        },
    )
    assert res.status_code == 422
    assert (
        "does not match" in res.json()["message"].lower()
        or "not found" in res.json()["message"].lower()
    )


@pytest.mark.asyncio
async def test_ac35_rejects_document_source_out_of_bounds_page(
    client,
    workspace_setup,
    sample_store,
    sample_products,
    sample_agreement_media,
):
    today = datetime.now(tz=UTC).date()
    create_res = await client.post(
        "/promotions",
        json={
            "name": "Out of Bounds Page Test",
            "starts_on": str(today),
            "ends_on": str(today + timedelta(days=30)),
            "store_ids": [str(sample_store.id)],
            "agreement_media_id": str(sample_agreement_media.id),
        },
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac35-page-bounds-create",
        },
    )
    promo = create_res.json()
    promo_id = promo["id"]

    approve_payload = {
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
                    "page": 15,  # Out of bounds (> 10) per SEMANTICS.md:40-42
                    "quote": "Quote from page 15.",
                    "reviewer_note": None,
                },
            }
        ],
    }
    res = await client.post(
        f"/promotions/{promo_id}/approve",
        json=approve_payload,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac35-page-bounds-approve",
        },
    )
    assert res.status_code == 422
    data = res.json()
    assert (
        any("page" in (d.get("field") or "") for d in data.get("details", []))
        or "page" in data.get("message", "").lower()
    )
