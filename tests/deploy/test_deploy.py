"""Unit and contract tests for cloud deployment scripts and infrastructure configs (T11 / AC-41)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEPLOY_SH = ROOT_DIR / "scripts" / "deploy" / "deploy.sh"
ROLLBACK_SH = ROOT_DIR / "scripts" / "deploy" / "rollback.sh"
SMOKE_CHECK_PY = ROOT_DIR / "scripts" / "deploy" / "smoke_check.py"
INFRA_DIR = ROOT_DIR / "infra"


def test_deploy_script_requires_explicit_project():
    """AC-41: deploy.sh must fail fast if target project is unset (never default to implicit project)."""
    env = os.environ.copy()
    env.pop("STOREOPS_PROJECT_ID", None)
    env.pop("GCP_PROJECT", None)

    proc = subprocess.run(
        ["bash", str(DEPLOY_SH)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 2
    assert "BLOCKED: Cloud deployment requires an explicit authorized project" in proc.stdout


def test_deploy_script_protects_production():
    """AC-41: deploy.sh must abort if project name looks like production without explicit override."""
    env = os.environ.copy()
    env["STOREOPS_PROJECT_ID"] = "storeops-production-ac41"
    env["STOREOPS_ALLOW_PROD"] = "0"

    proc = subprocess.run(
        ["bash", str(DEPLOY_SH)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 1
    assert "appears to be PRODUCTION" in proc.stdout


def test_smoke_check_verify_config_only():
    """AC-41: smoke_check.py --verify-config-only validates all scaffold files."""
    proc = subprocess.run(
        [sys.executable, str(SMOKE_CHECK_PY), "--verify-config-only"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0
    assert "[PASS] firestore_indexes" in proc.stdout
    assert "[PASS] bigquery_schema" in proc.stdout
    assert "[PASS] worker_iam" in proc.stdout
    assert "[PASS] outbox_schedule" in proc.stdout
    assert "[PASS] terraform_main" in proc.stdout
    assert "[PASS] deploy_script" in proc.stdout
    assert "[PASS] rollback_script" in proc.stdout
    assert "[PASS] documentation" in proc.stdout


def test_smoke_check_blocked_when_unconfigured():
    """AC-41 / AGENTS.md: Missing credentials must output BLOCKED and exit code 2."""
    env = os.environ.copy()
    env.pop("STOREOPS_API_URL", None)

    proc = subprocess.run(
        [sys.executable, str(SMOKE_CHECK_PY)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 2
    assert "[BLOCKED]" in proc.stdout
    assert "Missing credentials produce a blocked live gate" in proc.stdout


def test_firestore_indexes_schema():
    """AC-41: firestore.indexes.json must contain required indexes for StoreOps entities."""
    indexes_file = INFRA_DIR / "firestore.indexes.json"
    assert indexes_file.exists(), "firestore.indexes.json must exist"

    with open(indexes_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    indexes = data.get("indexes", [])
    assert len(indexes) >= 8

    collection_groups = {idx["collectionGroup"] for idx in indexes}
    required_groups = {
        "stores",
        "products",
        "locations",
        "imports",
        "promotions",
        "policy_versions",
        "outbox",
        "jobs",
        "memberships",
    }
    assert required_groups.issubset(collection_groups)


def test_bigquery_schema_ddl():
    """AC-41: bigquery_schema.sql must define partitioned and clustered analytics tables."""
    schema_file = INFRA_DIR / "bigquery_schema.sql"
    assert schema_file.exists(), "bigquery_schema.sql must exist"

    content = schema_file.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS sales_facts" in content
    assert "PARTITION BY business_date" in content
    assert "CLUSTER BY workspace_id, store_id, sku" in content

    assert "CREATE TABLE IF NOT EXISTS inventory_facts" in content
    assert "CLUSTER BY workspace_id, location_id, sku" in content

    assert "CREATE TABLE IF NOT EXISTS import_batches" in content
    assert "CLUSTER BY workspace_id, batch_id" in content


def test_bigquery_schema_parity_with_migration():
    """AC-41: Assert infra/bigquery_schema.sql and migrations/bigquery/001_initial_analytics.sql maintain exact parity."""
    infra_ddl = INFRA_DIR / "bigquery_schema.sql"
    migration_ddl = ROOT_DIR / "migrations" / "bigquery" / "001_initial_analytics.sql"
    assert infra_ddl.exists()
    assert migration_ddl.exists()
    assert infra_ddl.read_text(encoding="utf-8") == migration_ddl.read_text(encoding="utf-8")


def test_bigquery_ddl_statement_split_parser():
    """AC-41: deploy.sh statement-by-statement DDL parser must yield all 3 CREATE TABLE statements."""
    ddl_file = ROOT_DIR / "migrations" / "bigquery" / "001_initial_analytics.sql"
    sql = ddl_file.read_text(encoding="utf-8")
    cleaned_lines = [l for l in sql.splitlines() if not l.strip().startswith("--")]
    cleaned_sql = "\n".join(cleaned_lines)
    statements = [s.strip() for s in cleaned_sql.split(";") if s.strip()]

    assert len(statements) == 3
    assert "CREATE TABLE IF NOT EXISTS import_batches" in statements[0]
    assert "CREATE TABLE IF NOT EXISTS sales_facts" in statements[1]
    assert "CREATE TABLE IF NOT EXISTS inventory_facts" in statements[2]


def test_worker_iam_and_scheduler_specs():
    """AC-41: worker IAM must be private and outbox schedule must run once per minute."""
    worker_iam = INFRA_DIR / "worker_iam.json"
    assert worker_iam.exists()
    with open(worker_iam, "r", encoding="utf-8") as f:
        iam_data = json.load(f)
    assert iam_data.get("ingress") == "INGRESS_TRAFFIC_INTERNAL_ONLY"
    assert iam_data.get("authentication") == "REQUIRED"

    outbox_spec = INFRA_DIR / "outbox_schedule.json"
    assert outbox_spec.exists()
    with open(outbox_spec, "r", encoding="utf-8") as f:
        sched_data = json.load(f)
    assert sched_data.get("schedule") == "* * * * *"
    assert "/health" in sched_data.get("httpTarget", {}).get("uri", "")


def test_terraform_files_syntax():
    """AC-41: Terraform configuration files must exist with required resource definitions."""
    main_tf = INFRA_DIR / "main.tf"
    assert main_tf.exists()
    content = main_tf.read_text(encoding="utf-8")

    assert "resource \"google_cloud_run_v2_service\" \"api\"" in content
    assert "resource \"google_cloud_run_v2_service\" \"worker\"" in content
    assert "resource \"google_cloud_tasks_queue\" \"work_queue\"" in content
    assert "resource \"google_cloud_scheduler_job\" \"outbox_drain\"" in content
    assert "resource \"google_storage_bucket\" \"media\"" in content
    assert "resource \"google_bigquery_dataset\" \"analytics\"" in content
    assert "resource \"google_artifact_registry_repository\" \"storeops\"" in content
    assert 'command = ["python3", "-m", "scripts.deploy.run_worker"]' in content
    assert "container_port = 8001" in content

    variables_tf = INFRA_DIR / "variables.tf"
    assert variables_tf.exists()
    var_content = variables_tf.read_text(encoding="utf-8")
    assert 'default     = "gemini-3.8-flash"' in var_content

    outputs_tf = INFRA_DIR / "outputs.tf"
    assert outputs_tf.exists()


def test_rollback_script_usage():
    """AC-41: rollback.sh must print usage when invoked without arguments."""
    proc = subprocess.run(
        ["bash", str(ROLLBACK_SH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "Usage:" in proc.stdout or "Usage:" in proc.stderr


def test_rollback_script_protects_production():
    """AC-41: rollback.sh must abort if target project looks like production without override."""
    env = os.environ.copy()
    env["STOREOPS_PROJECT_ID"] = "storeops-production-ac41"
    env["STOREOPS_ALLOW_PROD"] = "0"

    proc = subprocess.run(
        ["bash", str(ROLLBACK_SH), "api"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "appears to be PRODUCTION" in proc.stdout


@pytest.mark.asyncio
async def test_ac41_queue_worker_smoke_handler():
    """AC-41: Queue and worker smoke execution with lease fencing and job runner."""
    from datetime import UTC, datetime
    from uuid import uuid4

    from storeops_contracts import JobStatus, JobType
    from storeops_contracts.models import Job, ResourceType

    from apps.api.adapters.state.in_memory import InMemoryStateRepository
    from apps.api.jobs.runner import JobRunner

    state_repo = InMemoryStateRepository()
    ws_id = uuid4()
    job_id = uuid4()
    now = datetime.now(UTC)

    job = Job(
        id=job_id,
        workspace_id=ws_id,
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

    await state_repo.create_job_with_outbox(job, outbox_payload={"action": "cloud_smoke_test"})
    assert len(state_repo.outbox) >= 1

    executed = False

    async def _smoke_handler(j: Job, generation: int):
        nonlocal executed
        executed = True
        assert j.id == job_id
        assert generation >= 1

    runner = JobRunner(state_repo=state_repo, worker_id="smoke-worker-1")
    runner.register_handler(job.type.value if hasattr(job.type, "value") else str(job.type), _smoke_handler)

    await runner.execute_job(ws_id, job_id)

    assert executed, "Queue/worker smoke handler must have been executed"
    fetched = await state_repo.get_job(ws_id, job_id)
    assert fetched is not None
    assert fetched.status == JobStatus.SUCCEEDED

    # Duplicate delivery tolerance: second runner invocation on completed job is a no-op
    executed_again = False

    async def _fail_on_duplicate(j: Job, generation: int):
        nonlocal executed_again
        executed_again = True

    runner2 = JobRunner(state_repo=state_repo, worker_id="smoke-worker-2")
    runner2.register_handler(job.type.value if hasattr(job.type, "value") else str(job.type), _fail_on_duplicate)
    duplicate_result = await runner2.execute_job(ws_id, job_id)
    assert duplicate_result is True, "Terminal job execution should return True without re-running"
    assert not executed_again, "Completed job handler must not be re-executed on duplicate delivery"


@pytest.mark.asyncio
async def test_ac41_cloud_run_worker_http_server():
    """AC-41: scripts.deploy.run_worker binds port and responds 200 OK to Cloud Run health checks."""
    import asyncio

    from scripts.deploy.run_worker import _handle_http_client

    server = await asyncio.start_server(_handle_http_client, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()

    async with server:
        reader, writer = await asyncio.open_connection(host, port)
        writer.write(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()

        response = await reader.read(1024)
        writer.close()
        await writer.wait_closed()

        assert b"HTTP/1.1 200 OK" in response
        assert b"READY" in response
        assert b"storeops-worker" in response


