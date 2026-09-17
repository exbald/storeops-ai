"""AC18: Aggregate derivation order, inconclusive/partial handling, and no false pass or closure."""

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from storeops_contracts.models import (
    Action,
    Investigation,
    Outcome,
    PolicyVersion,
    Product,
    Promotion,
    State,
    Status5,
    Status6,
    Store,
    Visit,
)

from apps.api.ai.gateway import DeterministicModelGateway
from apps.api.ai.schemas import (
    Detection,
    ImageObservation,
    ProposedCheck,
    VerificationProposal,
)
from apps.api.core.auth import UserContext
from apps.api.modules.verification.dependencies import set_model_gateway
from apps.api.modules.verification.repository import InMemoryVerificationRepository
from apps.api.modules.visits.repository import InMemoryVisitRepository
from tests.verification.conftest import FrozenClock


@pytest.mark.asyncio
async def test_ac18_any_unknown_derives_inconclusive_and_does_not_close(
    test_workspace_id: UUID,
    rep_user: UserContext,
    sample_visit: Visit,
    sample_store: Store,
    sample_promotion_and_policy: tuple[Promotion, PolicyVersion],
    sample_investigation_accepted: tuple[Investigation, list[Action]],
    frozen_clock: FrozenClock,
    memory_visit_repo: InMemoryVisitRepository,
    memory_verification_repo: InMemoryVerificationRepository,
    auth_headers: dict[str, str],
    make_after_media: Any,
    client: AsyncClient,
) -> None:
    """AC18: If any check is UNKNOWN (e.g. occlusion, partial zone, ambiguous SKU), aggregate is INCONCLUSIVE.

    Visit remains OPEN, investigation returns to NEEDS_WORK, actions NOT verified.
    """
    inv, actions = sample_investigation_accepted
    _promo, pol_ver = sample_promotion_and_policy
    now = frozen_clock.now_utc()

    media = await make_after_media(
        sha256="4" * 64,
        filename="after4.jpg",
        zone_id="zone-shelf-1",
        captured_at=now - timedelta(minutes=3),
    )

    # Rule 1: PASS, Rule 2: UNKNOWN (occluded/ambiguous)
    r1, r2 = pol_ver.rules
    custom_checks = [
        ProposedCheck(
            rule_id=r1.rule_id,
            result="PASS",
            evidence_ids=[media.id],
            explanation="Shelf facings restored to 3.",
        ),
        ProposedCheck(
            rule_id=r2.rule_id,
            result="UNKNOWN",
            evidence_ids=[media.id],
            explanation="Endcap zone obstructed by customer cart; unable to verify display.",
        ),
    ]
    gateway = DeterministicModelGateway()
    gateway.register_response(
        VerificationProposal,
        VerificationProposal(
            checks=custom_checks,
            requested_retakes=["Retake endcap zone with unobstructed view."],
        ),
    )
    set_model_gateway(gateway)

    resp = await client.post(
        f"/investigations/{inv.id}/verify",
        json={
            "expected_version": inv.version,
            "after_media_ids": [str(media.id)],
        },
        headers={**auth_headers, "Idempotency-Key": "idem-ac18-inconclusive"},
    )
    assert resp.status_code == 202

    list_resp = await client.get(
        f"/investigations/{inv.id}/verifications",
        headers=auth_headers,
    )
    assert list_resp.status_code == 200
    v_data = list_resp.json()["items"][0]

    # Aggregate must strictly be INCONCLUSIVE
    assert v_data["result"] == "INCONCLUSIVE"
    assert len(v_data["requested_retakes"]) == 1
    assert "Retake endcap" in v_data["requested_retakes"][0]

    # Investigation set to NEEDS_WORK, NOT RESOLVED
    updated_inv = await memory_visit_repo.get_investigation(test_workspace_id, inv.id)
    assert updated_inv is not None
    assert updated_inv.state == State.NEEDS_WORK

    # Visit remains OPEN, NOT CLOSED
    updated_visit = await memory_visit_repo.get_visit(test_workspace_id, sample_visit.id)
    assert updated_visit is not None
    assert updated_visit.status == Status5.OPEN

    # Actions remain CLAIMED_DONE, NOT VERIFIED
    assert len(updated_inv.actions) == len(actions)
    for act in updated_inv.actions:
        assert act.status == Status6.CLAIMED_DONE

    # Report outcome is INCONCLUSIVE
    assert v_data["report_id"] is not None
    report = await memory_visit_repo.get_report(
        test_workspace_id, UUID(v_data["report_id"])
    )
    assert report is not None
    assert report.outcome == Outcome.INCONCLUSIVE


@pytest.mark.asyncio
async def test_ac18_all_fail_derives_fail(
    test_workspace_id: UUID,
    rep_user: UserContext,
    sample_visit: Visit,
    sample_store: Store,
    sample_promotion_and_policy: tuple[Promotion, PolicyVersion],
    sample_investigation_accepted: tuple[Investigation, list[Action]],
    frozen_clock: FrozenClock,
    memory_visit_repo: InMemoryVisitRepository,
    memory_verification_repo: InMemoryVerificationRepository,
    auth_headers: dict[str, str],
    make_after_media: Any,
    client: AsyncClient,
) -> None:
    """AC18: If all checks are FAIL, aggregate is FAIL.

    Investigation returns to NEEDS_WORK, visit remains OPEN, actions remain unverified.
    """
    inv, _actions = sample_investigation_accepted
    _promo, pol_ver = sample_promotion_and_policy
    now = frozen_clock.now_utc()

    media = await make_after_media(
        sha256="5" * 64,
        filename="after5.jpg",
        captured_at=now - timedelta(minutes=4),
    )

    r1, r2 = pol_ver.rules
    custom_checks = [
        ProposedCheck(
            rule_id=r1.rule_id,
            result="FAIL",
            evidence_ids=[media.id],
            explanation="Only 1 facing observed, 3 required.",
        ),
        ProposedCheck(
            rule_id=r2.rule_id,
            result="FAIL",
            evidence_ids=[media.id],
            explanation="Endcap display completely absent.",
        ),
    ]
    gateway = DeterministicModelGateway()
    gateway.register_response(
        VerificationProposal,
        VerificationProposal(checks=custom_checks, requested_retakes=[]),
    )
    set_model_gateway(gateway)

    resp = await client.post(
        f"/investigations/{inv.id}/verify",
        json={
            "expected_version": inv.version,
            "after_media_ids": [str(media.id)],
        },
        headers={**auth_headers, "Idempotency-Key": "idem-ac18-fail"},
    )
    assert resp.status_code == 202

    list_resp = await client.get(
        f"/investigations/{inv.id}/verifications",
        headers=auth_headers,
    )
    assert list_resp.status_code == 200
    v_data = list_resp.json()["items"][0]
    assert v_data["result"] == "FAIL"

    updated_inv = await memory_visit_repo.get_investigation(test_workspace_id, inv.id)
    assert updated_inv is not None
    assert updated_inv.state == State.NEEDS_WORK

    updated_visit = await memory_visit_repo.get_visit(test_workspace_id, sample_visit.id)
    assert updated_visit is not None
    assert updated_visit.status == Status5.OPEN

    report = await memory_visit_repo.get_report(
        test_workspace_id, UUID(v_data["report_id"])
    )
    assert report is not None
    assert report.outcome == Outcome.FAIL


@pytest.mark.asyncio
async def test_ac18_mixed_pass_fail_derives_partial(
    test_workspace_id: UUID,
    rep_user: UserContext,
    sample_visit: Visit,
    sample_store: Store,
    sample_product: Product,
    sample_promotion_and_policy: tuple[Promotion, PolicyVersion],
    sample_investigation_accepted: tuple[Investigation, list[Action]],
    frozen_clock: FrozenClock,
    memory_visit_repo: InMemoryVisitRepository,
    memory_verification_repo: InMemoryVerificationRepository,
    auth_headers: dict[str, str],
    make_after_media: Any,
    client: AsyncClient,
) -> None:
    """AC18: If some PASS and some FAIL (without UNKNOWN), aggregate is PARTIAL.

    Investigation returns to NEEDS_WORK, visit remains OPEN, actions remain unverified.
    """
    inv, _actions = sample_investigation_accepted
    _promo, pol_ver = sample_promotion_and_policy
    now = frozen_clock.now_utc()

    media = await make_after_media(
        sha256="6" * 64,
        filename="after6.jpg",
        zone_id="zone-shelf-1",
        captured_at=now - timedelta(minutes=4),
    )

    r1, r2 = pol_ver.rules
    custom_checks = [
        ProposedCheck(
            rule_id=r1.rule_id,
            result="PASS",
            evidence_ids=[media.id],
            explanation="Facings compliant.",
        ),
        ProposedCheck(
            rule_id=r2.rule_id,
            result="FAIL",
            evidence_ids=[media.id],
            explanation="Display missing.",
        ),
    ]
    obs_shelf = ImageObservation(
        media_id=media.id,
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

    gateway = DeterministicModelGateway()
    gateway.register_response(ImageObservation, obs_shelf)
    gateway.register_response(
        VerificationProposal,
        VerificationProposal(checks=custom_checks, requested_retakes=[]),
    )
    set_model_gateway(gateway)

    resp = await client.post(
        f"/investigations/{inv.id}/verify",
        json={
            "expected_version": inv.version,
            "after_media_ids": [str(media.id)],
        },
        headers={**auth_headers, "Idempotency-Key": "idem-ac18-partial"},
    )
    assert resp.status_code == 202

    list_resp = await client.get(
        f"/investigations/{inv.id}/verifications",
        headers=auth_headers,
    )
    assert list_resp.status_code == 200
    v_data = list_resp.json()["items"][0]
    assert v_data["result"] == "PARTIAL"

    updated_inv = await memory_visit_repo.get_investigation(test_workspace_id, inv.id)
    assert updated_inv is not None
    assert updated_inv.state == State.NEEDS_WORK

    report = await memory_visit_repo.get_report(
        test_workspace_id, UUID(v_data["report_id"])
    )
    assert report is not None
    assert report.outcome == Outcome.PARTIAL
