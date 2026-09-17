import hashlib
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Path, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from storeops_contracts.models import (
    AiMode,
    Health,
    Job,
    JobEvents,
    Me,
    Profile,
    Status,
    Workspace,
)

from apps.api.adapters.state.firestore import FirestoreStateRepository
from apps.api.adapters.state.in_memory import InMemoryStateRepository
from apps.api.core.auth import (
    UserContext,
    WorkspaceContext,
    get_current_user,
    get_state_repository,
    require_workspace,
    set_state_repository,
)
from apps.api.core.config import settings
from apps.api.core.errors import (
    ApiError,
    api_error_handler,
    auth_error_handler,
    http_exception_handler,
    validation_error_handler,
    version_conflict_handler,
)
from apps.api.ports.identity import AuthError
from apps.api.ports.state import StateRepository, VersionConflictError
from apps.api.modules.catalog.router import router as catalog_router
from apps.api.modules.imports.router import router as imports_router
from apps.api.modules.policies.router import router as policies_router
from apps.api.modules.visits.router import router as visits_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize StateRepository if not already set (e.g. by tests)
    try:
        get_state_repository()
    except RuntimeError:
        if settings.state_backend == "firestore":
            repo = FirestoreStateRepository()
        else:
            repo = InMemoryStateRepository()
        set_state_repository(repo)
    yield


app = FastAPI(
    title="StoreOps API",
    version="2.0.0",
    lifespan=lifespan,
)

# Exception handlers
app.add_exception_handler(ApiError, api_error_handler)  # type: ignore
app.add_exception_handler(VersionConflictError, version_conflict_handler)  # type: ignore
app.add_exception_handler(AuthError, auth_error_handler)  # type: ignore
app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore
app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-Id")
    try:
        request.state.request_id = UUID(req_id) if req_id else uuid4()
    except ValueError:
        request.state.request_id = uuid4()

    response = await call_next(request)
    response.headers["X-Request-Id"] = str(request.state.request_id)
    return response


# --- 1. Health ---
@app.get(
    "/health",
    response_model=Health,
    operation_id="getHealth",
    tags=["System"],
)
async def get_health() -> Health:
    return Health(
        status=Status.READY,
        profile=Profile.CLOUD if settings.profile == "CLOUD" else Profile.LOCAL,
        ai_mode=AiMode.LIVE if settings.ai_mode == "LIVE" else AiMode.STUB,
    )


# --- 2. Me ---
@app.get(
    "/me",
    response_model=Me,
    operation_id="getMe",
    tags=["Identity"],
)
async def get_me(
    user: UserContext = Depends(get_current_user),
    state_repo: StateRepository = Depends(get_state_repository),
) -> Me:
    memberships = await state_repo.get_memberships_for_user(user.uid)
    return Me(
        uid=user.uid,
        memberships=memberships,
    )


# --- 3. Workspace ---
@app.get(
    "/workspace",
    response_model=Workspace,
    operation_id="getWorkspace",
    tags=["Identity"],
)
async def get_workspace(
    ctx: WorkspaceContext = Depends(require_workspace(required_role="REP")),
    state_repo: StateRepository = Depends(get_state_repository),
) -> Workspace:
    ws = await state_repo.get_workspace(ctx.workspace_id)
    if not ws:
        raise ApiError(status_code=404, code="NOT_FOUND", message="Workspace not found")
    return ws


# --- 4. Jobs ---
@app.get(
    "/jobs/{job_id}",
    response_model=Job,
    operation_id="getJob",
    tags=["Jobs"],
)
async def get_job(
    job_id: Annotated[UUID, Path()],
    ctx: WorkspaceContext = Depends(require_workspace(required_role="REP")),
    state_repo: StateRepository = Depends(get_state_repository),
) -> Job:
    job = await state_repo.get_job(ctx.workspace_id, job_id)
    if not job:
        raise ApiError(status_code=404, code="NOT_FOUND", message=f"Job {job_id} not found in workspace")
    return job


@app.get(
    "/jobs/{job_id}/events",
    response_model=JobEvents,
    operation_id="getJobEvents",
    tags=["Jobs"],
)
async def get_job_events(
    job_id: Annotated[UUID, Path()],
    after_sequence: Annotated[int | None, Query()] = None,
    ctx: WorkspaceContext = Depends(require_workspace(required_role="REP")),
    state_repo: StateRepository = Depends(get_state_repository),
) -> JobEvents:
    job = await state_repo.get_job(ctx.workspace_id, job_id)
    if not job:
        raise ApiError(status_code=404, code="NOT_FOUND", message=f"Job {job_id} not found in workspace")

    events = await state_repo.get_job_events(ctx.workspace_id, job_id)
    if after_sequence is not None:
        events = [e for e in events if e.sequence > after_sequence]

    last_seq = events[-1].sequence if events else (after_sequence or 0)
    return JobEvents(items=events, last_sequence=last_seq)


@app.post(
    "/jobs/{job_id}/retry",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="retryJob",
    tags=["Jobs"],
)
async def retry_job(
    job_id: Annotated[UUID, Path()],
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ctx: WorkspaceContext = Depends(require_workspace(required_role="REP")),
    state_repo: StateRepository = Depends(get_state_repository),
) -> Job:
    # Idempotency check
    body_bytes = await request.body()
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    is_replayed, cached_resp = await state_repo.check_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route=f"/jobs/{job_id}/retry",
        key=idempotency_key,
        body_hash=body_hash,
    )
    if is_replayed and cached_resp:
        return Job.model_validate(cached_resp["body"])

    existing_job = await state_repo.get_job(ctx.workspace_id, job_id)
    if not existing_job:
        raise ApiError(status_code=404, code="NOT_FOUND", message=f"Job {job_id} not found in workspace")

    if existing_job.status.value != "FAILED":
        raise ApiError(
            status_code=409,
            code="JOB_NOT_FAILED",
            message=f"Job {job_id} is in status {existing_job.status.value}, not FAILED",
        )

    # retryJob is allowed for FAILED INVESTIGATE or POLICY_EXTRACT jobs only
    job_type_str = existing_job.type.value if hasattr(existing_job.type, "value") else str(existing_job.type)
    if job_type_str not in ["INVESTIGATION", "POLICY_EXTRACT", "INVESTIGATE"]:
        raise ApiError(
            status_code=409,
            code="RETRY_WITH_RESOURCE_COMMAND",
            message=f"Direct retry is not supported for job type {job_type_str}. Use resource-specific retry command.",
        )

    # Create new linked job
    new_job_id = uuid4()
    now_dt = datetime.now(UTC)

    retried_job = Job(
        id=new_job_id,
        workspace_id=ctx.workspace_id,
        version=1,
        created_at=now_dt,
        updated_at=now_dt,
        type=existing_job.type,
        status=existing_job.status.__class__.QUEUED,
        resource_id=existing_job.resource_id,
        resource_type=existing_job.resource_type,
        attempt=existing_job.attempt + 1,
        stage="QUEUED",
        started_at=None,
        finished_at=None,
        error=None,
        linked_previous_job_id=existing_job.id,
        model_id=existing_job.model_id,
        usage=None,
    )
    await state_repo.create_job_with_outbox(retried_job, outbox_payload={"retried_from": str(existing_job.id)})

    # Record idempotency
    await state_repo.save_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route=f"/jobs/{job_id}/retry",
        key=idempotency_key,
        body_hash=body_hash,
        status_code=202,
        response_body=retried_job.model_dump(mode="json"),
    )
    return retried_job


# Mount module routers
app.include_router(catalog_router)
app.include_router(imports_router)
app.include_router(policies_router)
app.include_router(visits_router)

