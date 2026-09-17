from typing import Annotated

from fastapi import Depends

from apps.api.ai.gateway import DeterministicModelGateway, GeminiGateway
from apps.api.core.auth import get_state_repository
from apps.api.core.config import settings
from apps.api.modules.catalog.dependencies import (
    get_blob_repository,
    get_catalog_repository,
)
from apps.api.modules.imports.dependencies import get_analytics_repository
from apps.api.modules.policies.dependencies import (
    get_policy_repository,
)
from apps.api.modules.visits.ports import VisitCatalogPort, VisitPolicyPort
from apps.api.modules.visits.repository import (
    InMemoryVisitRepository,
    VisitRepository,
)
from apps.api.modules.visits.service import VisitService
from apps.api.ports.analytics import AnalyticsRepository
from apps.api.ports.blob import BlobRepository
from apps.api.ports.clock import Clock, SystemClock
from apps.api.ports.model import ModelGateway
from apps.api.ports.state import StateRepository

_visit_repository: VisitRepository | None = None
_model_gateway: ModelGateway | None = None
_clock: Clock | None = None


def get_visit_repository() -> VisitRepository:
    global _visit_repository
    if _visit_repository is None:
        _visit_repository = InMemoryVisitRepository()
    return _visit_repository


def set_visit_repository(repo: VisitRepository) -> None:
    global _visit_repository
    _visit_repository = repo


def get_model_gateway() -> ModelGateway:
    global _model_gateway
    if _model_gateway is None:
        if settings.ai_mode == "LIVE":
            _model_gateway = GeminiGateway()
        else:
            _model_gateway = DeterministicModelGateway()
    return _model_gateway


def set_model_gateway(gateway: ModelGateway) -> None:
    global _model_gateway
    _model_gateway = gateway


def get_clock() -> Clock:
    global _clock
    if _clock is None:
        _clock = SystemClock()
    return _clock


def set_clock(clk: Clock) -> None:
    global _clock
    _clock = clk


def get_visit_service(
    visit_repo: Annotated[VisitRepository, Depends(get_visit_repository)],
    catalog_repo: Annotated[VisitCatalogPort, Depends(get_catalog_repository)],
    policy_repo: Annotated[VisitPolicyPort, Depends(get_policy_repository)],
    state_repo: Annotated[StateRepository, Depends(get_state_repository)],
    model_gateway: Annotated[ModelGateway, Depends(get_model_gateway)],
    clock: Annotated[Clock, Depends(get_clock)],
    analytics_repo: Annotated[AnalyticsRepository, Depends(get_analytics_repository)],
    blob_repo: Annotated[BlobRepository, Depends(get_blob_repository)],
) -> VisitService:
    return VisitService(
        visit_repo=visit_repo,
        catalog_repo=catalog_repo,
        policy_repo=policy_repo,
        state_repo=state_repo,
        model_gateway=model_gateway,
        clock=clock,
        analytics_repo=analytics_repo,
        blob_repo=blob_repo,
    )
