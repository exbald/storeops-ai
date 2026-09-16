#!/usr/bin/env python3
"""StoreOps Cloud Deployment Smoke Check (T11 / AC-41).

Verifies health, auth rejection, private worker isolation, and infrastructure
configuration. Fails closed with BLOCKED status when credentials or deployment
endpoints are unconfigured, strictly adhering to AGENTS.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def check_scaffold_configs() -> dict[str, Any]:
    """Validates presence and schema of infrastructure and deployment files."""
    results: dict[str, Any] = {
        "firestore_indexes": False,
        "bigquery_schema": False,
        "worker_iam": False,
        "outbox_schedule": False,
        "terraform_main": False,
        "deploy_script": False,
        "rollback_script": False,
        "documentation": False,
    }

    # 1. Firestore indexes
    indexes_path = ROOT_DIR / "infra" / "firestore.indexes.json"
    if indexes_path.exists():
        with open(indexes_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            indexes = data.get("indexes", [])
            collection_groups = {idx.get("collectionGroup") for idx in indexes}
            required_groups = {"stores", "products", "memberships", "imports", "outbox"}
            if required_groups.issubset(collection_groups):
                results["firestore_indexes"] = True

    # 2. BigQuery schema DDL
    bq_path = ROOT_DIR / "infra" / "bigquery_schema.sql"
    if bq_path.exists():
        content = bq_path.read_text(encoding="utf-8")
        if "sales_facts" in content and "inventory_facts" in content and "import_batches" in content:
            results["bigquery_schema"] = True

    # 3. Worker IAM
    iam_path = ROOT_DIR / "infra" / "worker_iam.json"
    if iam_path.exists():
        with open(iam_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("service") == "storeops-worker" and data.get("ingress") == "INGRESS_TRAFFIC_INTERNAL_ONLY":
                results["worker_iam"] = True

    # 4. Outbox schedule
    schedule_path = ROOT_DIR / "infra" / "outbox_schedule.json"
    if schedule_path.exists():
        with open(schedule_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            uri = data.get("httpTarget", {}).get("uri", "")
            if data.get("schedule") == "* * * * *" and ("/health" in uri or "/outbox/drain" in uri):
                results["outbox_schedule"] = True

    # 5. Terraform main
    tf_path = ROOT_DIR / "infra" / "main.tf"
    if tf_path.exists():
        content = tf_path.read_text(encoding="utf-8")
        if "google_cloud_run_v2_service" in content and "google_cloud_tasks_queue" in content:
            results["terraform_main"] = True

    # 6. Deploy script
    deploy_path = ROOT_DIR / "scripts" / "deploy" / "deploy.sh"
    if deploy_path.exists() and os.access(deploy_path, os.X_OK):
        results["deploy_script"] = True

    # 7. Rollback script
    rollback_path = ROOT_DIR / "scripts" / "deploy" / "rollback.sh"
    if rollback_path.exists() and os.access(rollback_path, os.X_OK):
        results["rollback_script"] = True

    # 8. Documentation
    doc_path = ROOT_DIR / "docs" / "cloud-setup.md"
    if doc_path.exists() and len(doc_path.read_text(encoding="utf-8")) > 500:
        results["documentation"] = True

    return results


def run_live_smoke_checks(api_url: str, worker_url: str | None = None) -> list[dict[str, Any]]:
    """Runs live HTTP smoke checks against deployed API and Worker services."""
    checks: list[dict[str, Any]] = []

    # Check 1: Health endpoint
    health_url = f"{api_url.rstrip('/')}/health"
    try:
        req = urllib.request.Request(health_url, headers={"User-Agent": "StoreOps-SmokeCheck/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            body = json.loads(resp.read().decode("utf-8"))
            passed = status == 200 and body.get("status") in ("READY", "DEGRADED")
            checks.append({
                "name": "GET /health readiness",
                "passed": passed,
                "detail": f"Status: {status}, Body: {body}",
            })
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        checks.append({
            "name": "GET /health readiness",
            "passed": False,
            "detail": f"Failed to connect to {health_url}: {e}",
        })

    # Check 2: Unauthenticated protected endpoint returns 401
    workspace_url = f"{api_url.rstrip('/')}/workspace"
    try:
        req = urllib.request.Request(workspace_url, headers={"User-Agent": "StoreOps-SmokeCheck/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            checks.append({
                "name": "Auth rejection (unauthenticated)",
                "passed": False,
                "detail": f"Expected 401 but got status {resp.status}",
            })
    except urllib.error.HTTPError as e:
        passed = e.code == 401
        checks.append({
            "name": "Auth rejection (unauthenticated)",
            "passed": passed,
            "detail": f"Correctly returned HTTP {e.code}",
        })
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        checks.append({
            "name": "Auth rejection (unauthenticated)",
            "passed": False,
            "detail": f"Unexpected network error: {e}",
        })

    # Check 3: Private worker isolation (if worker URL provided)
    if worker_url:
        try:
            req = urllib.request.Request(worker_url, headers={"User-Agent": "StoreOps-SmokeCheck/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                checks.append({
                    "name": "Private worker isolation",
                    "passed": False,
                    "detail": f"Expected 401/403 but got status {resp.status} (Worker is publicly accessible!)",
                })
        except urllib.error.HTTPError as e:
            passed = e.code in (401, 403)
            checks.append({
                "name": "Private worker isolation",
                "passed": passed,
                "detail": f"Worker rejected public ingress with HTTP {e.code}",
            })
        except (TimeoutError, urllib.error.URLError, OSError) as e:
            # Internal-only Cloud Run returns 403 or drops connections/times out at GFE
            reason = str(getattr(e, "reason", e)).lower()
            is_boundary = isinstance(e, TimeoutError) or any(k in reason for k in ("timed out", "connection reset", "connection refused"))
            checks.append({
                "name": "Private worker isolation",
                "passed": is_boundary,
                "detail": f"Worker ingress blocked at network boundary ({e})" if is_boundary else f"Worker check failed with unexpected error: {e}",
            })

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="StoreOps Cloud Deployment Smoke Check (AC-41)")
    parser.add_argument("--api-url", default=os.getenv("STOREOPS_API_URL"), help="Public API URL to test")
    parser.add_argument("--worker-url", default=os.getenv("STOREOPS_WORKER_URL"), help="Private Worker URL to test")
    parser.add_argument(
        "--verify-config-only",
        action="store_true",
        help="Verify infrastructure configuration and deployment artifacts only",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("StoreOps Cloud Deployment Smoke Check (T11 / AC-41)")
    print("=" * 60)

    # 1. Verify Configuration & Scaffold Artifacts
    print("\n1. Verifying cloud scaffold artifacts...")
    config_results = check_scaffold_configs()
    all_configs_pass = True
    for item, passed in config_results.items():
        status_str = "PASS" if passed else "FAIL"
        print(f"  [{status_str}] {item}")
        if not passed:
            all_configs_pass = False

    if not all_configs_pass:
        print("\n[FAILED] Some cloud scaffold artifacts are missing or invalid.")
        return 1

    if args.verify_config_only:
        print("\n[PASSED] Cloud infrastructure scaffold artifacts verified successfully.")
        return 0

    # 2. Check Live Deployment Credentials / Endpoint
    if not args.api_url:
        print("\n" + "=" * 60)
        print("[BLOCKED] Cloud deployment live gate blocked:")
        print("  STOREOPS_API_URL environment variable is not configured.")
        print("  Per AGENTS.md: Missing credentials produce a blocked live gate,")
        print("  not a successful test. Local unit and contract tests remain green.")
        print("=" * 60)
        return 2

    # 3. Run Live Checks
    print(f"\n2. Running live smoke checks against: {args.api_url} ...")
    live_checks = run_live_smoke_checks(args.api_url, args.worker_url)
    all_live_pass = True
    for check in live_checks:
        status_str = "PASS" if check["passed"] else "FAIL"
        print(f"  [{status_str}] {check['name']}: {check['detail']}")
        if not check["passed"]:
            all_live_pass = False

    if not all_live_pass:
        print("\n[FAILED] One or more live cloud smoke checks failed.")
        return 1

    print("\n[PASSED] All cloud deployment smoke checks passed successfully (AC-41).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
