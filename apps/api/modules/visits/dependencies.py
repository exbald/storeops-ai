from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends

from apps.api.adapters.state.firestore_persistence import default_firestore_client
from apps.api.ai.gateway import DeterministicModelGateway, GeminiGateway
from apps.api.core.auth import get_state_repository
from apps.api.core.config import Settings, settings
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


def build_visit_repository(
    cfg: Settings = settings,
    firestore_client_factory: Callable[[str | None], Any] | None = None,
) -> VisitRepository:
    """Write-through Firestore repo when STATE_BACKEND=firestore; in-memory otherwise.

    The Firestore-backed repo serves reads from memory: single API instance only.
    """
    if cfg.state_backend.lower() == "firestore":
        from apps.api.adapters.state.firestore_write_through import (
            FirestoreBackedVisitRepository,
        )

        factory = firestore_client_factory or default_firestore_client
        return FirestoreBackedVisitRepository(client=factory(cfg.firebase_project_id))
    return InMemoryVisitRepository()


def get_visit_repository() -> VisitRepository:
    global _visit_repository
    if _visit_repository is None:
        _visit_repository = build_visit_repository()
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
