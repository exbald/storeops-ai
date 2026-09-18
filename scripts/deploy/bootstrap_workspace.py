#!/usr/bin/env python3
"""Bootstrap initial workspace and admin/rep memberships in Firestore.

Enables immediate authenticated usage of StoreOps web dashboard and API
on Cloud Run.
"""

import asyncio
import os
from datetime import datetime, timezone
from uuid import UUID

from storeops_contracts.models import Currency, Workspace

from apps.api.adapters.state.firestore import FirestoreStateRepository


async def main() -> None:
    project_id = os.getenv("STOREOPS_PROJECT_ID") or os.getenv("GCP_PROJECT") or "storeops-ai"
    print(f"Connecting to Firestore in project: {project_id}...")

    repo = FirestoreStateRepository(project_id=project_id)
    ws_id = UUID("00000000-0000-0000-0000-000000000001")

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
            name="StoreOps Retail Demo",
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
