import logging
from collections.abc import Callable, Coroutine
from typing import Any
from uuid import UUID

from storeops_contracts.models import Job

from apps.api.ports.state import StateRepository, VersionConflictError

logger = logging.getLogger("storeops.worker")


class JobRunner:
    def __init__(self, state_repo: StateRepository, worker_id: str = "worker-1") -> None:
        self.state_repo = state_repo
        self.worker_id = worker_id
        self._handlers: dict[str, Callable[[Job, int], Coroutine[Any, Any, None]]] = {}

    def register_handler(
        self, job_type: str, handler: Callable[[Job, int], Coroutine[Any, Any, None]]
    ) -> None:
        self._handlers[job_type] = handler

    async def execute_job(self, workspace_id: UUID, job_id: UUID) -> bool:
        job = await self.state_repo.get_job(workspace_id, job_id)
        if not job:
            logger.error("Job %s not found in workspace %s", job_id, workspace_id)
            return False

        if job.status.value in ["SUCCEEDED", "FAILED"]:
            logger.info("Job %s already in terminal status %s; skipping", job_id, job.status.value)
            return True

        # Acquire lease with fencing generation
        generation = await self.state_repo.acquire_job_lease(job_id, self.worker_id, lease_seconds=60)
        if generation is None:
            logger.warning("Could not acquire lease for job %s; held by another worker", job_id)
            return False

        handler = self._handlers.get(job.type.value if hasattr(job.type, "value") else str(job.type))
        if not handler:
            await self.state_repo.update_job_stage(
                job_id=job_id,
                generation=generation,
                stage="FAILED",
                status="FAILED",
                summary=f"No handler registered for job type {job.type}",
            )
            return False

        try:
            # Mark RUNNING
            await self.state_repo.update_job_stage(
                job_id=job_id,
                generation=generation,
                stage="RUNNING",
                status="RUNNING",
                summary="Worker claimed job and started processing",
            )
            # Execute handler
            await handler(job, generation)

            # Mark SUCCEEDED
            await self.state_repo.update_job_stage(
                job_id=job_id,
                generation=generation,
                stage="COMPLETED",
                status="SUCCEEDED",
                summary="Job completed successfully",
            )
            return True
        except VersionConflictError as e:
            logger.error("Fencing lease conflict for job %s: %s", job_id, e)
            return False
        except Exception as e:
            logger.exception("Error processing job %s: %s", job_id, e)
            try:
                await self.state_repo.update_job_stage(
                    job_id=job_id,
                    generation=generation,
                    stage="FAILED",
                    status="FAILED",
                    summary=f"Job failed: {e!s}",
                )
            except Exception:
                pass
            return False
