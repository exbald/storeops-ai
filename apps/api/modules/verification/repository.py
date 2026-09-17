"""Repository for Verification persistence."""

import base64
import json
from typing import Protocol
from uuid import UUID

from storeops_contracts.models import Verification


class VerificationRepository(Protocol):
    """Protocol for Verification record persistence."""

    async def save_verification(
        self, workspace_id: UUID, verification: Verification
    ) -> Verification: ...

    async def get_verification(
        self, workspace_id: UUID, verification_id: UUID
    ) -> Verification | None: ...

    async def update_verification(
        self, workspace_id: UUID, verification: Verification
    ) -> Verification: ...

    async def list_verifications(
        self,
        workspace_id: UUID,
        investigation_id: UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Verification], str | None]: ...


class InMemoryVerificationRepository:
    """In-memory verification repository for LOCAL profile and unit tests."""

    def __init__(self) -> None:
        # Keyed by (workspace_id, verification_id)
        self._verifications: dict[tuple[UUID, UUID], Verification] = {}

    async def save_verification(
        self, workspace_id: UUID, verification: Verification
    ) -> Verification:
        self._verifications[(workspace_id, verification.id)] = (
            verification.model_copy(deep=True)
        )
        return verification.model_copy(deep=True)

    async def get_verification(
        self, workspace_id: UUID, verification_id: UUID
    ) -> Verification | None:
        v = self._verifications.get((workspace_id, verification_id))
        return v.model_copy(deep=True) if v else None

    async def update_verification(
        self, workspace_id: UUID, verification: Verification
    ) -> Verification:
        self._verifications[(workspace_id, verification.id)] = (
            verification.model_copy(deep=True)
        )
        return verification.model_copy(deep=True)

    async def list_verifications(
        self,
        workspace_id: UUID,
        investigation_id: UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Verification], str | None]:
        # Filter by workspace and investigation
        matched = [
            v
            for (w_id, _), v in self._verifications.items()
            if w_id == workspace_id and v.investigation_id == investigation_id
        ]
        # Sort chronologically by created_at descending, with id as deterministic tie-break per SEMANTICS.md
        matched.sort(key=lambda x: (x.created_at, str(x.id)), reverse=True)

        start_index = 0
        if cursor:
            try:
                decoded = json.loads(
                    base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
                )
                start_index = int(decoded.get("offset", 0))
            except (ValueError, UnicodeDecodeError):
                start_index = 0

        paged = matched[start_index : start_index + limit]
        next_cursor = None
        if start_index + limit < len(matched):
            next_payload = {"offset": start_index + limit}
            next_cursor = base64.urlsafe_b64encode(
                json.dumps(next_payload).encode("utf-8")
            ).decode("utf-8")

        return [v.model_copy(deep=True) for v in paged], next_cursor
