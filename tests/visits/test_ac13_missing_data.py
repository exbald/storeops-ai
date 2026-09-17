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
    Alternative,
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
            original_sha256="d" * 64,
            normalized_sha256="d" * 64,
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
async def test_ac13_missing_sales_and_stale_stock_produces_gaps_and_check_stock(
    client,
    workspace_setup,
    sample_store,
    sample_promotion_with_policy,
    sample_ready_media,
    model_gateway,
):
    headers = workspace_setup["rep_headers"]
    promo, _policy_ver, rule = sample_promotion_with_policy

    # Create visit
    res_v = await client.post(
        "/visits",
        json={
            "store_id": str(sample_store.id),
            "notes": "Checking compliance under data gap",
        },
        headers={**headers, "Idempotency-Key": f"key-{uuid4()}"},
    )
    visit_id = UUID(res_v.json()["id"])
    media = await sample_ready_media(visit_id)

    # Custom model response asserting SUPPLY_CONSTRAINT / CHECK_STOCK when inventory is uncertain
    def dynamic_investigation_response(prompt: str):
        import re

        ev_match = re.search(
            r"<available_evidence_ids>(.*?)</available_evidence_ids>", prompt, re.DOTALL
        )
        evidence_ids = []
        if ev_match:
            for raw_id in re.findall(
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                ev_match.group(1),
            ):
                evidence_ids.append(UUID(raw_id))
        eid = evidence_ids[0] if evidence_ids else uuid4()

        return AnalysisProposal(
            hypothesis="SUPPLY_CONSTRAINT",
            summary="Shelf facings zero and backroom stock uncertain; requires physical check.",
            claims=[
                ProposedClaim(
                    claim_key="c1",
                    kind="OBSERVATION",
                    text="Shelf facing is zero.",
                    evidence_ids=[eid],
                )
            ],
            alternatives=[
                Alternative(
                    hypothesis="EXECUTION",
                    reason="Merchandiser may not have restocked shelf.",
                    evidence_ids=[eid],
                )
            ],
            actions=[
                ProposedAction(
                    kind="CHECK_STOCK",
                    rule_ids=[rule.rule_id],
                    claim_keys=["c1"],
                    evidence_ids=[eid],
                    instruction="Verify backroom stock before declaring out of stock.",
                    required_zone_ids=["shelf-1"],
                )
            ],
            unresolved_questions=["Is replenishment on transit?"],
        )

    model_gateway.register_response(AnalysisProposal, dynamic_investigation_response)

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
    assert inv["state"] == "PROPOSED"
    assert inv["diagnosis"]["hypothesis"] == "SUPPLY_CONSTRAINT"
    assert len(inv["actions"]) == 1
    assert inv["actions"][0]["kind"] == "CHECK_STOCK"
