"""FastAPI router for verification endpoints."""

import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from storeops_contracts.models import (
    Job,
    Verification,
    VerificationList,
    VerifyRequest,
)

from apps.api.core.auth import (
    WorkspaceContext,
    get_state_repository,
    require_workspace,
)
from apps.api.modules.verification.dependencies import get_verification_service
from apps.api.modules.verification.service import VerificationService
from apps.api.ports.state import StateRepository

router = APIRouter()
require_rep = require_workspace(required_role="REP")


@router.post(
    "/investigations/{investigation_id}/verify",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="verifyInvestigation",
    tags=["Verification"],
)
async def verify_investigation(
    investigation_id: UUID,
    payload: VerifyRequest,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[VerificationService, Depends(get_verification_service)],
    state_repo: Annotated[StateRepository, Depends(get_state_repository)],
    request: Request,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Job:
    """Submit after-action evidence to verify remediation against frozen policy rules."""
    if idempotency_key:
        raw_body = await request.body()
        body_hash = hashlib.sha256(raw_body).hexdigest()
        is_cached, cached_data = await state_repo.check_idempotency(
            uid=ctx.user.uid,
            method="POST",
            route=f"/investigations/{investigation_id}/verify",
            key=idempotency_key,
            body_hash=body_hash,
        )
        if is_cached and cached_data:
            cached_body = cached_data.get("body", cached_data)
            return Job.model_validate(cached_body)

    job = await service.verify_investigation(
        workspace_id=ctx.workspace_id,
        investigation_id=investigation_id,
        payload=payload,
        uid=ctx.user.uid,
    )

    if idempotency_key:
        raw_body = await request.body()
        body_hash = hashlib.sha256(raw_body).hexdigest()
        await state_repo.save_idempotency(
            uid=ctx.user.uid,
            method="POST",
            route=f"/investigations/{investigation_id}/verify",
            key=idempotency_key,
            body_hash=body_hash,
            status_code=202,
            response_body=job.model_dump(mode="json"),
        )

    return job


@router.get(
    "/investigations/{investigation_id}/verifications",
    response_model=VerificationList,
    status_code=status.HTTP_200_OK,
    operation_id="listVerifications",
    tags=["Verification"],
)
async def list_verifications(
    investigation_id: UUID,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[VerificationService, Depends(get_verification_service)],
    cursor: Annotated[str | None, Query(min_length=1, max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> VerificationList:
    """List verification attempts for an investigation."""
    return await service.list_verifications(
        workspace_id=ctx.workspace_id,
        investigation_id=investigation_id,
        cursor=cursor,
        limit=limit,
    )


@router.get(
    "/verifications/{verification_id}",
    response_model=Verification,
    status_code=status.HTTP_200_OK,
    operation_id="getVerification",
    tags=["Verification"],
)
async def get_verification(
    verification_id: UUID,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[VerificationService, Depends(get_verification_service)],
) -> Verification:
    """Fetch verification details including aggregate result and individual rule checks."""
    return await service.get_verification(
        workspace_id=ctx.workspace_id,
        verification_id=verification_id,
    )
