"""AC20: Concurrency, OCC fencing, idempotency replay/conflict, and state guards."""

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from storeops_contracts.models import (
    Action,
    Investigation,
    PolicyVersion,
    Product,
    Promotion,
    State,
    Store,
    Visit,
    ZoneKind,
)

from apps.api.ai.schemas import (
    Detection,
    ImageObservation,
    ProposedCheck,
    VerificationProposal,
)
from apps.api.core.auth import UserContext
from apps.api.modules.verification.dependencies import set_model_gateway
from apps.api.modules.visits.repository import InMemoryVisitRepository
from tests.verification.conftest import (
    FrozenClock,
    ScenarioModelGateway,
)


@pytest.mark.asyncio
async def test_ac20_occ_stale_version_returns_409(
    test_workspace_id: UUID,
    rep_user: UserContext,
    sample_visit: Visit,
    sample_store: Store,
    sample_promotion_and_policy: tuple[Promotion, PolicyVersion],
    sample_investigation_accepted: tuple[Investigation, list[Action]],
    frozen_clock: FrozenClock,
    auth_headers: dict[str, str],
    make_after_media: Any,
    client: AsyncClient,
) -> None:
    """AC20: Submitting stale expected_version returns 409 VERSION_CONFLICT."""
    inv, _ = sample_investigation_accepted
    now = frozen_clock.now_utc()

    media = await make_after_media(
        sha256="a" * 64,
        filename="ma.jpg",
        captured_at=now - timedelta(minutes=2),
    )

    # Send expected_version = inv.version + 99 (stale / wrong)
    resp = await client.post(
        f"/investigations/{inv.id}/verify",
        json={
            "expected_version": inv.version + 99,
            "after_media_ids": [str(media.id)],
        },
        headers={**auth_headers, "Idempotency-Key": "idem-ac20-stale-ver"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "VERSION_CONFLICT"


@pytest.mark.asyncio
async def test_ac20_idempotency_conflict_returns_409(
    test_workspace_id: UUID,
    rep_user: UserContext,
    sample_visit: Visit,
    sample_store: Store,
    sample_promotion_and_policy: tuple[Promotion, PolicyVersion],
    sample_investigation_accepted: tuple[Investigation, list[Action]],
    frozen_clock: FrozenClock,
    auth_headers: dict[str, str],
    make_after_media: Any,
    client: AsyncClient,
) -> None:
    """AC20: Same Idempotency-Key with altered body returns 409 IDEMPOTENCY_CONFLICT."""
    inv, _ = sample_investigation_accepted
    now = frozen_clock.now_utc()

    media1 = await make_after_media(
        sha256="b" * 64,
        filename="mb.jpg",
        captured_at=now - timedelta(minutes=2),
    )
    media2 = await make_after_media(
        sha256="c" * 64,
        filename="mc.jpg",
        captured_at=now - timedelta(minutes=2),
    )

    key = "idem-conflict-test-key"
    resp1 = await client.post(
        f"/investigations/{inv.id}/verify",
        json={
            "expected_version": inv.version,
            "after_media_ids": [str(media1.id)],
        },
        headers={**auth_headers, "Idempotency-Key": key},
    )
    assert resp1.status_code == 202

    # Now send same key with altered payload (different after_media_ids)
    resp2 = await client.post(
        f"/investigations/{inv.id}/verify",
        json={
            "expected_version": inv.version,
            "after_media_ids": [str(media2.id)],
        },
        headers={**auth_headers, "Idempotency-Key": key},
    )
    assert resp2.status_code == 409
    assert resp2.json()["code"] == "IDEMPOTENCY_KEY_MISMATCH"


@pytest.mark.asyncio
async def test_ac20_unsupported_state_returns_409(
    test_workspace_id: UUID,
    rep_user: UserContext,
    sample_visit: Visit,
    sample_store: Store,
    sample_promotion_and_policy: tuple[Promotion, PolicyVersion],
    sample_investigation_accepted: tuple[Investigation, list[Action]],
    frozen_clock: FrozenClock,
    memory_visit_repo: InMemoryVisitRepository,
    auth_headers: dict[str, str],
    make_after_media: Any,
    client: AsyncClient,
) -> None:
    """AC20: Verifying an investigation that is not in ACCEPTED or NEEDS_WORK returns 409."""
    inv, _ = sample_investigation_accepted
    now = frozen_clock.now_utc()

    # Move investigation to DISMISSED
    inv.state = State.DISMISSED
    inv.version += 1
    await memory_visit_repo.update_investigation(test_workspace_id, inv)

    media = await make_after_media(
        sha256="d" * 64,
        filename="md.jpg",
        captured_at=now - timedelta(minutes=2),
    )

    resp = await client.post(
        f"/investigations/{inv.id}/verify",
        json={
            "expected_version": inv.version,
            "after_media_ids": [str(media.id)],
        },
        headers={**auth_headers, "Idempotency-Key": "idem-ac20-dismissed"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "INVALID_STATE"


@pytest.mark.asyncio
async def test_saga_compensation_on_visit_update_failure(
    test_workspace_id: UUID,
    rep_user: UserContext,
    sample_visit: Visit,
    sample_store: Store,
    sample_product: Product,
    sample_promotion_and_policy: tuple[Promotion, PolicyVersion],
    sample_investigation_accepted: tuple[Investigation, list[Action]],
    frozen_clock: FrozenClock,
    memory_visit_repo: InMemoryVisitRepository,
    auth_headers: dict[str, str],
    make_after_media: Any,
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC20/Saga: If visit update fails during saga-coordinated PASS resolution, compensation rolls back investigation."""
    inv, _actions = sample_investigation_accepted
    _promo, pol_ver = sample_promotion_and_policy
    now = frozen_clock.now_utc()

    media1 = await make_after_media(
        sha256="e" * 64,
        filename="me1.jpg",
        zone_id="zone-shelf-1",
        zone_kind=ZoneKind.SHELF,
        captured_at=now - timedelta(minutes=2),
    )
    media2 = await make_after_media(
        sha256="f" * 64,
        filename="me2.jpg",
        zone_id="zone-endcap-1",
        zone_kind=ZoneKind.DISPLAY,
        captured_at=now - timedelta(minutes=1),
    )

    obs_shelf = ImageObservation(
        media_id=media1.id,
        zone_id="zone-shelf-1",
        zone_kind="SHELF",
        quality="CLEAR",
        coverage="FULL",
        occluded=False,
        detections=[
            Detection(
                product_id=sample_product.id,
                identity="CLEAR",
                view="FRONT",
                box=[100, 100, 400, 400],
                label="Sea Salt Chips 150g",
            )
            for _ in range(3)
        ],
        display="UNKNOWN",
        limitations=[],
    )
    obs_endcap = ImageObservation(
        media_id=media2.id,
        zone_id="zone-endcap-1",
        zone_kind="DISPLAY",
        quality="CLEAR",
        coverage="FULL",
        occluded=False,
        detections=[],
        display="PRESENT",
        limitations=[],
    )

    gateway = ScenarioModelGateway()
    gateway.register_queue(ImageObservation, [obs_shelf, obs_endcap])
    gateway.register_response(
        VerificationProposal,
        VerificationProposal(
            checks=[
                ProposedCheck(
                    rule_id=pol_ver.rules[0].rule_id,
                    result="PASS",
                    evidence_ids=[media1.id],
                    explanation=f"Compliant {pol_ver.rules[0].rule_id}",
                ),
                ProposedCheck(
                    rule_id=pol_ver.rules[1].rule_id,
                    result="PASS",
                    evidence_ids=[media2.id],
                    explanation=f"Compliant {pol_ver.rules[1].rule_id}",
                ),
            ],
            requested_retakes=[],
        ),
    )
    set_model_gateway(gateway)

    call_count = 0
    orig_update_visit = memory_visit_repo.update_visit

    async def fail_first_update_visit(workspace_id: UUID, visit: Visit) -> Visit:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Simulated DB connection timeout on visit update")
        return await orig_update_visit(workspace_id, visit)

    monkeypatch.setattr(memory_visit_repo, "update_visit", fail_first_update_visit)

    resp = await client.post(
        f"/investigations/{inv.id}/verify",
        json={
            "expected_version": inv.version,
            "after_media_ids": [str(media1.id), str(media2.id)],
        },
        headers={**auth_headers, "Idempotency-Key": "idem-saga-fail"},
    )
    assert resp.status_code == 202

    # After saga rollback compensation, investigation state must be in NEEDS_WORK (not stuck in VERIFYING or RESOLVED)
    persisted_inv = await memory_visit_repo.get_investigation(test_workspace_id, inv.id)
    assert persisted_inv is not None
    assert persisted_inv.state == State.NEEDS_WORK
    assert persisted_inv.state != State.RESOLVED

    # Verification must have terminal INCONCLUSIVE result
    v_id = resp.json()["resource_id"]
    ver_resp = await client.get(
        f"/verifications/{v_id}",
        headers=auth_headers,
    )
    assert ver_resp.status_code == 200
    assert ver_resp.json()["result"] == "INCONCLUSIVE"


@pytest.mark.asyncio
async def test_non_pass_cascade_compensation_restores_needs_work_and_allows_retry(
    test_workspace_id: UUID,
    rep_user: UserContext,
    sample_visit: Visit,
    sample_store: Store,
    sample_product: Product,
    sample_promotion_and_policy: tuple[Promotion, PolicyVersion],
    sample_investigation_accepted: tuple[Investigation, list[Action]],
    frozen_clock: FrozenClock,
    memory_visit_repo: InMemoryVisitRepository,
    auth_headers: dict[str, str],
    make_after_media: Any,
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-PASS cascade failure compensates cleanly to NEEDS_WORK with INCONCLUSIVE and allows re-verify."""
    inv, _actions = sample_investigation_accepted
    _, pol_ver = sample_promotion_and_policy
    now = frozen_clock.now_utc()

    media = await make_after_media(
        sha256="e" * 64,
        filename="me.jpg",
        captured_at=now - timedelta(minutes=2),
    )

    # Register FAIL proposal
    gateway = ScenarioModelGateway()
    gateway.register_response(
        VerificationProposal,
        VerificationProposal(
            checks=[
                ProposedCheck(
                    rule_id=pol_ver.rules[0].rule_id,
                    result="FAIL",
                    evidence_ids=[media.id],
                    explanation="Rule violated",
                ),
            ],
            requested_retakes=[],
        ),
    )
    set_model_gateway(gateway)

    call_count = 0
    orig_update_inv = memory_visit_repo.update_investigation

    async def fail_second_update_inv(
        workspace_id: UUID, investigation: Investigation
    ) -> Investigation:
        nonlocal call_count
        call_count += 1
        # Call 1 is verify_investigation entering VERIFYING
        # Call 2 is non-PASS cascade step 2 transitioning to NEEDS_WORK
        if call_count == 2:
            raise RuntimeError("Simulated DB timeout on non-PASS investigation update")
        return await orig_update_inv(workspace_id, investigation)

    monkeypatch.setattr(
        memory_visit_repo, "update_investigation", fail_second_update_inv
    )

    resp = await client.post(
        f"/investigations/{inv.id}/verify",
        json={
            "expected_version": inv.version,
            "after_media_ids": [str(media.id)],
        },
        headers={**auth_headers, "Idempotency-Key": "idem-nonpass-fail"},
    )
    assert resp.status_code == 202
    v_id = resp.json()["resource_id"]

    # Investigation must be in NEEDS_WORK (not VERIFYING!)
    persisted_inv = await memory_visit_repo.get_investigation(test_workspace_id, inv.id)
    assert persisted_inv is not None
    assert persisted_inv.state == State.NEEDS_WORK

    # Verification must have terminal INCONCLUSIVE result
    ver_resp = await client.get(
        f"/verifications/{v_id}",
        headers=auth_headers,
    )
    assert ver_resp.status_code == 200
    assert ver_resp.json()["result"] == "INCONCLUSIVE"

    # Retry via POST verifyInvestigation must not be blocked (SEMANTICS.md:88)
    retry_resp = await client.post(
        f"/investigations/{inv.id}/verify",
        json={
            "expected_version": persisted_inv.version,
            "after_media_ids": [str(media.id)],
        },
        headers={**auth_headers, "Idempotency-Key": "idem-nonpass-retry"},
    )
    assert retry_resp.status_code == 202
