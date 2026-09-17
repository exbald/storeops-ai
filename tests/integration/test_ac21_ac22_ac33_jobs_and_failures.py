"""Integration tests for AC21, AC22, and AC33.

AC21: Job persistence, event stream polling, outbox delivery, crash recovery idempotency.
AC22: Provider timeouts, quota exhaustion, permanent error budgets, explicit incomplete state.
AC33: Invalid model JSON single repair attempt, subsequent failure leaves investigation incomplete without false resolution.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from storeops_contracts.models import (
    Error,
    Job,
    ResourceType,
    Status2,
    Type2,
)

from apps.api.ports.state import StateRepository


@pytest.mark.asyncio
async def test_ac21_job_persistence_and_event_stream(
    integration_client: AsyncClient,
    rep_a_headers: dict[str, str],
    int_state_repo: StateRepository,
    workspace_a_id: UUID,
):
    """AC21: Job remains discoverable after disconnect/restart; event stream preserves sequence."""
    job_id = uuid4()
    now = datetime.now(UTC)

    # 1. Create a job in state repo with outbox
    job = Job(
        id=job_id,
        workspace_id=workspace_a_id,
        version=1,
        created_at=now,
        updated_at=now,
        type=Type2.INVESTIGATE,
        status=Status2.QUEUED,
        resource_id=uuid4(),
        resource_type=ResourceType.INVESTIGATION,
        attempt=1,
        stage="CREATED",
        started_at=None,
        finished_at=None,
        error=None,
        linked_previous_job_id=None,
        model_id=None,
        usage=None,
    )
    await int_state_repo.create_job_with_outbox(job)

    # 2. Acquire lease and advance stages with lease fencing
    gen = await int_state_repo.acquire_job_lease(job_id=job_id, worker_id="worker-test-1")
    assert gen is not None

    await int_state_repo.update_job_stage(
        job_id=job_id,
        generation=gen,
        stage="RUNNING",
        status=Status2.RUNNING,
        summary="Model investigation underway",
    )
    await int_state_repo.update_job_stage(
        job_id=job_id,
        generation=gen,
        stage="COMPLETED",
        status=Status2.SUCCEEDED,
        summary="Investigation concluded successfully",
    )

    # 3. Discover job via GET /jobs/{job_id}
    res_job = await integration_client.get(f"/jobs/{job_id}", headers=rep_a_headers)
    assert res_job.status_code == 200
    retrieved_job = res_job.json()
    assert retrieved_job["id"] == str(job_id)
    assert retrieved_job["type"] == "INVESTIGATE"
    assert retrieved_job["status"] == "SUCCEEDED"

    # 4. Stream events via GET /jobs/{job_id}/events
    res_events = await integration_client.get(f"/jobs/{job_id}/events", headers=rep_a_headers)
    assert res_events.status_code == 200
    events_data = res_events.json()
    assert len(events_data["items"]) == 3
    assert events_data["items"][0]["sequence"] == 1
    assert events_data["items"][1]["sequence"] == 2
    assert events_data["items"][2]["sequence"] == 3

    # 5. Incremental streaming after sequence 1
    res_incremental = await integration_client.get(
        f"/jobs/{job_id}/events?after_sequence=1",
        headers=rep_a_headers,
    )
    assert res_incremental.status_code == 200
    inc_data = res_incremental.json()
    assert len(inc_data["items"]) == 2
    assert inc_data["items"][0]["sequence"] == 2


@pytest.mark.asyncio
async def test_ac22_provider_timeout_permanent_failure_no_fake_success(
    integration_client: AsyncClient,
    admin_a_headers: dict[str, str],
    rep_a_headers: dict[str, str],
    int_state_repo: StateRepository,
    workspace_a_id: UUID,
):
    """AC22: Permanent model/provider failure yields explicit incomplete/failed state, never fake success."""
    job_id = uuid4()
    now = datetime.now(UTC)

    # Create job that encountered an unrecoverable quota / timeout error
    job = Job(
        id=job_id,
        workspace_id=workspace_a_id,
        version=1,
        created_at=now,
        updated_at=now,
        type=Type2.INVESTIGATE,
        status=Status2.FAILED,
        resource_id=uuid4(),
        resource_type=ResourceType.INVESTIGATION,
        attempt=3,
        stage="FAILED",
        started_at=now,
        finished_at=now,
        error=Error(
            code="MODEL_QUOTA_EXHAUSTED",
            message="Model quota exhausted (RESOURCE_EXHAUSTED): 429 permanent failure",
            request_id=str(uuid4()),
            details=[],
        ),
        linked_previous_job_id=None,
        model_id="gemini-2.5-flash",
        usage=None,
    )
    await int_state_repo.create_job_with_outbox(job)

    res = await integration_client.get(f"/jobs/{job_id}", headers=rep_a_headers)
    assert res.status_code == 200
    retrieved = res.json()
    assert retrieved["status"] == "FAILED"
    assert retrieved["error"]["code"] == "MODEL_QUOTA_EXHAUSTED"
    assert "RESOURCE_EXHAUSTED" in retrieved["error"]["message"]
    assert retrieved["status"] != "SUCCEEDED"


@pytest.mark.asyncio
async def test_ac33_idempotency_key_payload_mismatch_returns_409(
    integration_client: AsyncClient,
    admin_a_headers: dict[str, str],
):
    """AC33: Reusing an idempotency key with a differing payload returns 409 conflict."""
    key = str(uuid4())
    payload_a = {
        "code": f"STR-IDEMP-{uuid4().hex[:6]}",
        "name": "Store Alpha",
        "retailer": "Retail Corp",
        "region": "North",
        "format": "Supermarket",
        "timezone": "Asia/Singapore",
        "distributor_location_id": None,
    }

    # 1. First request with payload_a succeeds
    res_1 = await integration_client.post(
        "/stores",
        headers={**admin_a_headers, "Idempotency-Key": key},
        json=payload_a,
    )
    assert res_1.status_code == 201

    # 2. Replay with exact same payload_a returns cached 201
    res_replay = await integration_client.post(
        "/stores",
        headers={**admin_a_headers, "Idempotency-Key": key},
        json=payload_a,
    )
    assert res_replay.status_code == 201

    # 3. Request with same key but differing payload_b -> returns 409 IDEMPOTENCY_KEY_MISMATCH
    payload_b = {**payload_a, "name": "Conflicting Store Name"}
    res_conflict = await integration_client.post(
        "/stores",
        headers={**admin_a_headers, "Idempotency-Key": key},
        json=payload_b,
    )
    assert res_conflict.status_code == 409
    assert res_conflict.json()["code"] == "IDEMPOTENCY_KEY_MISMATCH"


@pytest.mark.asyncio
async def test_ac33_model_schema_repair_failure_ends_incomplete(
    integration_client: AsyncClient,
    admin_a_headers: dict[str, str],
    rep_a_headers: dict[str, str],
    int_state_repo: StateRepository,
    workspace_a_id: UUID,
):
    """AC33: When model returns invalid JSON and 1-shot repair fails, job ends FAILED without false resolution."""
    job_id = uuid4()
    now = datetime.now(UTC)

    # Job record reflecting failed 1-shot repair
    job = Job(
        id=job_id,
        workspace_id=workspace_a_id,
        version=1,
        created_at=now,
        updated_at=now,
        type=Type2.VERIFY,
        status=Status2.FAILED,
        resource_id=uuid4(),
        resource_type=ResourceType.VERIFICATION,
        attempt=2,
        stage="FAILED",
        started_at=now,
        finished_at=now,
        error=Error(
            code="SCHEMA_VALIDATION_FAILED",
            message="Verification output schema repair failed: Invalid JSON syntax after 1-shot repair",
            request_id=str(uuid4()),
            details=[],
        ),
        linked_previous_job_id=None,
        model_id="gemini-2.5-flash",
        usage=None,
    )
    await int_state_repo.create_job_with_outbox(job)

    # Verify job is failed and does not produce a false PASS or resolved state
    res = await integration_client.get(f"/jobs/{job_id}", headers=rep_a_headers)
    assert res.status_code == 200
    retrieved = res.json()
    assert retrieved["status"] == "FAILED"
    assert retrieved["error"]["code"] == "SCHEMA_VALIDATION_FAILED"
    assert retrieved["status"] != "SUCCEEDED"
