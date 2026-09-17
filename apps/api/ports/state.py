from typing import Any, Protocol
from uuid import UUID

from storeops_contracts.models import Job, JobEvent, Membership, Workspace


class VersionConflictError(Exception):
    def __init__(self, message: str = "Resource version conflict", code: str = "VERSION_CONFLICT"):
        super().__init__(message)
        self.message = message
        self.code = code


class StateRepository(Protocol):
    async def get_workspace(self, workspace_id: UUID) -> Workspace | None:
        """Fetch workspace by ID."""
        ...

    async def get_memberships_for_user(self, uid: str) -> list[Membership]:
        """Fetch all workspace memberships for a user UID."""
        ...

    async def get_membership(self, workspace_id: UUID, uid: str) -> Membership | None:
        """Fetch user's membership for a specific workspace."""
        ...

    async def create_workspace_with_admin(
        self, workspace: Workspace, uid: str, email: str | None = None
    ) -> Membership:
        """Atomically create a workspace and an initial ADMIN membership."""
        ...

    async def add_membership(
        self, workspace_id: UUID, uid: str, role: str, email: str | None = None
    ) -> Membership:
        """Add or update a membership in a workspace."""
        ...

    async def get_job(self, workspace_id: UUID, job_id: UUID) -> Job | None:
        """Fetch a job by workspace and job ID."""
        ...

    async def get_job_events(self, workspace_id: UUID, job_id: UUID) -> list[JobEvent]:
        """Fetch ordered events for a job."""
        ...

    async def create_job_with_outbox(
        self, job: Job, outbox_payload: dict[str, Any] | None = None
    ) -> None:
        """Atomically persist a job and enqueue an undispatched outbox entry."""
        ...

    async def acquire_job_lease(
        self, job_id: UUID, worker_id: str, lease_seconds: int = 60
    ) -> int | None:
        """Acquire or extend a lease on a job with fencing generation check.

        Returns the new lease generation, or None if lease is held by another active worker.
        """
        ...

    async def update_job_stage(
        self, job_id: UUID, generation: int, stage: str, status: str, summary: str
    ) -> None:
        """Update job stage/status and append a JobEvent checking the fencing generation."""
        ...

    async def check_idempotency(
        self, uid: str, method: str, route: str, key: str, body_hash: str
    ) -> tuple[bool, dict[str, Any] | None]:
        """Check if request with idempotency key was executed.

        Returns (is_executed, cached_response_data).
        Raises VersionConflictError if same key is used with differing body_hash.
        """
        ...

    async def save_idempotency(
        self,
        uid: str,
        method: str,
        route: str,
        key: str,
        body_hash: str,
        status_code: int,
        response_body: dict[str, Any],
    ) -> None:
        """Save idempotent response associated with request key."""
        ...
