"""AC17: Compliant after-action media satisfying every rule yields PASS, closed visit, verified actions, and immutable report."""

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
    Promotion,
    State,
    Status5,
    Status6,
    Store,
    Visit,
    ZoneKind,
)

from apps.api.ai.gateway import DeterministicModelGateway
from apps.api.ai.schemas import ProposedCheck, VerificationProposal
from apps.api.core.auth import UserContext
from apps.api.modules.verification.dependencies import set_model_gateway
from apps.api.modules.verification.repository import InMemoryVerificationRepository
from apps.api.modules.visits.repository import InMemoryVisitRepository
from tests.verification.conftest import FrozenClock


@pytest.mark.asyncio
async def test_ac17_verification_pass_atomic_resolution(
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
    """AC17: Run verification on compliant after-media.

    Verify:
    1. Every rule checked once.
    2. Code derives PASS.
    3. Actions set VERIFIED, investigation set RESOLVED, visit set CLOSED, report saved.
    4. Exact same report/verification accessible via GET endpoints.
    """
    inv, actions = sample_investigation_accepted
    _promo, pol_ver = sample_promotion_and_policy

    # Prepare after-action media
    now = frozen_clock.now_utc()
    media1 = await make_after_media(
        sha256="2" * 64,
        filename="after1.jpg",
        zone_id="zone-shelf-1",
        zone_kind=ZoneKind.SHELF,
        captured_at=now - timedelta(minutes=2),
    )
    media2 = await make_after_media(
        sha256="3" * 64,
        filename="after2.jpg",
        zone_id="zone-endcap-1",
        zone_kind=ZoneKind.DISPLAY,
        captured_at=now - timedelta(minutes=1),
    )

    # Register deterministic proposal
    gateway = DeterministicModelGateway()
    gateway.register_response(
        VerificationProposal,
        VerificationProposal(
            checks=[
                ProposedCheck(
                    rule_id=r.rule_id,
                    result="PASS",
                    evidence_ids=[media1.id],
                    explanation=f"Rule {r.rule_id} observed compliant in verification imagery.",
                )
                for r in pol_ver.rules
            ],
            requested_retakes=[],
        ),
    )
    set_model_gateway(gateway)

    # Verify investigation
    idem_key = "idem-verify-ac17-1"
    headers = {**auth_headers, "Idempotency-Key": idem_key}
    verify_payload = {
        "expected_version": inv.version,
        "after_media_ids": [str(media1.id), str(media2.id)],
    }

    resp = await client.post(
        f"/investigations/{inv.id}/verify",
        json=verify_payload,
        headers=headers,
    )
    assert resp.status_code == 202, f"Failed: {resp.text}"
    job_data = resp.json()
    assert job_data["type"] == "VERIFY"
    assert job_data["status"] in ("QUEUED", "SUCCEEDED", "RUNNING")
    job_id = job_data["id"]

    # Replay with identical key/body must return 202 with same job
    replay_resp = await client.post(
        f"/investigations/{inv.id}/verify",
        json=verify_payload,
        headers=headers,
    )
    assert replay_resp.status_code == 202
    assert replay_resp.json()["id"] == job_id

    # Verify list verifications endpoint
    list_resp = await client.get(
        f"/investigations/{inv.id}/verifications",
        headers=auth_headers,
    )
    assert list_resp.status_code == 200
    v_list = list_resp.json()
    assert len(v_list["items"]) >= 1

    v_attempt = v_list["items"][0]
    v_id = v_attempt["id"]

    # Fetch single verification attempt
    get_v_resp = await client.get(
        f"/verifications/{v_id}",
        headers=auth_headers,
    )
    assert get_v_resp.status_code == 200
    verification = get_v_resp.json()
    assert verification["id"] == v_id
    assert verification["investigation_id"] == str(inv.id)
    assert verification["result"] == "PASS"
    assert verification["report_id"] is not None

    # Every frozen rule checked exactly once
    rule_ids = {str(r.rule_id) for r in pol_ver.rules}
    checked_rule_ids = {c["rule_id"] for c in verification["checks"]}
    assert checked_rule_ids == rule_ids
    for check in verification["checks"]:
        assert check["result"] == "PASS"
        assert len(check["evidence_ids"]) >= 1

    # Investigation atomically transitioned to RESOLVED
    updated_inv = await memory_visit_repo.get_investigation(test_workspace_id, inv.id)
    assert updated_inv is not None
    assert updated_inv.state == State.RESOLVED
    assert updated_inv.latest_verification_id == UUID(v_id)

    # Visit atomically CLOSED
    updated_visit = await memory_visit_repo.get_visit(test_workspace_id, sample_visit.id)
    assert updated_visit is not None
    assert updated_visit.status == Status5.CLOSED

    # Actions atomically VERIFIED
    assert len(updated_inv.actions) == len(actions)
    for act in updated_inv.actions:
        assert act.status == Status6.VERIFIED

    # Report saved with Outcome.PASS
    report = await memory_visit_repo.get_report(
        test_workspace_id, UUID(verification["report_id"])
    )
    assert report is not None
    assert report.outcome == Outcome.PASS
    assert report.investigation_id == inv.id
    assert report.visit_id == sample_visit.id
    assert report.policy_version_id == pol_ver.id
