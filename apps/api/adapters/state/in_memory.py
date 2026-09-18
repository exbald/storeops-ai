import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from storeops_contracts import JobStatus
from storeops_contracts.models import Job, JobEvent, Membership, Workspace

from apps.api.ports.state import StateRepository, VersionConflictError


class InMemoryStateRepository(StateRepository):
    def __init__(self, persistence_file: Path | str | None = None) -> None:
        self._lock = asyncio.Lock()
        self.workspaces: dict[UUID, Workspace] = {}
        # List of stored memberships: {workspace_id, uid, role, workspace_name}
        self.memberships: list[dict[str, Any]] = []
        self.jobs: dict[UUID, Job] = {}
        self.job_events: dict[UUID, list[JobEvent]] = {}
        self.job_leases: dict[UUID, dict[str, Any]] = {}
        self.outbox: list[dict[str, Any]] = []
        self.idempotency_records: dict[str, dict[str, Any]] = {}

        if persistence_file:
            self.persistence_file = Path(persistence_file)
        elif os.getenv("PERSIST_LOCAL_STATE") == "1" and not os.getenv("PYTEST_CURRENT_TEST"):
            self.persistence_file = Path(".local_storage/state.json")
        else:
            self.persistence_file = None

        if self.persistence_file and self.persistence_file.exists():
            self._load()

    def _save(self) -> None:
        if not self.persistence_file:
            return
        self.persistence_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "workspaces": {str(k): v.model_dump(mode="json") for k, v in self.workspaces.items()},
            "memberships": [
                {
                    "workspace_id": str(m["workspace_id"]),
                    "workspace_name": m["workspace_name"],
                    "uid": m["uid"],
                    "role": m["role"],
                    "email": m.get("email"),
                }
                for m in self.memberships
            ],
            "jobs": {str(k): v.model_dump(mode="json") for k, v in self.jobs.items()},
            "job_events": {
                str(k): [e.model_dump(mode="json") for e in events]
                for k, events in self.job_events.items()
            },
            "outbox": [
                {
                    **entry,
                    "job_id": str(entry["job_id"]),
                    "workspace_id": str(entry["workspace_id"]),
                }
                for entry in self.outbox
            ],
            "idempotency_records": self.idempotency_records,
        }
        self.persistence_file.write_text(json.dumps(data, indent=2))

    def _load(self) -> None:
        if not self.persistence_file or not self.persistence_file.exists():
            return
        try:
            raw = json.loads(self.persistence_file.read_text())
            for k, v in raw.get("workspaces", {}).items():
                self.workspaces[UUID(k)] = Workspace.model_validate(v)
            self.memberships = [
                {
                    "workspace_id": UUID(m["workspace_id"]),
                    "workspace_name": m["workspace_name"],
                    "uid": m["uid"],
                    "role": m["role"],
                    "email": m.get("email"),
                }
                for m in raw.get("memberships", [])
            ]
            for k, v in raw.get("jobs", {}).items():
                self.jobs[UUID(k)] = Job.model_validate(v)
            for k, v in raw.get("job_events", {}).items():
                self.job_events[UUID(k)] = [JobEvent.model_validate(e) for e in v]
            self.outbox = [
                {
                    **entry,
                    "job_id": UUID(entry["job_id"]),
                    "workspace_id": UUID(entry["workspace_id"]),
                }
                for entry in raw.get("outbox", [])
            ]
            self.idempotency_records = raw.get("idempotency_records", {})
        except Exception:
            pass

    async def get_workspace(self, workspace_id: UUID) -> Workspace | None:
        async with self._lock:
            return self.workspaces.get(workspace_id)

    async def get_memberships_for_user(self, uid: str) -> list[Membership]:
        async with self._lock:
            results: list[Membership] = []
            for m in self.memberships:
                if m["uid"] == uid:
                    results.append(
                        Membership(
                            workspace_id=m["workspace_id"],
                            workspace_name=m["workspace_name"],
                            role=m["role"],
                        )
                    )
            return results

    async def get_membership(self, workspace_id: UUID, uid: str) -> Membership | None:
        async with self._lock:
            for m in self.memberships:
                if m["workspace_id"] == workspace_id and m["uid"] == uid:
                    return Membership(
                        workspace_id=m["workspace_id"],
                        workspace_name=m["workspace_name"],
                        role=m["role"],
                    )
            return None

    async def create_workspace_with_admin(
        self, workspace: Workspace, uid: str, email: str | None = None
    ) -> Membership:
        async with self._lock:
            self.workspaces[workspace.id] = workspace
            membership_dict = {
                "workspace_id": workspace.id,
                "workspace_name": workspace.name,
                "uid": uid,
                "role": "ADMIN",
                "email": email,
            }
            self.memberships.append(membership_dict)
            self._save()
            return Membership(
                workspace_id=workspace.id,
                workspace_name=workspace.name,
                role="ADMIN",
            )

    async def add_membership(
        self, workspace_id: UUID, uid: str, role: str, email: str | None = None
    ) -> Membership:
        async with self._lock:
            ws = self.workspaces.get(workspace_id)
            if not ws:
                raise ValueError(f"Workspace {workspace_id} not found")

            # Check if membership exists
            for m in self.memberships:
                if m["workspace_id"] == workspace_id and m["uid"] == uid:
                    m["role"] = role
                    if email:
                        m["email"] = email
                    self._save()
                    return Membership(
                        workspace_id=workspace_id,
                        workspace_name=ws.name,
                        role=role,
                    )

            # Insert new membership
            self.memberships.append(
                {
                    "workspace_id": workspace_id,
                    "workspace_name": ws.name,
                    "uid": uid,
                    "role": role,
                    "email": email,
                }
            )
            self._save()
            return Membership(
                workspace_id=workspace_id,
                workspace_name=ws.name,
                role=role,
            )

    async def get_job(self, workspace_id: UUID, job_id: UUID) -> Job | None:
        async with self._lock:
            job = self.jobs.get(job_id)
            if job and job.workspace_id == workspace_id:
                return job
            return None

    async def get_job_events(self, workspace_id: UUID, job_id: UUID) -> list[JobEvent]:
        async with self._lock:
            job = self.jobs.get(job_id)
            if not job or job.workspace_id != workspace_id:
                return []
            return list(self.job_events.get(job_id, []))

    async def create_job_with_outbox(
        self, job: Job, outbox_payload: dict[str, Any] | None = None
    ) -> None:
        async with self._lock:
            self.jobs[job.id] = job
            now = datetime.now(UTC)
            initial_event = JobEvent(
                sequence=1,
                job_id=job.id,
                at=now,
                stage=job.stage or "QUEUED",
                summary=f"Job created with status {job.status.value}",
                status=job.status.value,
            )
            self.job_events[job.id] = [initial_event]
            self.outbox.append(
                {
                    "job_id": job.id,
                    "workspace_id": job.workspace_id,
                    "dispatched": False,
                    "created_at": now,
                    "payload": outbox_payload or {},
                }
            )

    async def acquire_job_lease(
        self, job_id: UUID, worker_id: str, lease_seconds: int = 60
    ) -> int | None:
        async with self._lock:
            now = datetime.now(UTC).timestamp()
            lease = self.job_leases.get(job_id)
            if lease is not None:
                # If lease is active and held by someone else, cannot acquire
                if lease["expires_at"] > now and lease["worker_id"] != worker_id:
                    return None
                new_gen = lease["generation"] + 1
            else:
                new_gen = 1

            self.job_leases[job_id] = {
                "worker_id": worker_id,
                "generation": new_gen,
                "expires_at": now + lease_seconds,
            }
            return new_gen

    async def update_job_stage(
        self, job_id: UUID, generation: int, stage: str, status: str, summary: str
    ) -> None:
        async with self._lock:
            lease = self.job_leases.get(job_id)
            if lease is None or lease["generation"] != generation:
                raise VersionConflictError(
                    f"Job lease fencing token mismatch: expected {lease.get('generation') if lease else None}, got {generation}"
                )

            job = self.jobs.get(job_id)
            if not job:
                raise ValueError(f"Job {job_id} not found")

            now = datetime.now(UTC)
            status_enum = JobStatus(status) if isinstance(status, str) else status
            # Update job state
            job.stage = stage
            job.status = status_enum
            job.updated_at = now
            if status_enum in (JobStatus.SUCCEEDED, JobStatus.FAILED):
                job.finished_at = now

            # Append event
            events = self.job_events.setdefault(job_id, [])
            seq = len(events) + 1
            events.append(
                JobEvent(
                    sequence=seq,
                    job_id=job_id,
                    at=now,
                    stage=stage,
                    summary=summary,
                    status=status_enum,
                )
            )

    async def check_idempotency(
        self, uid: str, method: str, route: str, key: str, body_hash: str
    ) -> tuple[bool, dict[str, Any] | None]:
        async with self._lock:
            id_key = f"{uid}:{method}:{route}:{key}"
            record = self.idempotency_records.get(id_key)
            if not record:
                return False, None
            if record["body_hash"] != body_hash:
                raise VersionConflictError(
                    "Idempotency key reused with different request payload",
                    code="IDEMPOTENCY_KEY_MISMATCH",
                )
            return True, record.get("response")

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
        async with self._lock:
            id_key = f"{uid}:{method}:{route}:{key}"
            self.idempotency_records[id_key] = {
                "body_hash": body_hash,
                "status_code": status_code,
                "response": {"status_code": status_code, "body": response_body},
            }
