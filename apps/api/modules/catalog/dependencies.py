from collections.abc import Callable
from typing import Any

from apps.api.adapters.blob.local_fs import LocalFileSystemBlobRepository
from apps.api.adapters.state.firestore_persistence import default_firestore_client
from apps.api.core.config import ConfigurationError, Settings, settings
from apps.api.modules.catalog.repository import (
    CatalogRepository,
    InMemoryCatalogRepository,
)
from apps.api.ports.blob import BlobRepository

_catalog_repository: CatalogRepository | None = None
_blob_repository: BlobRepository | None = None


def build_catalog_repository(
    cfg: Settings = settings,
    firestore_client_factory: Callable[[str | None], Any] | None = None,
) -> CatalogRepository:
    """Write-through Firestore repo when STATE_BACKEND=firestore; in-memory otherwise.

    The Firestore-backed repo serves reads from memory: single API instance only.
    """
    if cfg.state_backend.lower() == "firestore":
        from apps.api.adapters.state.firestore_write_through import (
            FirestoreBackedCatalogRepository,
        )

        factory = firestore_client_factory or default_firestore_client
        return FirestoreBackedCatalogRepository(client=factory(cfg.firebase_project_id))
    return InMemoryCatalogRepository()


def get_catalog_repository() -> CatalogRepository:
    global _catalog_repository
    if _catalog_repository is None:
        _catalog_repository = build_catalog_repository()
    return _catalog_repository


def set_catalog_repository(repo: CatalogRepository) -> None:
    global _catalog_repository
    _catalog_repository = repo


def _default_storage_client(project: str | None) -> Any:
    from google.cloud import storage

    return storage.Client(project=project)


def build_blob_repository(
    cfg: Settings = settings,
    storage_client_factory: Callable[[str | None], Any] | None = None,
) -> BlobRepository:
    """GCS when STATE_BACKEND=firestore and MEDIA_BUCKET is set; local disk otherwise.

    PROFILE=CLOUD without a bucket is a configuration error, never a silent fallback.
    """
    if cfg.state_backend.lower() == "firestore" and cfg.media_bucket:
        from apps.api.adapters.blob.gcs import GCSBlobRepository

        project = cfg.gcp_project or cfg.firebase_project_id
        factory = storage_client_factory or _default_storage_client
        return GCSBlobRepository(bucket_name=cfg.media_bucket, client=factory(project))
    if cfg.profile.upper() == "CLOUD":
        raise ConfigurationError(
            "PROFILE=CLOUD requires STATE_BACKEND=firestore and MEDIA_BUCKET for media storage"
        )
    return LocalFileSystemBlobRepository(base_dir=cfg.media_storage_dir)


def get_blob_repository() -> BlobRepository:
    global _blob_repository
    if _blob_repository is None:
        _blob_repository = build_blob_repository()
    return _blob_repository


def set_blob_repository(repo: BlobRepository) -> None:
    global _blob_repository
    _blob_repository = repo
