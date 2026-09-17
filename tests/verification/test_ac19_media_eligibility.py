"""AC19: Ineligible after-media rejection: reused before-image hash, stale/future timestamp, and bad scope."""

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from storeops_contracts.models import (
    Action,
    Investigation,
    Media,
    PolicyVersion,
    Promotion,
    Store,
    Visit,
)

from apps.api.core.auth import UserContext
from apps.api.modules.catalog.repository import InMemoryCatalogRepository
from tests.verification.conftest import FrozenClock


@pytest.mark.asyncio
async def test_ac19_reject_reused_before_image_hash(
    test_workspace_id: UUID,
    rep_user: UserContext,
    sample_visit: Visit,
    sample_store: Store,
    sample_before_media: Media,
    sample_promotion_and_policy: tuple[Promotion, PolicyVersion],
    sample_investigation_accepted: tuple[Investigation, list[Action]],
    frozen_clock: FrozenClock,
    auth_headers: dict[str, str],
    make_after_media: Any,
    client: AsyncClient,
) -> None:
    """AC19: Reusing a before-image normalized hash must be rejected."""
    inv, _ = sample_investigation_accepted
    now = frozen_clock.now_utc()

    # Reused media has the exact same normalized_sha256 as sample_before_media
    reused_media = await make_after_media(
        sha256=sample_before_media.normalized_sha256,
        filename="reused.jpg",
        captured_at=now - timedelta(minutes=5),
    )

    resp = await client.post(
        f"/investigations/{inv.id}/verify",
        json={
            "expected_version": inv.version,
            "after_media_ids": [str(reused_media.id)],
        },
        headers={**auth_headers, "Idempotency-Key": "idem-ac19-reused"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "REUSED_BEFORE_MEDIA"


@pytest.mark.asyncio
async def test_ac19_reject_media_older_than_30_minutes(
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
    """AC19: Media capture older than 30 minutes relative to server Clock must be rejected."""
    inv, _ = sample_investigation_accepted
    now = frozen_clock.now_utc()

    old_media = await make_after_media(
        sha256="7" * 64,
        filename="old.jpg",
        captured_at=now - timedelta(minutes=35),  # > 30 minutes!
    )

    resp = await client.post(
        f"/investigations/{inv.id}/verify",
        json={
            "expected_version": inv.version,
            "after_media_ids": [str(old_media.id)],
        },
        headers={**auth_headers, "Idempotency-Key": "idem-ac19-old"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "MEDIA_TOO_OLD"


@pytest.mark.asyncio
async def test_ac19_reject_media_future_dated(
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
    """AC19: Media capture more than 5 minutes in the future relative to server Clock must be rejected."""
    inv, _ = sample_investigation_accepted
    now = frozen_clock.now_utc()

    future_media = await make_after_media(
        sha256="8" * 64,
        filename="future.jpg",
        captured_at=now + timedelta(minutes=6),  # > 5 minutes in the future!
    )

    resp = await client.post(
        f"/investigations/{inv.id}/verify",
        json={
            "expected_version": inv.version,
            "after_media_ids": [str(future_media.id)],
        },
        headers={**auth_headers, "Idempotency-Key": "idem-ac19-future"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "MEDIA_FUTURE_DATED"


@pytest.mark.asyncio
async def test_ac19_reject_media_unbound_or_wrong_visit(
    test_workspace_id: UUID,
    rep_user: UserContext,
    sample_visit: Visit,
    sample_store: Store,
    sample_promotion_and_policy: tuple[Promotion, PolicyVersion],
    sample_investigation_accepted: tuple[Investigation, list[Action]],
    frozen_clock: FrozenClock,
    memory_catalog_repo: InMemoryCatalogRepository,
    auth_headers: dict[str, str],
    make_after_media: Any,
    client: AsyncClient,
) -> None:
    """AC19: Media not bound to the current visit or store must be rejected."""
    inv, _ = sample_investigation_accepted
    now = frozen_clock.now_utc()

    unbound_media = await make_after_media(
        sha256="9" * 64,
        filename="unbound.jpg",
        captured_at=now - timedelta(minutes=2),
    )
    unbound_media.visit_id = uuid4()
    await memory_catalog_repo.update_media(unbound_media)

    resp = await client.post(
        f"/investigations/{inv.id}/verify",
        json={
            "expected_version": inv.version,
            "after_media_ids": [str(unbound_media.id)],
        },
        headers={**auth_headers, "Idempotency-Key": "idem-ac19-unbound"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "MEDIA_NOT_BOUND_TO_VISIT"
