"""Complete the demo's example visit with live AI calls, through the public HTTP API only.

Runs one investigation on the example visit, accepts its plan, then verifies twice: first
with a shelf photo that still breaks the agreement (expected to need more work), then with
a compliant photo (expected to pass and close the visit). After photos are uploaded right
before each verification because the API only accepts captures from the last 30 minutes.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

from scripts.seed_demo.seed import upload_demo_media

JOB_TIMEOUT_SECONDS = 240
TERMINAL_JOB_STATES = ("SUCCEEDED", "FAILED", "CANCELLED")


async def wait_for_job(client: httpx.AsyncClient, headers: dict[str, str], job_id: str) -> dict:
    """Poll a job until it reaches a terminal state; a failed job raises."""
    deadline = asyncio.get_running_loop().time() + JOB_TIMEOUT_SECONDS
    while True:
        res = await client.get(f"/jobs/{job_id}", headers=headers)
        if res.status_code != 200:
            raise RuntimeError(f"Failed to read job {job_id}: {res.status_code} {res.text}")
        job = res.json()
        if job["status"] in TERMINAL_JOB_STATES:
            if job["status"] != "SUCCEEDED":
                raise RuntimeError(f"Job {job_id} ended {job['status']}: {job.get('error')}")
            return job
        if asyncio.get_running_loop().time() > deadline:
            raise TimeoutError(f"Job {job_id} did not finish within {JOB_TIMEOUT_SECONDS}s")
        await asyncio.sleep(2)


async def post_command(
    client: httpx.AsyncClient, headers: dict[str, str], path: str, body: dict, expected: tuple[int, ...]
) -> dict:
    res = await client.post(path, json=body, headers={**headers, "Idempotency-Key": f"seed-ai-{uuid4()}"})
    if res.status_code not in expected:
        raise RuntimeError(f"POST {path} failed: {res.status_code} {res.text}")
    return res.json()


async def get_json(client: httpx.AsyncClient, headers: dict[str, str], path: str) -> dict:
    res = await client.get(path, headers=headers)
    if res.status_code != 200:
        raise RuntimeError(f"GET {path} failed: {res.status_code} {res.text}")
    return res.json()


async def verify_with_photo(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    seed_result: dict,
    investigation_id: str,
    photo: Path,
    zone: tuple[str, str],
) -> dict:
    """Upload a fresh after photo for the example visit and run one verification."""
    media_id = await upload_demo_media(
        client,
        photo,
        kind="VISIT_AFTER",
        headers=headers,
        store_id=seed_result["store_id"],
        zone_id=zone[0],
        zone_kind=zone[1],
        captured_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        visit_id=seed_result["example_visit_id"],
    )
    inv = await get_json(client, headers, f"/investigations/{investigation_id}")
    job = await post_command(
        client,
        headers,
        f"/investigations/{investigation_id}/verify",
        {"expected_version": inv["version"], "after_media_ids": [media_id]},
        expected=(202,),
    )
    await wait_for_job(client, headers, job["id"])
    return await get_json(client, headers, f"/investigations/{investigation_id}")


async def complete_example_visit(
    client: httpx.AsyncClient, admin_headers: dict[str, str], seed_result: dict, fixtures_dir: Path
) -> dict:
    """Run investigate, accept, verify (fail), verify (pass) on the example visit once."""
    headers = {**admin_headers, "X-Workspace-Id": seed_result["workspace_id"]}
    visit_id = seed_result["example_visit_id"]

    visit = await get_json(client, headers, f"/visits/{visit_id}")
    if visit["status"] == "CLOSED":
        return {"status": "ALREADY_COMPLETE", "visit_id": visit_id}

    existing = await get_json(client, headers, f"/investigations?visit_id={visit_id}")
    if existing.get("items"):
        return {"status": "IN_PROGRESS_LEFT_AS_IS", "investigation_id": existing["items"][0]["id"]}

    job = await post_command(
        client,
        headers,
        "/investigations",
        {
            "store_id": seed_result["store_id"],
            "visit_id": visit_id,
            "promotion_id": seed_result["promotion_id"],
            "media_ids": [seed_result["example_shelf_before_media_id"]],
        },
        expected=(202,),
    )
    await wait_for_job(client, headers, job["id"])
    investigation_id = job["resource_id"]

    inv = await get_json(client, headers, f"/investigations/{investigation_id}")
    await post_command(
        client,
        headers,
        f"/investigations/{investigation_id}/accept",
        {"expected_version": inv["version"]},
        expected=(200,),
    )

    manifest_media = {
        "fail": fixtures_dir / "media" / "shelf_after_fail.jpg",
        "pass": fixtures_dir / "media" / "shelf_after.jpg",
    }
    store_cfg = json.loads((fixtures_dir / "manifest.json").read_text(encoding="utf-8"))["store"]
    zone = (store_cfg["zone_id"], store_cfg["zone_kind"])
    after_fail = await verify_with_photo(client, headers, seed_result, investigation_id, manifest_media["fail"], zone)
    after_pass = await verify_with_photo(client, headers, seed_result, investigation_id, manifest_media["pass"], zone)

    return {
        "status": "COMPLETED",
        "investigation_id": investigation_id,
        "hypothesis": (inv.get("diagnosis") or {}).get("hypothesis"),
        "state_after_failing_photo": after_fail["state"],
        "state_after_passing_photo": after_pass["state"],
    }
