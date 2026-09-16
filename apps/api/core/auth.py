from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from storeops_contracts.models import Membership

from apps.api.core.config import settings
from apps.api.core.errors import ApiError
from apps.api.ports.identity import AuthError, IdentityVerifier
from apps.api.ports.state import StateRepository


@dataclass
class UserContext:
    uid: str
    email: str | None = None


@dataclass
class WorkspaceContext:
    workspace_id: UUID
    membership: Membership
    user: UserContext


class EmulatorIdentityVerifier(IdentityVerifier):
    async def verify_token(self, token: str) -> tuple[str, str | None]:
        if settings.is_production:
            raise AuthError("Emulator identity verifier is forbidden in production", code="CONFIG_ERROR")
        if not token:
            raise AuthError("Missing authentication token", code="UNAUTHORIZED")

        # In dev/test mode: allow Bearer <uid> or Bearer test-<role>-<uid>
        uid = token.strip()
        email = f"{uid}@example.com"
        return uid, email


# Singleton instances configured at startup / dependency injection
_identity_verifier: IdentityVerifier = EmulatorIdentityVerifier()
_state_repository: StateRepository | None = None


def get_identity_verifier() -> IdentityVerifier:
    return _identity_verifier


def set_identity_verifier(verifier: IdentityVerifier) -> None:
    global _identity_verifier
    _identity_verifier = verifier


def get_state_repository() -> StateRepository:
    if _state_repository is None:
        raise RuntimeError("StateRepository has not been initialized")
    return _state_repository


def set_state_repository(repo: StateRepository) -> None:
    global _state_repository
    _state_repository = repo


async def get_current_user(
    request: Request,
    verifier: Annotated[IdentityVerifier, Depends(get_identity_verifier)],
    authorization: Annotated[str | None, Header()] = None,
) -> UserContext:
    if not authorization:
        # Check X-Test-Uid in dev/test mode
        if not settings.is_production:
            test_uid = request.headers.get("X-Test-Uid")
            if test_uid:
                return UserContext(uid=test_uid, email=f"{test_uid}@example.com")
        raise ApiError(status_code=401, code="UNAUTHORIZED", message="Authorization header required")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise ApiError(status_code=401, code="UNAUTHORIZED", message="Invalid Authorization header format. Expected Bearer <token>")

    token = parts[1]
    try:
        uid, email = await verifier.verify_token(token)
        return UserContext(uid=uid, email=email)
    except AuthError as e:
        raise ApiError(status_code=401, code=e.code, message=e.message)


def require_workspace(required_role: str = "REP"):
    async def _require_workspace(
        user: Annotated[UserContext, Depends(get_current_user)],
        state_repo: Annotated[StateRepository, Depends(get_state_repository)],
        x_workspace_id: Annotated[UUID | None, Header(alias="X-Workspace-Id")] = None,
    ) -> WorkspaceContext:
        if not x_workspace_id:
            raise ApiError(status_code=400, code="MISSING_WORKSPACE", message="X-Workspace-Id header is required")

        membership = await state_repo.get_membership(x_workspace_id, user.uid)
        if not membership:
            raise ApiError(
                status_code=403,
                code="FORBIDDEN",
                message="User is not a member of the requested workspace",
            )

        role_val = membership.role.value if hasattr(membership.role, "value") else str(membership.role)
        if required_role == "ADMIN" and role_val != "ADMIN":
            raise ApiError(
                status_code=403,
                code="FORBIDDEN",
                message="Admin role is required for this action",
            )

        return WorkspaceContext(
            workspace_id=x_workspace_id,
            membership=membership,
            user=user,
        )

    return _require_workspace
