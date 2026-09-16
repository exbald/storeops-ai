#!/usr/bin/env python3
"""StoreOps workspace bootstrap and member provisioning CLI."""

import argparse
import asyncio
from pathlib import Path
import sys
from datetime import datetime, timezone
from uuid import UUID, uuid4

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storeops_contracts.models import Currency, Workspace

from apps.api.adapters.state.firestore import FirestoreStateRepository
from apps.api.adapters.state.in_memory import InMemoryStateRepository
from apps.api.core.config import settings
from apps.api.ports.state import StateRepository


def get_repository() -> StateRepository:
    if settings.state_backend == "firestore":
        return FirestoreStateRepository()
    return InMemoryStateRepository()


async def bootstrap_workspace(
    repo: StateRepository,
    workspace_name: str,
    brand_name: str,
    currency_str: str,
    admin_uid: str,
    admin_email: str | None = None,
) -> tuple[Workspace, str]:
    now = datetime.now(timezone.utc)
    ws_id = uuid4()
    currency = Currency(currency_str.upper())

    workspace = Workspace(
        id=ws_id,
        workspace_id=ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        name=workspace_name,
        brand_name=brand_name,
        currency=currency,
    )

    membership = await repo.create_workspace_with_admin(
        workspace=workspace,
        uid=admin_uid,
        email=admin_email,
    )
    return workspace, membership.role


async def add_workspace_member(
    repo: StateRepository,
    workspace_id: UUID,
    uid: str,
    role: str,
    email: str | None = None,
) -> None:
    await repo.add_membership(
        workspace_id=workspace_id,
        uid=uid,
        role=role.upper(),
        email=email,
    )


def main():
    parser = argparse.ArgumentParser(description="StoreOps Bootstrap CLI")
    parser.add_argument("--add-member", action="store_true", help="Add member mode")
    parser.add_argument("--workspace-id", type=str, help="Workspace UUID (required for --add-member)")
    parser.add_argument("--workspace-name", type=str, default="Default Workspace", help="Workspace Name")
    parser.add_argument("--brand-name", type=str, default="Default Brand", help="Brand Name")
    parser.add_argument("--currency", type=str, default="SGD", choices=["SGD", "USD", "AUD"], help="Currency")
    parser.add_argument("--admin-uid", type=str, default="admin-uid-1", help="Firebase UID for first admin")
    parser.add_argument("--uid", type=str, help="Firebase UID to add")
    parser.add_argument("--role", type=str, default="REP", choices=["ADMIN", "REP"], help="Role for member")
    parser.add_argument("--email", type=str, help="User email")

    args = parser.parse_args()
    repo = get_repository()

    if args.add_member:
        if not args.workspace_id or not args.uid:
            print("Error: --workspace-id and --uid are required for --add-member", file=sys.stderr)
            sys.exit(1)
        asyncio.run(
            add_workspace_member(
                repo=repo,
                workspace_id=UUID(args.workspace_id),
                uid=args.uid,
                role=args.role,
                email=args.email,
            )
        )
        print(f"Successfully added user '{args.uid}' with role '{args.role}' to workspace '{args.workspace_id}'.")
    else:
        ws, role = asyncio.run(
            bootstrap_workspace(
                repo=repo,
                workspace_name=args.workspace_name,
                brand_name=args.brand_name,
                currency_str=args.currency,
                admin_uid=args.admin_uid,
                admin_email=args.email,
            )
        )
        print(f"Successfully bootstrapped workspace '{ws.name}' ({ws.id}) with admin '{args.admin_uid}'.")
        print(f"Currency: {ws.currency.value}, Brand: {ws.brand_name}")


if __name__ == "__main__":
    main()
