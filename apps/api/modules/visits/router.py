import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from storeops_contracts.models import (
    ActionUpdate,
    Dismiss,
    Evidence,
    EvidenceList,
    Investigation,
    InvestigationCreate,
    InvestigationList,
    Job,
    Report,
    VersionCommand,
    Visit,
    VisitCreate,
    VisitList,
    VisitUpdate,
)

from apps.api.core.auth import (
    WorkspaceContext,
    get_state_repository,
    require_workspace,
)
from apps.api.modules.visits.dependencies import get_visit_service
from apps.api.modules.visits.service import VisitService
from apps.api.ports.state import StateRepository

router = APIRouter()
require_rep = require_workspace(required_role="REP")


# --- Visits Endpoints ---


@router.post(
    "/visits",
    response_model=Visit,
    status_code=status.HTTP_201_CREATED,
    operation_id="createVisit",
    tags=["Visits"],
)
async def create_visit(
    request: Request,
    payload: VisitCreate,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[VisitService, Depends(get_visit_service)],
    state_repo: Annotated[StateRepository, Depends(get_state_repository)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Visit:
    raw_body = await request.body()
    body_hash = hashlib.sha256(raw_body).hexdigest()
    is_cached, cached_data = await state_repo.check_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route="/visits",
        key=idempotency_key,
        body_hash=body_hash,
    )
    if is_cached and cached_data:
        cached_body = cached_data.get("body", cached_data)
        return Visit.model_validate(cached_body)

    visit = await service.create_visit(
        workspace_id=ctx.workspace_id,
        payload=payload,
        uid=ctx.user.uid,
    )

    await state_repo.save_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route="/visits",
        key=idempotency_key,
        body_hash=body_hash,
        status_code=201,
        response_body=visit.model_dump(mode="json"),
    )
    return visit


@router.get(
    "/visits",
    response_model=VisitList,
    operation_id="listVisits",
    tags=["Visits"],
)
async def list_visits(
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[VisitService, Depends(get_visit_service)],
    store_id: Annotated[UUID | None, Query()] = None,
    cursor: Annotated[str | None, Query(min_length=1, max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> VisitList:
    return await service.list_visits(
        workspace_id=ctx.workspace_id,
        store_id=store_id,
        cursor=cursor,
        limit=limit,
    )


@router.get(
    "/visits/{visit_id}",
    response_model=Visit,
    operation_id="getVisit",
    tags=["Visits"],
)
async def get_visit(
    visit_id: UUID,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[VisitService, Depends(get_visit_service)],
) -> Visit:
    return await service.get_visit(ctx.workspace_id, visit_id)


@router.patch(
    "/visits/{visit_id}",
    response_model=Visit,
    operation_id="updateVisit",
    tags=["Visits"],
)
async def update_visit(
    visit_id: UUID,
    payload: VisitUpdate,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[VisitService, Depends(get_visit_service)],
) -> Visit:
    return await service.update_visit(
        workspace_id=ctx.workspace_id,
        visit_id=visit_id,
        payload=payload,
        uid=ctx.user.uid,
    )


# --- Investigations Endpoints ---


@router.post(
    "/investigations",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="createInvestigation",
    tags=["Investigations"],
)
async def create_investigation(
    request: Request,
    payload: InvestigationCreate,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[VisitService, Depends(get_visit_service)],
    state_repo: Annotated[StateRepository, Depends(get_state_repository)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Job:
    raw_body = await request.body()
    body_hash = hashlib.sha256(raw_body).hexdigest()
    is_cached, cached_data = await state_repo.check_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route="/investigations",
        key=idempotency_key,
        body_hash=body_hash,
    )
    if is_cached and cached_data:
        cached_body = cached_data.get("body", cached_data)
        return Job.model_validate(cached_body)

    job = await service.create_investigation(
        workspace_id=ctx.workspace_id,
        payload=payload,
        uid=ctx.user.uid,
    )

    await state_repo.save_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route="/investigations",
        key=idempotency_key,
        body_hash=body_hash,
        status_code=202,
        response_body=job.model_dump(mode="json"),
    )
    return job


@router.get(
    "/investigations",
    response_model=InvestigationList,
    operation_id="listInvestigations",
    tags=["Investigations"],
)
async def list_investigations(
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[VisitService, Depends(get_visit_service)],
    store_id: Annotated[UUID | None, Query()] = None,
    visit_id: Annotated[UUID | None, Query()] = None,
    cursor: Annotated[str | None, Query(min_length=1, max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> InvestigationList:
    return await service.list_investigations(
        workspace_id=ctx.workspace_id,
        store_id=store_id,
        visit_id=visit_id,
        cursor=cursor,
        limit=limit,
    )


@router.get(
    "/investigations/{investigation_id}",
    response_model=Investigation,
    operation_id="getInvestigation",
    tags=["Investigations"],
)
async def get_investigation(
    investigation_id: UUID,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[VisitService, Depends(get_visit_service)],
) -> Investigation:
    return await service.get_investigation(ctx.workspace_id, investigation_id)


@router.post(
    "/investigations/{investigation_id}/accept",
    response_model=Investigation,
    operation_id="acceptInvestigation",
    tags=["Investigations"],
)
async def accept_investigation(
    request: Request,
    investigation_id: UUID,
    payload: VersionCommand,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[VisitService, Depends(get_visit_service)],
    state_repo: Annotated[StateRepository, Depends(get_state_repository)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Investigation:
    raw_body = await request.body()
    body_hash = hashlib.sha256(raw_body).hexdigest()
    route_path = f"/investigations/{investigation_id}/accept"
    is_cached, cached_data = await state_repo.check_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route=route_path,
        key=idempotency_key,
        body_hash=body_hash,
    )
    if is_cached and cached_data:
        cached_body = cached_data.get("body", cached_data)
        return Investigation.model_validate(cached_body)

    inv = await service.accept_investigation(
        workspace_id=ctx.workspace_id,
        investigation_id=investigation_id,
        payload=payload,
        uid=ctx.user.uid,
    )

    await state_repo.save_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route=route_path,
        key=idempotency_key,
        body_hash=body_hash,
        status_code=200,
        response_body=inv.model_dump(mode="json"),
    )
    return inv


@router.post(
    "/investigations/{investigation_id}/dismiss",
    response_model=Investigation,
    operation_id="dismissInvestigation",
    tags=["Investigations"],
)
async def dismiss_investigation(
    request: Request,
    investigation_id: UUID,
    payload: Dismiss,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[VisitService, Depends(get_visit_service)],
    state_repo: Annotated[StateRepository, Depends(get_state_repository)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Investigation:
    raw_body = await request.body()
    body_hash = hashlib.sha256(raw_body).hexdigest()
    route_path = f"/investigations/{investigation_id}/dismiss"
    is_cached, cached_data = await state_repo.check_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route=route_path,
        key=idempotency_key,
        body_hash=body_hash,
    )
    if is_cached and cached_data:
        cached_body = cached_data.get("body", cached_data)
        return Investigation.model_validate(cached_body)

    inv = await service.dismiss_investigation(
        workspace_id=ctx.workspace_id,
        investigation_id=investigation_id,
        payload=payload,
        uid=ctx.user.uid,
    )

    await state_repo.save_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route=route_path,
        key=idempotency_key,
        body_hash=body_hash,
        status_code=200,
        response_body=inv.model_dump(mode="json"),
    )
    return inv


@router.patch(
    "/investigations/{investigation_id}/actions/{action_id}",
    response_model=Investigation,
    operation_id="updateAction",
    tags=["Investigations"],
)
async def update_action(
    investigation_id: UUID,
    action_id: UUID,
    payload: ActionUpdate,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[VisitService, Depends(get_visit_service)],
) -> Investigation:
    return await service.update_action(
        workspace_id=ctx.workspace_id,
        investigation_id=investigation_id,
        action_id=action_id,
        payload=payload,
        uid=ctx.user.uid,
    )


# --- Evidence Endpoints ---


@router.get(
    "/investigations/{investigation_id}/evidence",
    response_model=EvidenceList,
    operation_id="listEvidence",
    tags=["Evidence"],
)
async def list_evidence(
    investigation_id: UUID,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[VisitService, Depends(get_visit_service)],
    cursor: Annotated[str | None, Query(min_length=1, max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> EvidenceList:
    return await service.list_evidence(
        workspace_id=ctx.workspace_id,
        investigation_id=investigation_id,
        cursor=cursor,
        limit=limit,
    )


@router.get(
    "/evidence/{evidence_id}",
    response_model=Evidence,
    operation_id="getEvidence",
    tags=["Evidence"],
)
async def get_evidence(
    evidence_id: UUID,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[VisitService, Depends(get_visit_service)],
) -> Evidence:
    return await service.get_evidence(
        workspace_id=ctx.workspace_id,
        evidence_id=evidence_id,
    )


# --- Reports Endpoints ---


@router.get(
    "/reports/{report_id}",
    response_model=Report,
    operation_id="getReport",
    tags=["Reports"],
)
async def get_report(
    report_id: UUID,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[VisitService, Depends(get_visit_service)],
) -> Report:
    return await service.get_report(
        workspace_id=ctx.workspace_id,
        report_id=report_id,
    )
