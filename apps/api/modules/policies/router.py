import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from storeops_contracts.models import (
    ApprovePolicy,
    Job,
    PolicyVersion,
    PolicyVersionList,
    Promotion,
    PromotionCreate,
    PromotionList,
    PromotionUpdate,
    VersionCommand,
)

from apps.api.core.auth import (
    WorkspaceContext,
    get_state_repository,
    require_workspace,
)
from apps.api.core.errors import ApiError
from apps.api.modules.policies.dependencies import get_policy_service
from apps.api.modules.policies.service import (
    PolicyService,
    PolicyServiceError,
)
from apps.api.ports.state import StateRepository

router = APIRouter()

require_rep = require_workspace(required_role="REP")
require_admin = require_workspace(required_role="ADMIN")


@router.get(
    "/promotions",
    response_model=PromotionList,
    operation_id="listPromotions",
    tags=["Policies"],
)
async def list_promotions(
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[PolicyService, Depends(get_policy_service)],
    cursor: Annotated[str | None, Query(min_length=1, max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PromotionList:
    return await service.list_promotions(
        workspace_id=ctx.workspace_id,
        cursor=cursor,
        limit=limit,
    )


@router.post(
    "/promotions",
    response_model=Promotion,
    status_code=status.HTTP_201_CREATED,
    operation_id="createPromotion",
    tags=["Policies"],
)
async def create_promotion(
    request: Request,
    payload: PromotionCreate,
    ctx: Annotated[WorkspaceContext, Depends(require_admin)],
    service: Annotated[PolicyService, Depends(get_policy_service)],
    state_repo: Annotated[StateRepository, Depends(get_state_repository)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Promotion:
    raw_body = await request.body()
    body_hash = hashlib.sha256(raw_body).hexdigest()
    is_cached, cached_data = await state_repo.check_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route="/promotions",
        key=idempotency_key,
        body_hash=body_hash,
    )
    if is_cached and cached_data:
        cached_body = cached_data.get("body", cached_data)
        return Promotion.model_validate(cached_body)

    try:
        promo = await service.create_promotion(ctx.workspace_id, payload)
    except PolicyServiceError as e:
        raise ApiError(status_code=e.status_code, code=e.code, message=e.message)

    await state_repo.save_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route="/promotions",
        key=idempotency_key,
        body_hash=body_hash,
        status_code=201,
        response_body=promo.model_dump(mode="json"),
    )
    return promo


@router.get(
    "/promotions/{promotion_id}",
    response_model=Promotion,
    operation_id="getPromotion",
    tags=["Policies"],
)
async def get_promotion(
    promotion_id: UUID,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[PolicyService, Depends(get_policy_service)],
) -> Promotion:
    try:
        return await service.get_promotion(ctx.workspace_id, promotion_id)
    except PolicyServiceError as e:
        raise ApiError(status_code=e.status_code, code=e.code, message=e.message)


@router.patch(
    "/promotions/{promotion_id}",
    response_model=Promotion,
    operation_id="updatePromotion",
    tags=["Policies"],
)
async def update_promotion(
    promotion_id: UUID,
    payload: PromotionUpdate,
    ctx: Annotated[WorkspaceContext, Depends(require_admin)],
    service: Annotated[PolicyService, Depends(get_policy_service)],
) -> Promotion:
    try:
        return await service.update_promotion(ctx.workspace_id, promotion_id, payload)
    except PolicyServiceError as e:
        raise ApiError(status_code=e.status_code, code=e.code, message=e.message)


@router.post(
    "/promotions/{promotion_id}/extract",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="extractPolicy",
    tags=["Policies"],
)
async def extract_policy(
    request: Request,
    promotion_id: UUID,
    payload: VersionCommand,
    ctx: Annotated[WorkspaceContext, Depends(require_admin)],
    service: Annotated[PolicyService, Depends(get_policy_service)],
    state_repo: Annotated[StateRepository, Depends(get_state_repository)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Job:
    raw_body = await request.body()
    body_hash = hashlib.sha256(raw_body).hexdigest()
    route = f"/promotions/{promotion_id}/extract"
    is_cached, cached_data = await state_repo.check_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route=route,
        key=idempotency_key,
        body_hash=body_hash,
    )
    if is_cached and cached_data:
        cached_body = cached_data.get("body", cached_data)
        return Job.model_validate(cached_body)

    try:
        job = await service.extract_policy(
            workspace_id=ctx.workspace_id,
            promotion_id=promotion_id,
            expected_version=payload.expected_version,
            uid=ctx.user.uid,
        )
    except PolicyServiceError as e:
        raise ApiError(status_code=e.status_code, code=e.code, message=e.message)

    await state_repo.save_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route=route,
        key=idempotency_key,
        body_hash=body_hash,
        status_code=202,
        response_body=job.model_dump(mode="json"),
    )
    return job


@router.post(
    "/promotions/{promotion_id}/approve",
    response_model=PolicyVersion,
    status_code=status.HTTP_201_CREATED,
    operation_id="approvePolicy",
    tags=["Policies"],
)
async def approve_policy(
    request: Request,
    promotion_id: UUID,
    payload: ApprovePolicy,
    ctx: Annotated[WorkspaceContext, Depends(require_admin)],
    service: Annotated[PolicyService, Depends(get_policy_service)],
    state_repo: Annotated[StateRepository, Depends(get_state_repository)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> PolicyVersion:
    raw_body = await request.body()
    body_hash = hashlib.sha256(raw_body).hexdigest()
    route = f"/promotions/{promotion_id}/approve"
    is_cached, cached_data = await state_repo.check_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route=route,
        key=idempotency_key,
        body_hash=body_hash,
    )
    if is_cached and cached_data:
        cached_body = cached_data.get("body", cached_data)
        return PolicyVersion.model_validate(cached_body)

    try:
        policy_version = await service.approve_policy(
            workspace_id=ctx.workspace_id,
            promotion_id=promotion_id,
            payload=payload,
            user_uid=ctx.user.uid,
        )
    except PolicyServiceError as e:
        raise ApiError(status_code=e.status_code, code=e.code, message=e.message)

    await state_repo.save_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route=route,
        key=idempotency_key,
        body_hash=body_hash,
        status_code=201,
        response_body=policy_version.model_dump(mode="json"),
    )
    return policy_version


@router.get(
    "/promotions/{promotion_id}/versions",
    response_model=PolicyVersionList,
    operation_id="listPolicyVersions",
    tags=["Policies"],
)
async def list_policy_versions(
    promotion_id: UUID,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[PolicyService, Depends(get_policy_service)],
    cursor: Annotated[str | None, Query(min_length=1, max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PolicyVersionList:
    try:
        return await service.list_policy_versions(
            workspace_id=ctx.workspace_id,
            promotion_id=promotion_id,
            cursor=cursor,
            limit=limit,
        )
    except PolicyServiceError as e:
        raise ApiError(status_code=e.status_code, code=e.code, message=e.message)
