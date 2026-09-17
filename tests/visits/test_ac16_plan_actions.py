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
            original_sha256="f" * 64,
            normalized_sha256="f" * 64,
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
async def test_ac16_accept_plan_revision_idempotency_and_conflict(
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
        json={"store_id": str(sample_store.id), "notes": "Plan revision test"},
        headers={**headers, "Idempotency-Key": f"key-{uuid4()}"},
    )
    visit_id = UUID(res_v.json()["id"])
    media = await sample_ready_media(visit_id)

    # 2. Start investigation
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
    inv_id = res_inv.json()["resource_id"]

    res_get = await client.get(f"/investigations/{inv_id}", headers=headers)
    inv = res_get.json()
    assert inv["state"] == "PROPOSED"
    current_ver = inv["version"]

    # 3. Accept investigation plan
    accept_key = f"acc-{uuid4()}"
    accept_payload = {"expected_version": current_ver}
    res_acc = await client.post(
        f"/investigations/{inv_id}/accept",
        json=accept_payload,
        headers={**headers, "Idempotency-Key": accept_key},
    )
    assert res_acc.status_code == 200, res_acc.text
    acc_inv = res_acc.json()
    assert acc_inv["state"] == "ACCEPTED"
    assert acc_inv["accepted_at"] is not None
    assert acc_inv["accepted_by"] == workspace_setup["rep_uid"]
    assert acc_inv["version"] == current_ver + 1

    # 4. Idempotency replay with same key & body returns exact same 200
    res_replay = await client.post(
        f"/investigations/{inv_id}/accept",
        json=accept_payload,
        headers={**headers, "Idempotency-Key": accept_key},
    )
    assert res_replay.status_code == 200
    assert res_replay.json()["version"] == acc_inv["version"]

    # 5. Idempotency replay with altered body returns 409 conflict
    res_conflict = await client.post(
        f"/investigations/{inv_id}/accept",
        json={"expected_version": 999},
        headers={**headers, "Idempotency-Key": accept_key},
    )
    assert res_conflict.status_code == 409

    # 6. Re-accepting with stale version returns 409 conflict
    res_stale = await client.post(
        f"/investigations/{inv_id}/accept",
        json={"expected_version": current_ver},
        headers={**headers, "Idempotency-Key": f"acc-stale-{uuid4()}"},
    )
    assert res_stale.status_code == 409


@pytest.mark.asyncio
async def test_ac16_rep_action_status_and_forbidden_verification(
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
        json={"store_id": str(sample_store.id), "notes": "Action update test"},
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

    # Accept plan first
    res_get = await client.get(f"/investigations/{inv_id}", headers=headers)
    inv = res_get.json()
    action = inv["actions"][0]
    action_id = action["id"]

    res_acc = await client.post(
        f"/investigations/{inv_id}/accept",
        json={"expected_version": inv["version"]},
        headers={**headers, "Idempotency-Key": f"acc-{uuid4()}"},
    )
    accepted_inv = res_acc.json()

    # Rep updates action to CLAIMED_DONE
    res_action = await client.patch(
        f"/investigations/{inv_id}/actions/{action_id}",
        json={"expected_version": accepted_inv["version"], "status": "CLAIMED_DONE"},
        headers=headers,
    )
    assert res_action.status_code == 200, res_action.text
    updated_inv = res_action.json()
    updated_action = next(a for a in updated_inv["actions"] if a["id"] == action_id)
    assert updated_action["status"] == "CLAIMED_DONE"

    # Rep attempting to set VERIFIED or RESOLVED must be rejected with 422
    res_invalid_1 = await client.patch(
        f"/investigations/{inv_id}/actions/{action_id}",
        json={"expected_version": updated_inv["version"], "status": "VERIFIED"},
        headers=headers,
    )
    assert res_invalid_1.status_code == 422

    res_invalid_2 = await client.patch(
        f"/investigations/{inv_id}/actions/{action_id}",
        json={"expected_version": updated_inv["version"], "status": "RESOLVED"},
        headers=headers,
    )
    assert res_invalid_2.status_code == 422


@pytest.mark.asyncio
async def test_ac16_dismiss_investigation_releases_active_link(
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
        json={"store_id": str(sample_store.id), "notes": "Dismiss link test"},
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

    # Verify visit currently has active_investigation_id
    res_visit_before = await client.get(f"/visits/{visit_id}", headers=headers)
    assert res_visit_before.json()["active_investigation_id"] == inv_id

    # Dismiss proposal
    res_inv_obj = await client.get(f"/investigations/{inv_id}", headers=headers)
    res_dismiss = await client.post(
        f"/investigations/{inv_id}/dismiss",
        json={
            "expected_version": res_inv_obj.json()["version"],
            "reason": "Store manager rejected proposed rearrangement",
        },
        headers={**headers, "Idempotency-Key": f"dismiss-{uuid4()}"},
    )
    assert res_dismiss.status_code == 200
    assert res_dismiss.json()["state"] == "DISMISSED"

    # Verify visit active_investigation_id is now released
    res_visit_after = await client.get(f"/visits/{visit_id}", headers=headers)
    assert res_visit_after.json()["active_investigation_id"] is None

    # We can now launch a new investigation on the same visit without 409 conflict
    res_inv_2 = await client.post(
        "/investigations",
        json={
            "store_id": str(sample_store.id),
            "visit_id": str(visit_id),
            "promotion_id": str(promo.id),
            "media_ids": [str(media.id)],
        },
        headers={**headers, "Idempotency-Key": f"inv2-{uuid4()}"},
    )
    assert res_inv_2.status_code == 202


@pytest.mark.asyncio
async def test_ac16_no_issue_outcome_creates_no_action_report_and_closes_visit(
    client,
    workspace_setup,
    sample_store,
    sample_promotion_with_policy,
    sample_ready_media,
    model_gateway,
    analytics_repo,
):
    headers = workspace_setup["rep_headers"]
    promo, _policy_ver, _rule = sample_promotion_with_policy
    ws_id = workspace_setup["workspace_id"]
    now_dt = datetime.now(UTC)

    # Seed complete sales and stock data so commercial coverage is fully SUPPORTED
    await analytics_repo.commit_import_batch(
        workspace_id=ws_id,
        batch_id=str(uuid4()),
        kind="SALES",
        import_id=uuid4(),
        source_sha256="a" * 64,
        rows=[
            {
                "store_id": sample_store.id,
                "sku": "SKU-OK-1",
                "business_date": "2026-08-05",
                "units": 100,
                "revenue": 200.0,
                "currency": "SGD",
            },
            {
                "store_id": sample_store.id,
                "sku": "SKU-OK-1",
                "business_date": "2026-08-10",
                "units": 110,
                "revenue": 220.0,
                "currency": "SGD",
            },
        ],
    )
    await analytics_repo.commit_import_batch(
        workspace_id=ws_id,
        batch_id=str(uuid4()),
        kind="INVENTORY",
        import_id=uuid4(),
        source_sha256="b" * 64,
        rows=[
            {
                "location_id": sample_store.id,
                "sku": "SKU-OK-1",
                "observed_at": now_dt.isoformat(),
                "quantity": 50,
                "unit": "UNIT",
                "normalized_units": 50,
            }
        ],
    )

    res_v = await client.post(
        "/visits",
        json={"store_id": str(sample_store.id), "notes": "Clean audit visit"},
        headers={**headers, "Idempotency-Key": f"key-{uuid4()}"},
    )
    visit_id = UUID(res_v.json()["id"])
    media = await sample_ready_media(visit_id)

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
            summary="All facings compliant with approved policy. Sales steady.",
            claims=[
                ProposedClaim(
                    claim_key="c1",
                    kind="OBSERVATION",
                    text="Shelf facing count meets or exceeds requirement.",
                    evidence_ids=[eid],
                )
            ],
            alternatives=[],
            actions=[],
            unresolved_questions=[],
        )

    model_gateway.register_response(AnalysisProposal, no_issue_response)

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
    inv_id = res_inv.json()["resource_id"]

    res_get = await client.get(f"/investigations/{inv_id}", headers=headers)
    inv = res_get.json()
    assert inv["state"] == "NO_ACTION"
    assert inv["diagnosis"]["support"] == "SUPPORTED"
    assert len(inv["actions"]) == 0

    # Verify visit is closed and has report attached
    res_visit = await client.get(f"/visits/{visit_id}", headers=headers)
    visit = res_visit.json()
    assert visit["status"] == "CLOSED"
    assert len(visit["report_ids"]) == 1
    report_id = visit["report_ids"][0]

    # Verify report outcome is NO_ACTION
    res_report = await client.get(f"/reports/{report_id}", headers=headers)
    assert res_report.status_code == 200
    report = res_report.json()
    assert report["outcome"] == "NO_ACTION"
    assert report["investigation_id"] == inv_id
    assert report["visit_id"] == str(visit_id)


@pytest.mark.asyncio
async def test_ac16_no_issue_with_incomplete_data_produces_needs_work(
    client,
    workspace_setup,
    sample_store,
    sample_promotion_with_policy,
    sample_ready_media,
    model_gateway,
):
    headers = workspace_setup["rep_headers"]
    promo, _policy_ver, _rule = sample_promotion_with_policy

    res_v = await client.post(
        "/visits",
        json={"store_id": str(sample_store.id), "notes": "Incomplete audit visit"},
        headers={**headers, "Idempotency-Key": f"key-{uuid4()}"},
    )
    visit_id = UUID(res_v.json()["id"])
    media = await sample_ready_media(visit_id)

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
            summary="Compliant facings, but no sales/stock data in analytics.",
            claims=[
                ProposedClaim(
                    claim_key="c1",
                    kind="OBSERVATION",
                    text="Shelf facings comply with approved policy.",
                    evidence_ids=[eid],
                )
            ],
            alternatives=[],
            actions=[],
            unresolved_questions=[],
        )

    model_gateway.register_response(AnalysisProposal, no_issue_response)

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
    inv_id = res_inv.json()["resource_id"]

    res_get = await client.get(f"/investigations/{inv_id}", headers=headers)
    inv = res_get.json()
    # Incomplete commercial window gates NO_ISSUE to NEEDS_WORK per SEMANTICS
    assert inv["state"] == "NEEDS_WORK"
    assert inv["diagnosis"]["support"] == "LIMITED"

    # Visit remains open
    res_visit = await client.get(f"/visits/{visit_id}", headers=headers)
    assert res_visit.json()["status"] == "OPEN"


@pytest.mark.asyncio
async def test_ac16_stale_policy_conflict_on_accept(
    client,
    workspace_setup,
    sample_store,
    sample_promotion_with_policy,
    sample_ready_media,
    policy_repo,
):
    headers = workspace_setup["rep_headers"]
    promo, policy_ver, _rule = sample_promotion_with_policy
    ws_id = workspace_setup["workspace_id"]
    now = datetime.now(UTC)

    # 1. Start investigation with policy version 1
    res_v = await client.post(
        "/visits",
        json={"store_id": str(sample_store.id), "notes": "Stale policy test"},
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
    assert res_inv.status_code == 202
    inv_id = res_inv.json()["resource_id"]

    res_get = await client.get(f"/investigations/{inv_id}", headers=headers)
    inv = res_get.json()
    assert inv["state"] == "PROPOSED"
    ver = inv["version"]

    # 2. Advance policy version for this promotion to version 2
    from storeops_contracts.models import PolicyVersion as PVModel

    new_pv = PVModel(
        id=uuid4(),
        promotion_id=promo.id,
        version=2,
        rules=policy_ver.rules,
        catalog_product_ids=policy_ver.catalog_product_ids,
        store_ids=policy_ver.store_ids,
        starts_on=policy_ver.starts_on,
        ends_on=policy_ver.ends_on,
        approved_at=now,
        approved_by="admin-user",
        content_sha256="9" * 64,
    )
    await policy_repo.create_policy_version(ws_id, new_pv)
    promo.approved_policy = new_pv
    promo.version += 1
    await policy_repo.update_promotion(ws_id, promo)

    # 3. Attempt to accept investigation with stale policy
    res_acc = await client.post(
        f"/investigations/{inv_id}/accept",
        json={"expected_version": ver},
        headers={**headers, "Idempotency-Key": f"acc-{uuid4()}"},
    )
    assert res_acc.status_code == 409
    assert res_acc.json()["code"] == "STALE_POLICY"


@pytest.mark.asyncio
async def test_ac16_version_conflict_and_invalid_action_status_on_update_action(
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
        json={"store_id": str(sample_store.id), "notes": "Action conflict test"},
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
    res_get = await client.get(f"/investigations/{inv_id}", headers=headers)
    inv = res_get.json()
    ver = inv["version"]
    act_id = inv["actions"][0]["id"]

    # Accept plan
    res_acc = await client.post(
        f"/investigations/{inv_id}/accept",
        json={"expected_version": ver},
        headers={**headers, "Idempotency-Key": f"acc-{uuid4()}"},
    )
    assert res_acc.status_code == 200
    inv_acc = res_acc.json()
    accepted_ver = inv_acc["version"]

    # 1. VERSION_CONFLICT on update_action with wrong version
    res_conflict = await client.patch(
        f"/investigations/{inv_id}/actions/{act_id}",
        json={"expected_version": 999, "status": "CLAIMED_DONE"},
        headers=headers,
    )
    assert res_conflict.status_code == 409
    assert res_conflict.json()["code"] == "VERSION_CONFLICT"

    # 2. INVALID_ACTION_STATUS on update_action with status other than CLAIMED_DONE
    res_bad_status = await client.patch(
        f"/investigations/{inv_id}/actions/{act_id}",
        json={"expected_version": accepted_ver, "status": "OPEN"},
        headers=headers,
    )
    assert res_bad_status.status_code == 422
    assert res_bad_status.json()["code"] == "INVALID_ACTION_STATUS"


@pytest.mark.asyncio
async def test_ac16_invalid_state_on_dismiss_terminal(
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
        json={"store_id": str(sample_store.id), "notes": "Dismiss terminal test"},
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
    res_get = await client.get(f"/investigations/{inv_id}", headers=headers)
    inv = res_get.json()
    ver = inv["version"]

    # First dismissal succeeds
    res_dis = await client.post(
        f"/investigations/{inv_id}/dismiss",
        json={"expected_version": ver, "reason": "First dismissal"},
        headers={**headers, "Idempotency-Key": f"dis-{uuid4()}"},
    )
    assert res_dis.status_code == 200
    assert res_dis.json()["state"] == "DISMISSED"

    # Second dismissal on already terminal investigation returns 409 INVALID_STATE
    res_dis_2 = await client.post(
        f"/investigations/{inv_id}/dismiss",
        json={
            "expected_version": res_dis.json()["version"],
            "reason": "Second dismissal",
        },
        headers={**headers, "Idempotency-Key": f"dis2-{uuid4()}"},
    )
    assert res_dis_2.status_code == 409
    assert res_dis_2.json()["code"] == "INVALID_STATE"
