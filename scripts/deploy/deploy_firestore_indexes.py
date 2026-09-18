#!/usr/bin/env python3
"""Deploy Firestore composite indexes from infra/firestore.indexes.json using gcloud.

Idempotent: skips indexes that already exist or are in the process of being created.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
INDEXES_FILE = ROOT_DIR / "infra" / "firestore.indexes.json"


def deploy_indexes(project_id: str) -> bool:
    if not INDEXES_FILE.exists():
        print(f"ERROR: Indexes file not found: {INDEXES_FILE}", file=sys.stderr)
        return False

    with open(INDEXES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    indexes = data.get("indexes", [])
    print(f"Deploying {len(indexes)} Firestore composite indexes to project: {project_id}...")

    success = True
    for i, idx in enumerate(indexes, 1):
        cg = idx["collectionGroup"]
        qs = idx.get("queryScope", "COLLECTION").lower()
        fields = idx["fields"]

        cmd = [
            "gcloud",
            "firestore",
            "indexes",
            "composite",
            "create",
            f"--collection-group={cg}",
            f"--query-scope={qs}",
            "--async",
            f"--project={project_id}",
        ]

        for f_item in fields:
            fp = f_item["fieldPath"]
            order = f_item.get("order", "ASCENDING").lower()
            cmd.append(f"--field-config=field-path={fp},order={order}")

        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = (res.stdout + " " + res.stderr).strip()

        if res.returncode == 0 or "Create request issued" in output:
            print(f"  [{i}/{len(indexes)}] ✓ Created/Queued: {cg} ({', '.join(f['fieldPath'] for f in fields)})")
        elif "ALREADY_EXISTS" in output or "already exists" in output:
            print(f"  [{i}/{len(indexes)}] = Already exists: {cg} ({', '.join(f['fieldPath'] for f in fields)})")
        else:
            print(f"  [{i}/{len(indexes)}] ✗ Failed: {cg}: {output}", file=sys.stderr)
            success = False

    return success


if __name__ == "__main__":
    project = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.getenv("STOREOPS_PROJECT_ID") or os.getenv("GCP_PROJECT") or ""
    )
    if not project:
        print("ERROR: Project ID must be provided as argument or in STOREOPS_PROJECT_ID/GCP_PROJECT", file=sys.stderr)
        sys.exit(1)

    ok = deploy_indexes(project)
    sys.exit(0 if ok else 1)
