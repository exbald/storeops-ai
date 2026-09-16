from typing import Protocol
from uuid import UUID


class JobDispatcher(Protocol):
    async def enqueue(self, job_id: UUID) -> None:
        """Enqueue job ID for background processing."""
        ...
