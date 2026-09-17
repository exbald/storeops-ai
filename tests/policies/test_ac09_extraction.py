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


@pytest.mark.asyncio
async def test_ac09_unresolved_rule_proposal_becomes_extraction_gap(
    client,
    workspace_setup,
    sample_store,
    sample_products,
    sample_agreement_media,
    model_gateway,
):
    """Per SEMANTICS.md:46-47: proposals with missing zone_id or invalid product remain extraction gaps."""
    today = datetime.now(tz=UTC).date()
    create_payload = {
        "name": "Gap Proposal Campaign",
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
            "Idempotency-Key": "ac09-gap-promo-create",
        },
    )
    promo = create_res.json()
    promo_id = promo["id"]

    # Register extraction with:
    # 1. Proposal missing zone_id
    # 2. Proposal referencing unknown product
    unknown_prod_id = uuid4()
    mock_extraction = PolicyExtraction(
        media_id=sample_agreement_media.id,
        rules=[
            ExtractedRule(
                kind="MIN_FACINGS",
                product_id=sample_products[0].id,
                zone_kind="SHELF",
                zone_id=None,  # Missing zone_id!
                min_facings=2,
                source_page=1,
                source_quote="2 facings on unspecified shelf.",
            ),
            ExtractedRule(
                kind="REQUIRED_PRODUCT",
                product_id=unknown_prod_id,  # Product not in catalog!
                zone_kind="SHELF",
                zone_id="shelf-main",
                min_facings=None,
                source_page=2,
                source_quote="Must stock mystery beverage.",
            ),
        ],
        gaps=["Standard general ambiguity gap."],
    )
    model_gateway.register_response(PolicyExtraction, mock_extraction)

    extract_res = await client.post(
        f"/promotions/{promo_id}/extract",
        json={"expected_version": promo["version"]},
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac09-extract-gap-job",
        },
    )
    assert extract_res.status_code == 202

    get_res = await client.get(
        f"/promotions/{promo_id}",
        headers=workspace_setup["admin_headers"],
    )
    assert get_res.status_code == 200
    updated = get_res.json()

    # Neither invalid proposal became a valid Rule!
    assert len(updated["extracted_rules"]) == 0
    # Both proposals became extraction gaps along with the general gap
    assert len(updated["extraction_gaps"]) == 3
    assert any("Missing zone_id" in g for g in updated["extraction_gaps"])
    assert any("references unknown product" in g for g in updated["extraction_gaps"])


@pytest.mark.asyncio
async def test_ac09_extract_stale_expected_version_conflict(
    client,
    workspace_setup,
    sample_store,
    sample_agreement_media,
):
    today = datetime.now(tz=UTC).date()
    create_res = await client.post(
        "/promotions",
        json={
            "name": "Stale Extract Promo",
            "starts_on": str(today),
            "ends_on": str(today + timedelta(days=14)),
            "store_ids": [str(sample_store.id)],
            "agreement_media_id": str(sample_agreement_media.id),
        },
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac09-stale-extract-create",
        },
    )
    promo_id = create_res.json()["id"]

    res = await client.post(
        f"/promotions/{promo_id}/extract",
        json={"expected_version": 999},  # Stale version
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac09-stale-extract-call",
        },
    )
    assert res.status_code == 409
    assert res.json()["code"] == "VERSION_CONFLICT"


@pytest.mark.asyncio
async def test_ac09_extract_archived_promotion_conflict(
    client,
    workspace_setup,
    sample_store,
    sample_agreement_media,
):
    today = datetime.now(tz=UTC).date()
    create_res = await client.post(
        "/promotions",
        json={
            "name": "Archived Extract Promo",
            "starts_on": str(today),
            "ends_on": str(today + timedelta(days=14)),
            "store_ids": [str(sample_store.id)],
            "agreement_media_id": str(sample_agreement_media.id),
        },
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac09-arch-extract-create",
        },
    )
    promo = create_res.json()
    promo_id = promo["id"]

    # Archive promo
    await client.patch(
        f"/promotions/{promo_id}",
        json={"expected_version": promo["version"], "archived": True},
        headers=workspace_setup["admin_headers"],
    )

    # Attempt extraction on archived promo -> 409
    res = await client.post(
        f"/promotions/{promo_id}/extract",
        json={"expected_version": promo["version"] + 1},
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac09-arch-extract-call",
        },
    )
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_ac09_extract_missing_agreement_media_error(
    client,
    workspace_setup,
    sample_store,
):
    today = datetime.now(tz=UTC).date()
    create_res = await client.post(
        "/promotions",
        json={
            "name": "No Agreement Promo",
            "starts_on": str(today),
            "ends_on": str(today + timedelta(days=14)),
            "store_ids": [str(sample_store.id)],
            "agreement_media_id": None,
        },
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac09-no-agree-create",
        },
    )
    promo = create_res.json()
    promo_id = promo["id"]

    res = await client.post(
        f"/promotions/{promo_id}/extract",
        json={"expected_version": promo["version"]},
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac09-no-agree-extract",
        },
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_ac09_extract_model_failure_marks_job_failed(
    client,
    workspace_setup,
    sample_store,
    sample_agreement_media,
    state_repo,
    model_gateway,
):
    today = datetime.now(tz=UTC).date()
    create_res = await client.post(
        "/promotions",
        json={
            "name": "Model Fail Promo",
            "starts_on": str(today),
            "ends_on": str(today + timedelta(days=14)),
            "store_ids": [str(sample_store.id)],
            "agreement_media_id": str(sample_agreement_media.id),
        },
        headers={
            **workspace_setup["admin_headers"],
            "Idempotency-Key": "ac09-model-fail-create",
        },
    )
    promo = create_res.json()
    promo_id = promo["id"]

    # Configure gateway to raise
    model_gateway.register_response(
        PolicyExtraction, RuntimeError("Gemini API backend timeout")
    )

    with pytest.raises(RuntimeError, match="Gemini API backend timeout"):
        await client.post(
            f"/promotions/{promo_id}/extract",
            json={"expected_version": promo["version"]},
            headers={
                **workspace_setup["admin_headers"],
                "Idempotency-Key": "ac09-model-fail-extract",
            },
        )

    # Verify job in state_repo was marked FAILED
    jobs = [
        j
        for j in state_repo.jobs.values()
        if str(j.resource_id) == str(promo_id) and j.stage == "FAILED"
    ]
    assert len(jobs) == 1
    assert jobs[0].status == "FAILED" or jobs[0].status.value == "FAILED"
    assert jobs[0].stage == "FAILED"
