#!/usr/bin/env python3
"""Bootstrap initial workspace and admin/rep memberships in Firestore.

Enables immediate authenticated usage of StoreOps web dashboard and API
on Cloud Run.
"""

import argparse
import asyncio
import os
from datetime import datetime, timezone
from uuid import UUID

from storeops_contracts.models import Currency, Workspace

from apps.api.adapters.state.firestore import FirestoreStateRepository


DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a workspace and its demo memberships.")
    parser.add_argument("--workspace-id", default=DEFAULT_WORKSPACE_ID)
    parser.add_argument("--name", default="StoreOps Retail Demo")
    return parser


async def main() -> None:
    args = build_parser().parse_args()
    project_id = os.getenv("STOREOPS_PROJECT_ID") or os.getenv("GCP_PROJECT") or "storeops-ai"
    print(f"Connecting to Firestore in project: {project_id}...")

    repo = FirestoreStateRepository(project_id=project_id)
    ws_id = UUID(args.workspace_id)

    existing = await repo.get_workspace(ws_id)
    now = datetime.now(timezone.utc)
    if not existing:
        print(f"Creating default workspace: {ws_id}...")
        workspace = Workspace(
            id=ws_id,
            workspace_id=ws_id,
            version=1,
            created_at=now,
            updated_at=now,
            name=args.name,
            brand_name="AquaPure",
            currency=Currency.USD,
        )
        await repo.create_workspace_with_admin(
            workspace=workspace,
            uid="dev-admin-token",
            email="dev-admin@storeops.ai",
        )
        print("  ✓ Created workspace with admin: dev-admin-token")
    else:
        print(f"  ✓ Workspace {ws_id} already exists ({existing.name})")

    # Ensure admin & rep memberships exist
    users = [
        ("dev-admin-token", "ADMIN", "dev-admin@storeops.ai"),
        ("demo-admin", "ADMIN", "demo-admin@storeops.ai"),
        ("demo-rep", "REP", "demo-rep@storeops.ai"),
        ("exbald", "ADMIN", "exbald@gmail.com"),
    ]

    for uid, role, email in users:
        await repo.add_membership(ws_id, uid=uid, role=role, email=email)
        print(f"  ✓ Configured membership: {uid} -> {role}")

    print("Firestore workspace bootstrap complete!")


if __name__ == "__main__":
    asyncio.run(main())
