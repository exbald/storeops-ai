import hashlib
import io
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from PIL import Image
from storeops_contracts import Job, JobStatus, JobType
from storeops_contracts.models import Error, JobEvents, ResourceType

from apps.api.jobs.runner import JobRunner
from apps.api.ports.state import VersionConflictError


@pytest.mark.asyncio
async def test_ac37_scope_and_membership_enforcement(api_client, bootstrapped_workspace):
    """AC37.1: Multi-tenant boundary enforcement via X-Workspace-Id and role checks."""
    ws = bootstrapped_workspace["workspace"]
    admin_uid = bootstrapped_workspace["admin_uid"]

    # 1. Missing workspace header -> 400
    resp_missing = await api_client.get(
        "/workspace",
        headers={"Authorization": f"Bearer {admin_uid}"},
    )
    assert resp_missing.status_code == 400
    assert resp_missing.json()["code"] == "MISSING_WORKSPACE"

    # 2. Foreign workspace header -> 403
    foreign_ws_id = uuid4()
    resp_foreign = await api_client.get(
        "/workspace",
        headers={
            "Authorization": f"Bearer {admin_uid}",
            "X-Workspace-Id": str(foreign_ws_id),
        },
    )
    assert resp_foreign.status_code == 403
    assert resp_foreign.json()["code"] == "FORBIDDEN"

    # 3. Valid workspace header with admin member -> 200
    resp_valid = await api_client.get(
        "/workspace",
        headers={
            "Authorization": f"Bearer {admin_uid}",
            "X-Workspace-Id": str(ws.id),
        },
    )
    assert resp_valid.status_code == 200


@pytest.mark.asyncio
async def test_ac37_blob_primitives(blob_repo):
    """AC37.2: Blob repository verifies bytes, computes SHA-256 and detects dimensions."""
    media_id = uuid4()

    # 1. Minimal 1x1 valid PNG
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff"
        b"?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    sha, size, dims = await blob_repo.finalize_upload(media_id, raw_bytes=png_bytes)
    assert sha == hashlib.sha256(png_bytes).hexdigest()
    assert size == len(png_bytes)
    assert dims == (1, 1)

    # 2. Download URL generation
    url = await blob_repo.get_download_url(media_id, expires_in_seconds=300)
    assert "expires=300" in url

    # 3. Oversized asset rejection (> 5MB for image)
    oversized_media_id = uuid4()
    oversized_bytes = b"\xff\xd8" + b"\x00" * (6 * 1024 * 1024)
    with pytest.raises(ValueError, match="exceeds maximum allowed size"):
        await blob_repo.finalize_upload(oversized_media_id, raw_bytes=oversized_bytes)

    # 4. EXIF-oriented JPEG: orientation normalization and EXIF metadata stripping
    img = Image.new("RGB", (100, 50), color="blue")
    exif = img.getexif()
    exif[0x0112] = 6  # 90 degrees CW rotation tag
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    exif_jpeg_bytes = buf.getvalue()

    exif_media_id = uuid4()
    _sha_exif, _size_exif, dims_exif = await blob_repo.finalize_upload(
        exif_media_id, raw_bytes=exif_jpeg_bytes
    )
    assert dims_exif == (50, 100)  # Dimensions swapped after orientation normalization

    stored_bytes = await blob_repo.read_bytes(exif_media_id)
    with Image.open(io.BytesIO(stored_bytes)) as stored_img:
        assert not stored_img.getexif()
        assert stored_img.size == (50, 100)


@pytest.mark.asyncio
async def test_ac37_outbox_and_lease_fencing(api_client, state_repo, bootstrapped_workspace):
    """AC37.3: Outbox enqueue, lease fencing tokens, and duplicate delivery protection."""
    ws = bootstrapped_workspace["workspace"]
    admin_uid = bootstrapped_workspace["admin_uid"]
    now = datetime.now(UTC)
    job_id = uuid4()

    # Create job with outbox entry
    job = Job(
        id=job_id,
        workspace_id=ws.id,
        version=1,
        created_at=now,
        updated_at=now,
        type=JobType.INVESTIGATE,
        status=JobStatus.QUEUED,
        resource_id=uuid4(),
        resource_type=ResourceType.INVESTIGATION,
        attempt=1,
        stage="QUEUED",
        started_at=None,
        finished_at=None,
        error=None,
        linked_previous_job_id=None,
        model_id=None,
        usage=None,
    )
    await state_repo.create_job_with_outbox(job, outbox_payload={"action": "run_test"})

    # Check outbox entry created
    assert len(state_repo.outbox) == 1
    assert state_repo.outbox[0]["job_id"] == job_id

    # Worker 1 acquires lease -> generation 1
    _runner1 = JobRunner(state_repo=state_repo, worker_id="worker-1")
    gen1 = await state_repo.acquire_job_lease(job_id, worker_id="worker-1", lease_seconds=60)
    assert gen1 == 1

    # Worker 2 tries to acquire lease while active -> blocked (None)
    gen2 = await state_repo.acquire_job_lease(job_id, worker_id="worker-2", lease_seconds=60)
    assert gen2 is None

    # Worker 1 updates stage with correct fencing token -> succeeds
    await state_repo.update_job_stage(
        job_id=job_id,
        generation=gen1,
        stage="RUNNING",
        status="RUNNING",
        summary="Stage 1 completed",
    )

    # Stale worker (expired generation) tries to update -> VersionConflictError
    with pytest.raises(VersionConflictError, match="fencing token mismatch"):
        await state_repo.update_job_stage(
            job_id=job_id,
            generation=999,  # Stale generation
            stage="SUCCEEDED",
            status="SUCCEEDED",
            summary="Zombie update",
        )

    # Verify events recorded in state repository
    events = await state_repo.get_job_events(ws.id, job_id)
    assert len(events) == 2  # initial event + stage 1
    assert events[1].stage == "RUNNING"

    # HTTP contract verification: GET /jobs/{job_id} and GET /jobs/{job_id}/events
    headers = {
        "Authorization": f"Bearer {admin_uid}",
        "X-Workspace-Id": str(ws.id),
    }
    resp_job = await api_client.get(f"/jobs/{job_id}", headers=headers)
    assert resp_job.status_code == 200
    job_contract = Job.model_validate(resp_job.json())
    assert job_contract.id == job_id
    assert job_contract.status == JobStatus.RUNNING

    resp_events = await api_client.get(f"/jobs/{job_id}/events", headers=headers)
    assert resp_events.status_code == 200
    events_contract = JobEvents.model_validate(resp_events.json())
    assert len(events_contract.items) == 2
    assert events_contract.items[1].stage == "RUNNING"


@pytest.mark.asyncio
async def test_ac37_idempotency_replay(api_client, state_repo, bootstrapped_workspace):
    """AC37.4: Idempotent POST replay returns identical response; mismatch returns 409."""
    ws = bootstrapped_workspace["workspace"]
    admin_uid = bootstrapped_workspace["admin_uid"]
    job_id = uuid4()
    now = datetime.now(UTC)

    # Seed a failed investigation job
    failed_job = Job(
        id=job_id,
        workspace_id=ws.id,
        version=1,
        created_at=now,
        updated_at=now,
        type=JobType.INVESTIGATE,
        status=JobStatus.FAILED,
        resource_id=uuid4(),
        resource_type=ResourceType.INVESTIGATION,
        attempt=1,
        stage="FAILED",
        started_at=now,
        finished_at=now,
        error=Error(
            code="PROVIDER_TIMEOUT",
            message="Temporary provider timeout",
            request_id=uuid4(),
            details=[],
        ),
        linked_previous_job_id=None,
        model_id=None,
        usage=None,
    )
    await state_repo.create_job_with_outbox(failed_job)

    # First retry call with Idempotency-Key
    idempotency_key = "idemp-key-test-12345"
    headers = {
        "Authorization": f"Bearer {admin_uid}",
        "X-Workspace-Id": str(ws.id),
        "Idempotency-Key": idempotency_key,
    }

    resp1 = await api_client.post(f"/jobs/{job_id}/retry", headers=headers)
    assert resp1.status_code == 202
    data1 = resp1.json()
    assert data1["attempt"] == 2
    assert data1["linked_previous_job_id"] == str(job_id)

    # Replay identical request -> returns cached response with same new job ID
    resp2 = await api_client.post(f"/jobs/{job_id}/retry", headers=headers)
    assert resp2.status_code == 202
    data2 = resp2.json()
    assert data1["id"] == data2["id"]

    # Replay with same Idempotency-Key but different payload -> 409 Conflict
    resp_conflict = await api_client.post(
        f"/jobs/{job_id}/retry",
        headers=headers,
        content=b'{"altered": true}',
    )
    assert resp_conflict.status_code == 409
    err_data = resp_conflict.json()
    assert err_data["code"] == "IDEMPOTENCY_KEY_MISMATCH"
