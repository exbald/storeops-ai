from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from storeops_contracts.models import (
    Kind,
    Media,
    Status1,
    ZoneKind,
)

from apps.api.ai.schemas import (
    AnalysisProposal,
    ProposedAction,
    ProposedClaim,
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
            original_sha256="e" * 64,
            normalized_sha256="e" * 64,
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
async def test_ac15_evidence_listing_and_locators(
    client,
    workspace_setup,
    sample_store,
    sample_promotion_with_policy,
    sample_ready_media,
):
    headers = workspace_setup["rep_headers"]
    promo, _policy_ver, _rule = sample_promotion_with_policy

    # 1. Create visit & ready media
    res_v = await client.post(
        "/visits",
        json={
            "store_id": str(sample_store.id),
            "notes": "Audit visit for evidence checking",
        },
        headers={**headers, "Idempotency-Key": f"key-{uuid4()}"},
    )
    visit_id = UUID(res_v.json()["id"])
    media = await sample_ready_media(visit_id)

    # 2. Trigger investigation
    res_inv = await client.post(
        "/investigations",
        json={
            "store_id": str(sample_store.id),
            "visit_id": str(visit_id),
            "promotion_id": str(promo.id),
            "media_ids": [str(media.id)],
        },
        headers={**headers, "Idempotency-Key": f"inv-{uuid4()}"},
    )
    assert res_inv.status_code == 202
    job_data = res_inv.json()
    inv_id = job_data["resource_id"]

    # 3. Retrieve evidence items
    res_ev = await client.get(f"/investigations/{inv_id}/evidence", headers=headers)
    assert res_ev.status_code == 200
    ev_list = res_ev.json()
    assert "items" in ev_list
    items = ev_list["items"]
    assert len(items) >= 2  # Must include sales/stock/visual evidence

    # Check locator contents on visual evidence
    kinds = [item["kind"] for item in items]
    assert "SALES_ROWS" in kinds or "VISUAL" in kinds or "POLICY_CLAUSE" in kinds

    for item in items:
        assert item["investigation_id"] == inv_id
        assert "locator" in item
        assert "freshness" in item
        assert "source_sha256" in item


@pytest.mark.asyncio
async def test_ac15_grounding_rejection_of_invented_evidence_ids(
    client,
    workspace_setup,
    sample_store,
    sample_promotion_with_policy,
    sample_ready_media,
    model_gateway,
):
    headers = workspace_setup["rep_headers"]
    promo, _policy_ver, rule = sample_promotion_with_policy

    res_v = await client.post(
        "/visits",
        json={
            "store_id": str(sample_store.id),
            "notes": "Checking ungrounded rejection",
        },
        headers={**headers, "Idempotency-Key": f"key-{uuid4()}"},
    )
    visit_id = UUID(res_v.json()["id"])
    media = await sample_ready_media(visit_id)

    # Register an invalid model response citing an invented, ungrounded evidence_id
    invented_eid = uuid4()

    def invented_evidence_response(prompt: str):
        return AnalysisProposal(
            hypothesis="EXECUTION",
            summary="Hallucinated finding citing invented evidence.",
            claims=[
                ProposedClaim(
                    claim_key="c1",
                    kind="OBSERVATION",
                    text="Fictitious observation with invented evidence.",
                    evidence_ids=[invented_eid],
                )
            ],
            alternatives=[],
            actions=[
                ProposedAction(
                    kind="RESTORE_FACINGS",
                    rule_ids=[rule.rule_id],
                    claim_keys=["c1"],
                    evidence_ids=[invented_eid],
                    instruction="Restore facings.",
                    required_zone_ids=["shelf-1"],
                )
            ],
            unresolved_questions=[],
        )

    model_gateway.register_response(AnalysisProposal, invented_evidence_response)

    res_inv = await client.post(
        "/investigations",
        json={
            "store_id": str(sample_store.id),
            "visit_id": str(visit_id),
            "promotion_id": str(promo.id),
            "media_ids": [str(media.id)],
        },
        headers={**headers, "Idempotency-Key": f"inv-{uuid4()}"},
    )
    assert res_inv.status_code == 202
    job_data = res_inv.json()
    inv_id = job_data["resource_id"]

    res_get = await client.get(f"/investigations/{inv_id}", headers=headers)
    assert res_get.status_code == 200
    inv = res_get.json()
    # Grounding error should cause state to be INCOMPLETE
    assert inv["state"] == "INCOMPLETE"
