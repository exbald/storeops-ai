"""Dependency injection wiring for verification module."""

from typing import Annotated

from fastapi import Depends

from apps.api.ai.gateway import DeterministicModelGateway, GeminiGateway
from apps.api.core.auth import get_state_repository
from apps.api.core.config import settings
from apps.api.modules.catalog.dependencies import (
    get_blob_repository,
    get_catalog_repository,
)
from apps.api.modules.policies.dependencies import get_policy_repository
from apps.api.modules.verification.ports import (
    VerificationCatalogPort,
    VerificationPolicyPort,
    VerificationVisitPort,
)
from apps.api.modules.verification.repository import (
    InMemoryVerificationRepository,
    VerificationRepository,
)
from apps.api.modules.verification.service import VerificationService
from apps.api.modules.visits.dependencies import get_visit_repository
from apps.api.ports.blob import BlobRepository
from apps.api.ports.clock import Clock, SystemClock
from apps.api.ports.model import ModelGateway
from apps.api.ports.state import StateRepository

_verification_repository: VerificationRepository | None = None
_model_gateway: ModelGateway | None = None
_clock: Clock | None = None


def get_verification_repository() -> VerificationRepository:
    global _verification_repository
    if _verification_repository is None:
        _verification_repository = InMemoryVerificationRepository()
    return _verification_repository


def set_verification_repository(repo: VerificationRepository) -> None:
    global _verification_repository
    _verification_repository = repo


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


def get_verification_service(
    verification_repo: Annotated[
        VerificationRepository, Depends(get_verification_repository)
    ],
    visit_port: Annotated[VerificationVisitPort, Depends(get_visit_repository)],
    policy_port: Annotated[VerificationPolicyPort, Depends(get_policy_repository)],
    catalog_port: Annotated[VerificationCatalogPort, Depends(get_catalog_repository)],
    blob_repo: Annotated[BlobRepository, Depends(get_blob_repository)],
    state_repo: Annotated[StateRepository, Depends(get_state_repository)],
    model_gateway: Annotated[ModelGateway, Depends(get_model_gateway)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> VerificationService:
    return VerificationService(
        verification_repo=verification_repo,
        visit_port=visit_port,
        policy_port=policy_port,
        catalog_port=catalog_port,
        blob_repo=blob_repo,
        state_repo=state_repo,
        model_gateway=model_gateway,
        clock=clock,
    )
