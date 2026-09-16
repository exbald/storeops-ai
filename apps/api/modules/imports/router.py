import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from storeops_contracts.models import (
    Import,
    ImportCreate,
    ImportList,
    Job,
    StoreHealth,
    VersionCommand,
)

from apps.api.core.auth import (
    WorkspaceContext,
    get_state_repository,
    require_workspace,
)
from apps.api.core.errors import ApiError
from apps.api.modules.imports.dependencies import get_import_service
from apps.api.modules.imports.service import (
    ConflictError,
    ImportService,
    ImportServiceError,
    NotFoundError,
    ValidationError,
)
from apps.api.ports.state import StateRepository

router = APIRouter()

require_rep = require_workspace(required_role="REP")
require_admin = require_workspace(required_role="ADMIN")


def _map_service_error(e: ImportServiceError) -> ApiError:
    if isinstance(e, NotFoundError):
        return ApiError(status_code=404, code="NOT_FOUND", message=e.message)
    if isinstance(e, ConflictError):
        return ApiError(status_code=409, code="CONFLICT", message=e.message)
    if isinstance(e, ValidationError):
        return ApiError(status_code=422, code="UNPROCESSABLE_ENTITY", message=e.message)
    return ApiError(status_code=e.status_code, code="BAD_REQUEST", message=e.message)


# ==============================================================================
# Imports endpoints
# ==============================================================================


@router.get(
    "/imports",
    response_model=ImportList,
    operation_id="listImports",
    tags=["Imports"],
)
async def list_imports(
    ctx: Annotated[WorkspaceContext, Depends(require_admin)],
    service: Annotated[ImportService, Depends(get_import_service)],
    cursor: Annotated[str | None, Query(min_length=1, max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ImportList:
    items, next_cursor = await service.list_imports(
        workspace_id=ctx.workspace_id,
        cursor=cursor,
        limit=limit,
    )
    return ImportList(items=items, next_cursor=next_cursor)


@router.post(
    "/imports",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="createImport",
    tags=["Imports"],
)
async def create_import(
    request: Request,
    payload: ImportCreate,
    ctx: Annotated[WorkspaceContext, Depends(require_admin)],
    service: Annotated[ImportService, Depends(get_import_service)],
    state_repo: Annotated[StateRepository, Depends(get_state_repository)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Job:
    raw_body = await request.body()
    body_hash = hashlib.sha256(raw_body).hexdigest()
    is_cached, cached_data = await state_repo.check_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route="/imports",
        key=idempotency_key,
        body_hash=body_hash,
    )
    if is_cached and cached_data:
        cached_body = cached_data.get("body", cached_data)
        return Job.model_validate(cached_body)

    try:
        job = await service.create_import(
            workspace_id=ctx.workspace_id,
            payload=payload,
            user_id=ctx.user.uid,
        )
    except ImportServiceError as e:
        raise _map_service_error(e) from e

    await state_repo.save_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route="/imports",
        key=idempotency_key,
        body_hash=body_hash,
        status_code=202,
        response_body=job.model_dump(mode="json"),
    )
    return job


@router.get(
    "/imports/{import_id}",
    response_model=Import,
    operation_id="getImport",
    tags=["Imports"],
)
async def get_import(
    import_id: UUID,
    ctx: Annotated[WorkspaceContext, Depends(require_admin)],
    service: Annotated[ImportService, Depends(get_import_service)],
) -> Import:
    try:
        return await service.get_import(
            workspace_id=ctx.workspace_id, import_id=import_id
        )
    except ImportServiceError as e:
        raise _map_service_error(e) from e


@router.post(
    "/imports/{import_id}/commit",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="commitImport",
    tags=["Imports"],
)
async def commit_import(
    request: Request,
    import_id: UUID,
    payload: VersionCommand,
    ctx: Annotated[WorkspaceContext, Depends(require_admin)],
    service: Annotated[ImportService, Depends(get_import_service)],
    state_repo: Annotated[StateRepository, Depends(get_state_repository)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Job:
    raw_body = await request.body()
    body_hash = hashlib.sha256(raw_body).hexdigest()
    route = f"/imports/{import_id}/commit"
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
        job = await service.commit_import(
            workspace_id=ctx.workspace_id,
            import_id=import_id,
            command=payload,
            user_id=ctx.user.uid,
        )
    except ImportServiceError as e:
        raise _map_service_error(e) from e

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


# ==============================================================================
# Store Health endpoint
# ==============================================================================


@router.get(
    "/stores/{store_id}/health",
    response_model=StoreHealth,
    operation_id="getStoreHealth",
    tags=["Stores"],
)
async def get_store_health(
    store_id: UUID,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[ImportService, Depends(get_import_service)],
) -> StoreHealth:
    try:
        return await service.get_store_health(
            workspace_id=ctx.workspace_id, store_id=store_id
        )
    except ImportServiceError as e:
        raise _map_service_error(e) from e
