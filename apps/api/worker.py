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

    # Register handlers
    async def _default_handler(job, generation):
        logger.info(
            "Executing job %s (type=%s) at generation %s",
            job.id,
            getattr(job.type, "value", job.type),
            generation,
        )

    for job_type in ["TEST", "INVESTIGATE", "VERIFY", "POLICY_EXTRACT", "IMPORT_VALIDATE", "IMPORT_COMMIT"]:
        runner.register_handler(job_type, _default_handler)

    return state_repo, runner


async def drain_outbox(state_repo: StateRepository, runner: JobRunner) -> int:
    """Drain undispatched outbox items, executing each job via the runner.

    Supports both InMemoryStateRepository (LOCAL profile) and FirestoreStateRepository (CLOUD profile).
    Entries are only marked as dispatched after successful execution, guaranteeing no lost jobs on crash.
    """
    dispatched_count = 0

    # CLOUD / Firestore path
    if isinstance(state_repo, FirestoreStateRepository) or (
        hasattr(state_repo, "db") and state_repo.db is not None and not isinstance(getattr(state_repo, "outbox", None), list)
    ):
        try:
            outbox_ref = (
                state_repo.db.collection("outbox")
                .where("dispatched", "==", False)
                .order_by("created_at")
            )
            async for doc in outbox_ref.stream():
                data = doc.to_dict()
                ws_id = UUID(str(data["workspace_id"]))
                job_id = UUID(str(data["job_id"]))
                success = await runner.execute_job(ws_id, job_id)
                if success:
                    await doc.reference.update({"dispatched": True})
                    dispatched_count += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Firestore outbox drain encountered error: %s", exc)

    # LOCAL / InMemory path
    elif isinstance(getattr(state_repo, "outbox", None), list):
        for entry in list(state_repo.outbox):
            if not entry.get("dispatched"):
                success = await runner.execute_job(
                    UUID(str(entry["workspace_id"])), UUID(str(entry["job_id"]))
                )
                if success:
                    entry["dispatched"] = True
                    dispatched_count += 1

    return dispatched_count


async def run_worker_loop():
    logger.info("Starting StoreOps worker process (profile=%s)...", settings.profile)
    state_repo, runner = create_worker()
    while True:
        await drain_outbox(state_repo, runner)
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(run_worker_loop())
