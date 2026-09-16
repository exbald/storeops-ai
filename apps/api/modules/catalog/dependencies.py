from apps.api.adapters.blob.local_fs import LocalFileSystemBlobRepository
from apps.api.modules.catalog.repository import (
    CatalogRepository,
    InMemoryCatalogRepository,
)
from apps.api.ports.blob import BlobRepository

_catalog_repository: CatalogRepository | None = None
_blob_repository: BlobRepository | None = None


def get_catalog_repository() -> CatalogRepository:
    global _catalog_repository
    if _catalog_repository is None:
        _catalog_repository = InMemoryCatalogRepository()
    return _catalog_repository


def set_catalog_repository(repo: CatalogRepository) -> None:
    global _catalog_repository
    _catalog_repository = repo


def get_blob_repository() -> BlobRepository:
    global _blob_repository
    if _blob_repository is None:
        _blob_repository = LocalFileSystemBlobRepository()
    return _blob_repository


def set_blob_repository(repo: BlobRepository) -> None:
    global _blob_repository
    _blob_repository = repo
