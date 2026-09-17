from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from storeops_contracts.models import (
    Currency,
    Kind,
    Media,
    Status1,
    Workspace,
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


@pytest.mark.asyncio
async def test_ac15_tenant_isolation_on_evidence_and_reports(
    client,
    workspace_setup,
    sample_store,
    sample_promotion_with_policy,
    sample_ready_media,
    analytics_repo,
    model_gateway,
    state_repo,
):
    headers_ws1 = workspace_setup["rep_headers"]
    promo, _policy_ver, _rule = sample_promotion_with_policy
    ws1_id = workspace_setup["workspace_id"]
    ws2_id = uuid4()
    now_dt = datetime.now(UTC)

    # Initialize workspace 2 so rep-user-ws2 has a valid workspace membership
    ws2 = Workspace(
        id=ws2_id,
        workspace_id=ws2_id,
        version=1,
        created_at=now_dt,
        updated_at=now_dt,
        name="Workspace 2",
        brand_name="Brand 2",
        currency=Currency.SGD,
    )
    await state_repo.create_workspace_with_admin(
        ws2, uid="admin-user-ws2", email="admin2@test.com"
    )
    await state_repo.add_membership(
        ws2_id, uid="rep-user-ws2", role="REP", email="rep2@test.com"
    )

    headers_ws2 = {
        "Authorization": "Bearer rep-user-ws2",
        "X-Workspace-Id": str(ws2_id),
    }

    # Commit data in ws1 to get a NO_ACTION report
    await analytics_repo.commit_import_batch(
        workspace_id=ws1_id,
        batch_id=str(uuid4()),
        kind="SALES",
        import_id=uuid4(),
        source_sha256="1" * 64,
        rows=[
            {
                "store_id": sample_store.id,
                "sku": "SKU-ISO-1",
                "business_date": "2026-08-05",
                "units": 100,
                "revenue": 200.0,
                "currency": "SGD",
            },
            {
                "store_id": sample_store.id,
                "sku": "SKU-ISO-1",
                "business_date": "2026-08-10",
                "units": 110,
                "revenue": 220.0,
                "currency": "SGD",
            },
        ],
    )
    await analytics_repo.commit_import_batch(
        workspace_id=ws1_id,
        batch_id=str(uuid4()),
        kind="INVENTORY",
        import_id=uuid4(),
        source_sha256="2" * 64,
        rows=[
            {
                "location_id": sample_store.id,
                "sku": "SKU-ISO-1",
                "observed_at": now_dt.isoformat(),
                "quantity": 50,
                "unit": "UNIT",
                "normalized_units": 50,
            }
        ],
    )

    def no_issue_response(prompt: str):
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
            hypothesis="NO_ISSUE",
            summary="Clean audit.",
            claims=[
                ProposedClaim(
                    claim_key="c1",
                    kind="OBSERVATION",
                    text="Facings conform to rule.",
                    evidence_ids=[eid],
                )
            ],
            alternatives=[],
            actions=[],
            unresolved_questions=[],
        )

    model_gateway.register_response(AnalysisProposal, no_issue_response)

    # 1. Create visit & investigation in workspace 1
    res_v = await client.post(
        "/visits",
        json={"store_id": str(sample_store.id), "notes": "Isolation test visit"},
        headers={**headers_ws1, "Idempotency-Key": f"key-{uuid4()}"},
    )
    visit_id = UUID(res_v.json()["id"])
    media = await sample_ready_media(visit_id)

    res_inv = await client.post(
        "/investigations",
        json={
            "store_id": str(sample_store.id),
            "visit_id": str(visit_id),
            "promotion_id": str(promo.id),
            "media_ids": [str(media.id)],
        },
        headers={**headers_ws1, "Idempotency-Key": f"inv-{uuid4()}"},
    )
    inv_id = res_inv.json()["resource_id"]

    # Retrieve evidence in ws1
    res_ev_ws1 = await client.get(
        f"/investigations/{inv_id}/evidence", headers=headers_ws1
    )
    assert res_ev_ws1.status_code == 200
    evidence_id = res_ev_ws1.json()["items"][0]["id"]

    # Verify visit in ws1 has a closed report
    res_visit = await client.get(f"/visits/{visit_id}", headers=headers_ws1)
    report_id = res_visit.json()["report_ids"][0]

    # 2. Access evidence with workspace 2 headers returns 404
    res_ev_ws2 = await client.get(f"/evidence/{evidence_id}", headers=headers_ws2)
    assert res_ev_ws2.status_code == 404
    assert res_ev_ws2.json()["code"] == "EVIDENCE_NOT_FOUND"

    # 3. Access report with workspace 2 headers returns 404
    res_rep_ws2 = await client.get(f"/reports/{report_id}", headers=headers_ws2)
    assert res_rep_ws2.status_code == 404
    assert res_rep_ws2.json()["code"] == "REPORT_NOT_FOUND"


@pytest.mark.asyncio
async def test_ac15_evidence_pagination(
    client,
    workspace_setup,
    sample_store,
    sample_promotion_with_policy,
    sample_ready_media,
):
    headers = workspace_setup["rep_headers"]
    promo, _policy_ver, _rule = sample_promotion_with_policy

    res_v = await client.post(
        "/visits",
        json={"store_id": str(sample_store.id), "notes": "Pagination test visit"},
        headers={**headers, "Idempotency-Key": f"key-{uuid4()}"},
    )
    visit_id = UUID(res_v.json()["id"])
    media = await sample_ready_media(visit_id)

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
    inv_id = res_inv.json()["resource_id"]

    # List page 1 with limit=1
    res_p1 = await client.get(
        f"/investigations/{inv_id}/evidence?limit=1", headers=headers
    )
    assert res_p1.status_code == 200
    p1 = res_p1.json()
    assert len(p1["items"]) == 1
    assert p1["next_cursor"] is not None

    # List page 2 using next_cursor
    res_p2 = await client.get(
        f"/investigations/{inv_id}/evidence?cursor={p1['next_cursor']}&limit=1",
        headers=headers,
    )
    assert res_p2.status_code == 200
    p2 = res_p2.json()
    assert len(p2["items"]) == 1
    assert p2["items"][0]["id"] != p1["items"][0]["id"]
