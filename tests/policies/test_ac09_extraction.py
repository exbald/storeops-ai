"""Acceptance test AC09: Merchandising policy rule extraction and draft review.

Given an uploaded agreement and catalog,
When extract proposed rules,
Then:
- A draft with page/quote evidence and unresolved gaps is produced.
- No policy becomes approved automatically.
- A manual correction is explicitly marked MANUAL.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from apps.api.ai.schemas import ExtractedRule, PolicyExtraction


@pytest.mark.asyncio
async def test_ac09_extraction_workflow(
    client,
    workspace_setup,
    sample_store,
    sample_products,
    sample_agreement_media,
    model_gateway,
):
    # 1. Create a draft promotion with agreement media attached
    today = datetime.now(tz=UTC).date()
    create_payload = {
        "name": "Q2 Beverage Promotional Plan",
        "starts_on": str(today),
        "ends_on": str(today + timedelta(days=60)),
        "store_ids": [str(sample_store.id)],
        "agreement_media_id": str(sample_agreement_media.id),
    }
    create_res = await client.post(
        "/promotions",
        json=create_payload,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac09-create-promo",
        },
    )
    assert create_res.status_code == 201
    promo = create_res.json()
    promo_id = promo["id"]
    current_version = promo["version"]

    # 2. Register mock AI extraction output on DeterministicModelGateway
    target_product = sample_products[0]
    mock_extraction = PolicyExtraction(
        media_id=sample_agreement_media.id,
        rules=[
            ExtractedRule(
                kind="MIN_FACINGS",
                product_id=target_product.id,
                zone_kind="SHELF",
                zone_id="shelf-main",
                min_facings=3,
                source_page=2,
                source_quote="Vendor agrees to provide minimum of 3 facings on primary shelf.",
            )
        ],
        gaps=[
            "Secondary promotional endcap placement fee clause is ambiguous regarding start date.",
        ],
    )
    model_gateway.register_response(PolicyExtraction, mock_extraction)

    # 3. Trigger rule extraction via POST /promotions/{promotion_id}/extract
    extract_payload = {"expected_version": current_version}
    extract_res = await client.post(
        f"/promotions/{promo_id}/extract",
        json=extract_payload,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac09-extract-job-1",
        },
    )
    assert extract_res.status_code == 202
    job_data = extract_res.json()
    assert job_data["type"] == "POLICY_EXTRACT"
    assert job_data["status"] == "SUCCEEDED"
    assert job_data["stage"] == "EXTRACTED"

    # 4. Read the promotion draft: inspect extracted rules and gaps
    get_res = await client.get(
        f"/promotions/{promo_id}",
        headers=workspace_setup["admin_headers"],
    )
    assert get_res.status_code == 200
    updated_promo = get_res.json()

    # Rule extraction checks:
    # A draft with page/quote evidence and unresolved gaps is produced
    assert len(updated_promo["extracted_rules"]) == 1
    rule = updated_promo["extracted_rules"][0]
    assert rule["kind"] == "MIN_FACINGS"
    assert rule["product_id"] == str(target_product.id)
    assert rule["min_facings"] == 3
    assert rule["source"]["kind"] == "DOCUMENT"
    assert rule["source"]["media_id"] == str(sample_agreement_media.id)
    assert rule["source"]["page"] == 2
    assert "minimum of 3 facings" in rule["source"]["quote"]

    assert len(updated_promo["extraction_gaps"]) == 1
    assert "Secondary promotional endcap" in updated_promo["extraction_gaps"][0]

    # No policy becomes approved automatically!
    assert updated_promo["approved_policy"] is None
    assert updated_promo["draft_revision"] >= 2


@pytest.mark.asyncio
async def test_ac09_manual_rule_explicitly_marked_manual(
    client,
    workspace_setup,
    sample_store,
    sample_products,
    sample_agreement_media,
):
    # Create draft
    today = datetime.now(tz=UTC).date()
    create_payload = {
        "name": "Manual Rule Test Campaign",
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
            "Idempotency-Key": "ac09-manual-promo-create",
        },
    )
    promo = create_res.json()
    promo_id = promo["id"]
    version = promo["version"]

    # Admin approves a policy with a MANUAL rule
    manual_rule_id = str(uuid4())
    approve_payload = {
        "expected_version": version,
        "catalog_product_ids": [str(sample_products[0].id)],
        "rules": [
            {
                "rule_id": manual_rule_id,
                "kind": "MIN_FACINGS",
                "zone_id": "shelf-secondary",
                "zone_kind": "SHELF",
                "product_id": str(sample_products[0].id),
                "min_facings": 2,
                "source": {
                    "kind": "MANUAL",
                    "media_id": None,
                    "page": None,
                    "quote": None,
                    "reviewer_note": "Approved per regional manager verbal agreement on 2026-03-01.",
                },
            }
        ],
    }

    approve_res = await client.post(
        f"/promotions/{promo_id}/approve",
        json=approve_payload,
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac09-approve-manual-1",
        },
    )
    assert approve_res.status_code == 201
    approved = approve_res.json()
    assert approved["version"] == 1
    assert len(approved["rules"]) == 1
    approved_rule = approved["rules"][0]
    assert approved_rule["source"]["kind"] == "MANUAL"
    assert approved_rule["source"]["reviewer_note"] is not None
    assert approved_rule["source"]["quote"] is None
    assert approved_rule["source"]["media_id"] is None
    assert approved_rule["source"]["page"] is None
