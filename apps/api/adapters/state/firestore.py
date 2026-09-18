import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from google.cloud import firestore
from storeops_contracts.models import Job, JobEvent, Membership, Workspace

from apps.api.ports.state import StateRepository, VersionConflictError


class FirestoreStateRepository(StateRepository):
    def __init__(self, project_id: str | None = None) -> None:
        self.project_id = (
            project_id
            or os.getenv("FIREBASE_PROJECT_ID")
            or os.getenv("GCP_PROJECT")
            or os.getenv("STOREOPS_PROJECT_ID")
            or "storeops-dev"
        )
        self.db = firestore.AsyncClient(project=self.project_id)

    async def get_workspace(self, workspace_id: UUID) -> Workspace | None:
        doc = await self.db.collection("workspaces").document(str(workspace_id)).get()
        if not doc.exists:
            return None
        return Workspace.model_validate(doc.to_dict())

    async def get_memberships_for_user(self, uid: str) -> list[Membership]:
        docs = self.db.collection("memberships").where("uid", "==", uid).stream()
        results: list[Membership] = []
        async for doc in docs:
            data = doc.to_dict()
            results.append(
                Membership(
                    workspace_id=UUID(data["workspace_id"]),
                    workspace_name=data["workspace_name"],
                    role=data["role"],
                )
            )
        return results

    async def get_membership(self, workspace_id: UUID, uid: str) -> Membership | None:
        doc_id = f"{workspace_id}_{uid}"
        doc = await self.db.collection("memberships").document(doc_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        return Membership(
            workspace_id=UUID(data["workspace_id"]),
            workspace_name=data["workspace_name"],
            role=data["role"],
        )

    async def create_workspace_with_admin(
        self, workspace: Workspace, uid: str, email: str | None = None
    ) -> Membership:
        ws_ref = self.db.collection("workspaces").document(str(workspace.id))
        mem_ref = self.db.collection("memberships").document(f"{workspace.id}_{uid}")

        ws_data = workspace.model_dump(mode="json")
        mem_data = {
            "workspace_id": str(workspace.id),
            "workspace_name": workspace.name,
            "uid": uid,
            "role": "ADMIN",
            "email": email,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Write in a batch
        batch = self.db.batch()
        batch.set(ws_ref, ws_data)
        batch.set(mem_ref, mem_data)
        await batch.commit()

        return Membership(
            workspace_id=workspace.id,
            workspace_name=workspace.name,
            role="ADMIN",
        )

    async def add_membership(
        self, workspace_id: UUID, uid: str, role: str, email: str | None = None
    ) -> Membership:
        ws = await self.get_workspace(workspace_id)
        if not ws:
            raise ValueError(f"Workspace {workspace_id} not found")

        doc_id = f"{workspace_id}_{uid}"
        mem_ref = self.db.collection("memberships").document(doc_id)
        mem_data = {
            "workspace_id": str(workspace_id),
            "workspace_name": ws.name,
            "uid": uid,
            "role": role,
            "email": email,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await mem_ref.set(mem_data, merge=True)
        return Membership(
            workspace_id=workspace_id,
            workspace_name=ws.name,
            role=role,
        )

    async def get_job(self, workspace_id: UUID, job_id: UUID) -> Job | None:
        doc = await self.db.collection("jobs").document(str(job_id)).get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        if data.get("workspace_id") != str(workspace_id):
            return None
        return Job.model_validate(data)

    async def get_job_events(self, workspace_id: UUID, job_id: UUID) -> list[JobEvent]:
        job = await self.get_job(workspace_id, job_id)
        if not job:
            return []
        events_ref = (
            self.db.collection("jobs")
            .document(str(job_id))
            .collection("events")
            .order_by("sequence")
        )
        results: list[JobEvent] = []
        async for doc in events_ref.stream():
            results.append(JobEvent.model_validate(doc.to_dict()))
        return results

    async def create_job_with_outbox(
        self, job: Job, outbox_payload: dict[str, Any] | None = None
    ) -> None:
        job_ref = self.db.collection("jobs").document(str(job.id))
        event_ref = job_ref.collection("events").document("1")
        outbox_ref = self.db.collection("outbox").document(str(job.id))

        now = datetime.now(timezone.utc)
        initial_event = JobEvent(
            sequence=1,
            job_id=job.id,
            at=now,
            stage=job.stage or "QUEUED",
            summary=f"Job created with status {job.status.value}",
            status=job.status.value,
        )

        batch = self.db.batch()
        batch.set(job_ref, job.model_dump(mode="json"))
        batch.set(event_ref, initial_event.model_dump(mode="json"))
        batch.set(
            outbox_ref,
            {
                "job_id": str(job.id),
                "workspace_id": str(job.workspace_id),
                "dispatched": False,
                "created_at": now.isoformat(),
                "payload": outbox_payload or {},
            },
        )
        await batch.commit()

    async def acquire_job_lease(
        self, job_id: UUID, worker_id: str, lease_seconds: int = 60
    ) -> int | None:
        lease_ref = self.db.collection("job_leases").document(str(job_id))
        now = datetime.now(timezone.utc).timestamp()

        # Run in transaction
        @firestore.async_transactional
        async def _acquire(transaction: firestore.AsyncTransaction) -> int | None:
            snapshot = await lease_ref.get(transaction=transaction)
            if snapshot.exists:
                data = snapshot.to_dict()
                if data["expires_at"] > now and data["worker_id"] != worker_id:
                    return None
                new_gen = data["generation"] + 1
            else:
                new_gen = 1

            transaction.set(
                lease_ref,
                {
                    "worker_id": worker_id,
                    "generation": new_gen,
                    "expires_at": now + lease_seconds,
                },
            )
            return new_gen

        transaction = self.db.transaction()
        return await _acquire(transaction)

    async def update_job_stage(
        self, job_id: UUID, generation: int, stage: str, status: str, summary: str
    ) -> None:
        job_ref = self.db.collection("jobs").document(str(job_id))
        lease_ref = self.db.collection("job_leases").document(str(job_id))

        now = datetime.now(timezone.utc)

        @firestore.async_transactional
        async def _update(transaction: firestore.AsyncTransaction) -> None:
            lease_snap = await lease_ref.get(transaction=transaction)
            if not lease_snap.exists or lease_snap.to_dict().get("generation") != generation:
                raise VersionConflictError("Job lease fencing token mismatch")

            job_snap = await job_ref.get(transaction=transaction)
            if not job_snap.exists:
                raise ValueError(f"Job {job_id} not found")

            # Update job
            update_data = {
                "stage": stage,
                "status": status,
                "updated_at": now.isoformat(),
            }
            if status in ["SUCCEEDED", "FAILED"]:
                update_data["finished_at"] = now.isoformat()
            transaction.update(job_ref, update_data)

            # Add event
            events_count = len([d async for d in job_ref.collection("events").stream()])
            seq = events_count + 1
            event_ref = job_ref.collection("events").document(str(seq))
            event = JobEvent(
                sequence=seq,
                job_id=job_id,
                at=now,
                stage=stage,
                summary=summary,
                status=status,
            )
            transaction.set(event_ref, event.model_dump(mode="json"))

        transaction = self.db.transaction()
        await _update(transaction)

    async def check_idempotency(
        self, uid: str, method: str, route: str, key: str, body_hash: str
    ) -> tuple[bool, dict[str, Any] | None]:
        doc_id = f"{uid}_{method}_{route.replace('/', '_')}_{key}"
        doc = await self.db.collection("idempotency").document(doc_id).get()
        if not doc.exists:
            return False, None
        data = doc.to_dict()
        if data.get("body_hash") != body_hash:
            raise VersionConflictError(
                "Idempotency key reused with different request payload",
                code="IDEMPOTENCY_KEY_MISMATCH",
            )
        return True, data.get("response")

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
        doc_id = f"{uid}_{method}_{route.replace('/', '_')}_{key}"
        doc_ref = self.db.collection("idempotency").document(doc_id)
        await doc_ref.set(
            {
                "body_hash": body_hash,
                "status_code": status_code,
                "response": {"status_code": status_code, "body": response_body},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
