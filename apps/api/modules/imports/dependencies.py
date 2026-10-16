from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends

from apps.api.analytics.duckdb import DuckDBAnalyticsRepository
from apps.api.core.auth import get_state_repository
from apps.api.core.config import ConfigurationError, Settings, settings
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
from apps.api.ports.imports import ImportRepositoryPort
from apps.api.ports.state import StateRepository

_import_repository: ImportRepositoryPort | None = None
_analytics_repository: AnalyticsRepository | None = None
_clock: Clock | None = None


def _default_firestore_client(project: str | None) -> Any:
    from google.cloud import firestore

    return firestore.AsyncClient(project=project)


def _default_bigquery_client(project: str | None) -> Any:
    from google.cloud import bigquery

    return bigquery.Client(project=project)


def build_import_repository(
    cfg: Settings = settings,
    firestore_client_factory: Callable[[str | None], Any] | None = None,
) -> ImportRepositoryPort:
    """Firestore when STATE_BACKEND=firestore; in-memory otherwise (LOCAL only)."""
    if cfg.state_backend.lower() == "firestore":
        from apps.api.adapters.state.firestore_imports import FirestoreImportRepository

        factory = firestore_client_factory or _default_firestore_client
        return FirestoreImportRepository(client=factory(cfg.firebase_project_id))
    return ImportRepository()


def build_analytics_repository(
    cfg: Settings = settings,
    bigquery_client_factory: Callable[[str | None], Any] | None = None,
) -> AnalyticsRepository:
    """BigQuery when DATA_BACKEND=CLOUD; DuckDB otherwise. No silent fallback in CLOUD."""
    if cfg.data_backend.upper() == "CLOUD":
        missing = [
            name
            for name, value in (
                ("GCP_PROJECT", cfg.gcp_project),
                ("BIGQUERY_DATASET", cfg.bigquery_dataset),
            )
            if not value
        ]
        if missing:
            raise ConfigurationError(f"DATA_BACKEND=CLOUD requires {', '.join(missing)}")
        from apps.api.analytics.bigquery import BigQueryAnalyticsRepository

        factory = bigquery_client_factory or _default_bigquery_client
        return BigQueryAnalyticsRepository(
            project_id=cfg.gcp_project,
            dataset_id=cfg.bigquery_dataset,
            allow_prod=cfg.is_production,
            client=factory(cfg.gcp_project),
        )
    if cfg.profile.upper() == "CLOUD":
        raise ConfigurationError("PROFILE=CLOUD requires DATA_BACKEND=CLOUD (BigQuery analytics)")
    return DuckDBAnalyticsRepository()


def get_import_repository() -> ImportRepositoryPort:
    global _import_repository
    if _import_repository is None:
        _import_repository = build_import_repository()
    return _import_repository


def set_import_repository(repo: ImportRepositoryPort) -> None:
    global _import_repository
    _import_repository = repo


def get_analytics_repository() -> AnalyticsRepository:
    global _analytics_repository
    if _analytics_repository is None:
        _analytics_repository = build_analytics_repository()
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
    import_repo: Annotated[ImportRepositoryPort, Depends(get_import_repository)],
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
