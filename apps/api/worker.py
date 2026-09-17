import asyncio
import logging
import os
from uuid import UUID

from apps.api.adapters.state.firestore import FirestoreStateRepository
from apps.api.adapters.state.in_memory import InMemoryStateRepository
from apps.api.core.config import settings
from apps.api.jobs.runner import JobRunner
from apps.api.ports.state import StateRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("storeops.worker")


def create_worker(state_repo: StateRepository | None = None) -> tuple[StateRepository, JobRunner]:
    if state_repo is None:
        if settings.state_backend == "firestore":
            state_repo = FirestoreStateRepository()
        else:
            state_repo = InMemoryStateRepository()

    runner = JobRunner(state_repo=state_repo, worker_id=f"worker-{os.getpid()}")

    # Register test handler for AC37
    async def _test_handler(job, generation):
        logger.info("Executing test job %s at generation %s", job.id, generation)
        await asyncio.sleep(0.01)

    runner.register_handler("TEST", _test_handler)
    return state_repo, runner


async def drain_outbox(state_repo: StateRepository, runner: JobRunner) -> int:
    """Drain undispatched outbox items, executing each job via the runner.

    Supports both InMemoryStateRepository (LOCAL profile) and FirestoreStateRepository (CLOUD profile).
    Entries are only marked as dispatched after successful execution, guaranteeing no lost jobs on crash.
    """
    dispatched_count = 0

    # CLOUD / Firestore path
    if isinstance(state_repo, FirestoreStateRepository):
        try:
            outbox_ref = (
                state_repo.db.collection("outbox")
                .where("dispatched", "==", False)
                .order_by("created_at", direction="ASCENDING")
            )
            async for doc in outbox_ref.stream():
                data = doc.to_dict()
                ws_id = UUID(str(data["workspace_id"]))
                job_id = UUID(str(data["job_id"]))
                success = await runner.execute_job(ws_id, job_id)
                if success:
                    await doc.reference.update({"dispatched": True})
                    dispatched_count += 1
        except Exception:
            logger.exception(
                "Firestore outbox drain encountered error (dispatched_so_far=%d)",
                dispatched_count,
            )

    # LOCAL / InMemory path
    elif isinstance(state_repo, InMemoryStateRepository) or isinstance(getattr(state_repo, "outbox", None), list):
        for entry in list(state_repo.outbox):
            if not entry.get("dispatched"):
                success = await runner.execute_job(
                    UUID(str(entry["workspace_id"])), UUID(str(entry["job_id"]))
                )
                if success:
                    entry["dispatched"] = True
                    dispatched_count += 1
    else:
        logger.warning(
            "drain_outbox: Unrecognized state_repo type '%s', 0 items drained",
            type(state_repo).__name__,
        )

    return dispatched_count


async def run_worker_loop():
    logger.info("Starting StoreOps worker process (profile=%s)...", settings.profile)
    state_repo, runner = create_worker()
    while True:
        await drain_outbox(state_repo, runner)
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(run_worker_loop())
