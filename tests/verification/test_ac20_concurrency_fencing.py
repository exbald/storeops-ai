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
    Promotion,
    State,
    Store,
    Visit,
)

from apps.api.core.auth import UserContext
from apps.api.modules.visits.repository import InMemoryVisitRepository
from tests.verification.conftest import FrozenClock


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
    sample_promotion_and_policy: tuple[Promotion, PolicyVersion],
    sample_investigation_accepted: tuple[Investigation, list[Action]],
    frozen_clock: FrozenClock,
    memory_visit_repo: InMemoryVisitRepository,
    auth_headers: dict[str, str],
    make_after_media: Any,
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC20/Saga: If visit update fails during atomic PASS resolution, compensation rolls back investigation."""
    from apps.api.ai.gateway import DeterministicModelGateway
    from apps.api.ai.schemas import ProposedCheck, VerificationProposal
    from apps.api.modules.verification.dependencies import set_model_gateway

    inv, _actions = sample_investigation_accepted
    _promo, pol_ver = sample_promotion_and_policy
    now = frozen_clock.now_utc()

    media = await make_after_media(
        sha256="e" * 64,
        filename="me.jpg",
        captured_at=now - timedelta(minutes=2),
    )

    gateway = DeterministicModelGateway()
    gateway.register_response(
        VerificationProposal,
        VerificationProposal(
            checks=[
                ProposedCheck(
                    rule_id=r.rule_id,
                    result="PASS",
                    evidence_ids=[media.id],
                    explanation=f"Compliant {r.rule_id}",
                )
                for r in pol_ver.rules
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
            "after_media_ids": [str(media.id)],
        },
        headers={**auth_headers, "Idempotency-Key": "idem-saga-fail"},
    )
    assert resp.status_code == 202

    # After saga rollback compensation, investigation state must NOT be RESOLVED
    persisted_inv = await memory_visit_repo.get_investigation(test_workspace_id, inv.id)
    assert persisted_inv is not None
    assert persisted_inv.state in (State.ACCEPTED, State.NEEDS_WORK)
    assert persisted_inv.state != State.RESOLVED

