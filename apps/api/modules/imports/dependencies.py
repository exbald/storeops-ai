from typing import Annotated

from fastapi import Depends

from apps.api.analytics.duckdb import DuckDBAnalyticsRepository
from apps.api.core.auth import get_state_repository
from apps.api.modules.catalog.dependencies import (
    get_blob_repository,
    get_catalog_repository,
)
from apps.api.modules.catalog.repository import CatalogRepository
from apps.api.modules.imports.repository import ImportRepository
from apps.api.modules.imports.service import ImportService
from apps.api.ports.analytics import AnalyticsRepository
from apps.api.ports.blob import BlobRepository
from apps.api.ports.clock import Clock, SystemClock
from apps.api.ports.state import StateRepository

_import_repository: ImportRepository | None = None
_analytics_repository: AnalyticsRepository | None = None
_clock: Clock | None = None


def get_import_repository() -> ImportRepository:
    global _import_repository
    if _import_repository is None:
        _import_repository = ImportRepository()
    return _import_repository


def set_import_repository(repo: ImportRepository) -> None:
    global _import_repository
    _import_repository = repo


def get_analytics_repository() -> AnalyticsRepository:
    global _analytics_repository
    if _analytics_repository is None:
        _analytics_repository = DuckDBAnalyticsRepository()
    return _analytics_repository


def set_analytics_repository(repo: AnalyticsRepository) -> None:
    global _analytics_repository
    _analytics_repository = repo


def get_clock() -> Clock:
    global _clock
    if _clock is None:
        _clock = SystemClock()
    return _clock


def set_clock(clk: Clock) -> None:
    global _clock
    _clock = clk


def get_import_service(
    import_repo: Annotated[ImportRepository, Depends(get_import_repository)],
    analytics_repo: Annotated[AnalyticsRepository, Depends(get_analytics_repository)],
    catalog_repo: Annotated[CatalogRepository, Depends(get_catalog_repository)],
    state_repo: Annotated[StateRepository, Depends(get_state_repository)],
    blob_repo: Annotated[BlobRepository, Depends(get_blob_repository)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> ImportService:
    return ImportService(
        import_repo=import_repo,
        analytics_repo=analytics_repo,
        catalog_repo=catalog_repo,
        state_repo=state_repo,
        blob_repo=blob_repo,
        clock=clock,
    )
