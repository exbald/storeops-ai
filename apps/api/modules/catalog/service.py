from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from pydantic import AnyUrl
from storeops_contracts.models import (
    Error,
    Location,
    LocationCreate,
    LocationList,
    LocationUpdate,
    Media,
    MediaInit,
    MediaUpload,
    Method,
    Product,
    ProductCreate,
    ProductList,
    ProductUpdate,
    Status1,
    Store,
    StoreCreate,
    StoreList,
    StoreUpdate,
    Type1,
    VersionCommand,
    Workspace,
)

from apps.api.core.errors import ApiError
from apps.api.modules.catalog.repository import CatalogRepository
from apps.api.ports.blob import BlobRepository
from apps.api.ports.state import VersionConflictError


class CatalogService:
    def __init__(self, repo: CatalogRepository, blob_repo: BlobRepository) -> None:
        self.repo = repo
        self.blob_repo = blob_repo

    async def create_store(self, workspace: Workspace, data: StoreCreate) -> Store:
        existing = await self.repo.get_store_by_code(workspace.id, data.code)
        if existing:
            raise ApiError(status_code=409, code="DUPLICATE_CODE", message=f"Store code {data.code} already exists")

        now = datetime.now(UTC)
        store_id = uuid4()
        backroom_id = uuid4()

        backroom = Location(
            id=backroom_id,
            workspace_id=workspace.id,
            version=1,
            created_at=now,
            updated_at=now,
            code=f"{data.code}-BACKROOM",
            name=f"{data.name} Backroom",
            type=Type1.BACKROOM,
            store_id=store_id,
            active=True,
        )

        store = Store(
            id=store_id,
            workspace_id=workspace.id,
            version=1,
            created_at=now,
            updated_at=now,
            code=data.code,
            name=data.name,
            retailer=data.retailer,
            region=data.region,
            format=data.format,
            timezone=data.timezone,
            distributor_location_id=data.distributor_location_id,
            currency=workspace.currency,
            backroom_location_id=backroom_id,
            active=True,
        )

        await self.repo.create_store_with_backroom(store, backroom)
        return store

    async def get_store(self, workspace_id: UUID, store_id: UUID) -> Store:
        store = await self.repo.get_store(workspace_id, store_id)
        if not store:
            raise ApiError(status_code=404, code="NOT_FOUND", message="Store not found")
        return store

    async def update_store(self, workspace_id: UUID, store_id: UUID, data: StoreUpdate) -> Store:
        existing = await self.get_store(workspace_id, store_id)
        if existing.version != data.expected_version:
            raise VersionConflictError(
                f"Version conflict: expected {data.expected_version}, got {existing.version}"
            )

        now = datetime.now(UTC)
        updated = Store(
            id=existing.id,
            workspace_id=existing.workspace_id,
            version=existing.version + 1,
            created_at=existing.created_at,
            updated_at=now,
            code=existing.code,
            name=data.name if data.name is not None else existing.name,
            retailer=data.retailer if data.retailer is not None else existing.retailer,
            region=data.region if data.region is not None else existing.region,
            format=data.format if data.format is not None else existing.format,
            timezone=data.timezone if data.timezone is not None else existing.timezone,
            distributor_location_id=(
                data.distributor_location_id
                if data.distributor_location_id is not None
                else existing.distributor_location_id
            ),
            currency=existing.currency,
            backroom_location_id=existing.backroom_location_id,
            active=data.active if data.active is not None else existing.active,
        )
        await self.repo.update_store(updated)
        return updated

    async def list_stores(
        self,
        workspace_id: UUID,
        active: bool | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> StoreList:
        items, next_cursor = await self.repo.list_stores(
            workspace_id=workspace_id, active=active, cursor=cursor, limit=limit
        )
        return StoreList(items=items, next_cursor=next_cursor)

    async def create_location(self, workspace_id: UUID, data: LocationCreate) -> Location:
        existing = await self.repo.get_location_by_code(workspace_id, data.code)
        if existing:
            raise ApiError(status_code=409, code="DUPLICATE_CODE", message=f"Location code {data.code} already exists")

        now = datetime.now(UTC)
        location = Location(
            id=uuid4(),
            workspace_id=workspace_id,
            version=1,
            created_at=now,
            updated_at=now,
            code=data.code,
            name=data.name,
            type=Type1.DISTRIBUTOR,
            store_id=None,
            active=True,
        )
        await self.repo.create_location(location)
        return location

    async def get_location(self, workspace_id: UUID, location_id: UUID) -> Location:
        loc = await self.repo.get_location(workspace_id, location_id)
        if not loc:
            raise ApiError(status_code=404, code="NOT_FOUND", message="Location not found")
        return loc

    async def update_location(
        self, workspace_id: UUID, location_id: UUID, data: LocationUpdate
    ) -> Location:
        existing = await self.get_location(workspace_id, location_id)
        if existing.version != data.expected_version:
            raise VersionConflictError(
                f"Version conflict: expected {data.expected_version}, got {existing.version}"
            )

        now = datetime.now(UTC)
        updated = Location(
            id=existing.id,
            workspace_id=existing.workspace_id,
            version=existing.version + 1,
            created_at=existing.created_at,
            updated_at=now,
            code=existing.code,
            name=data.name if data.name is not None else existing.name,
            type=existing.type,
            store_id=existing.store_id,
            active=data.active if data.active is not None else existing.active,
        )
        await self.repo.update_location(updated)
        return updated

    async def list_locations(
        self,
        workspace_id: UUID,
        store_id: UUID | None = None,
        type: Type1 | None = None,
        active: bool | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> LocationList:
        items, next_cursor = await self.repo.list_locations(
            workspace_id=workspace_id,
            store_id=store_id,
            type=type,
            active=active,
            cursor=cursor,
            limit=limit,
        )
        return LocationList(items=items, next_cursor=next_cursor)

    async def create_product(self, workspace_id: UUID, data: ProductCreate) -> Product:
        existing = await self.repo.get_product_by_sku(workspace_id, data.sku)
        if existing:
            raise ApiError(status_code=409, code="DUPLICATE_SKU", message=f"Product SKU {data.sku} already exists")

        now = datetime.now(UTC)
        product = Product(
            id=uuid4(),
            workspace_id=workspace_id,
            version=1,
            created_at=now,
            updated_at=now,
            sku=data.sku,
            name=data.name,
            case_units=data.case_units,
            reference_media_ids=[],
            active=True,
        )
        await self.repo.create_product(product)
        return product

    async def get_product(self, workspace_id: UUID, product_id: UUID) -> Product:
        product = await self.repo.get_product(workspace_id, product_id)
        if not product:
            raise ApiError(status_code=404, code="NOT_FOUND", message="Product not found")
        return product

    async def update_product(
        self, workspace_id: UUID, product_id: UUID, data: ProductUpdate
    ) -> Product:
        existing = await self.get_product(workspace_id, product_id)
        if existing.version != data.expected_version:
            raise VersionConflictError(
                f"Version conflict: expected {data.expected_version}, got {existing.version}"
            )

        if data.active is False:
            has_policy = await self.repo.has_active_policy_product_reference(workspace_id, product_id)
            if has_policy:
                raise ApiError(
                    status_code=409,
                    code="POLICY_CONFLICT",
                    message="Cannot archive product referenced by an active policy",
                )

        now = datetime.now(UTC)
        updated = Product(
            id=existing.id,
            workspace_id=existing.workspace_id,
            version=existing.version + 1,
            created_at=existing.created_at,
            updated_at=now,
            sku=existing.sku,
            name=data.name if data.name is not None else existing.name,
            case_units=data.case_units if data.case_units is not None else existing.case_units,
            reference_media_ids=(
                data.reference_media_ids
                if data.reference_media_ids is not None
                else existing.reference_media_ids
            ),
            active=data.active if data.active is not None else existing.active,
        )
        await self.repo.update_product(updated)
        return updated

    async def list_products(
        self,
        workspace_id: UUID,
        active: bool | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> ProductList:
        items, next_cursor = await self.repo.list_products(
            workspace_id=workspace_id, active=active, cursor=cursor, limit=limit
        )
        return ProductList(items=items, next_cursor=next_cursor)

    async def init_media(self, workspace_id: UUID, data: MediaInit) -> MediaUpload:
        now = datetime.now(UTC)
        media_id = uuid4()
        media = Media(
            id=media_id,
            workspace_id=workspace_id,
            version=1,
            created_at=now,
            updated_at=now,
            kind=data.kind,
            filename=data.filename,
            mime_type=data.mime_type.value,
            status=Status1.PENDING_UPLOAD,
            store_id=data.store_id,
            visit_id=data.visit_id,
            product_id=data.product_id,
            zone_id=data.zone_id,
            zone_kind=data.zone_kind,
            captured_at=data.captured_at,
            original_sha256=data.sha256,
            normalized_sha256=None,
            byte_size=data.byte_size,
            width=None,
            height=None,
            rejection=None,
            download_url=None,
            download_url_expires_at=None,
        )
        await self.repo.create_media(media)

        upload_url = await self.blob_repo.prepare_upload(
            media_id=media_id, filename=data.filename, mime_type=data.mime_type.value
        )
        return MediaUpload(
            media=media,
            upload_url=AnyUrl(upload_url),
            method=Method.PUT,
            headers={"Content-Type": data.mime_type.value},
            expires_at=now + timedelta(minutes=15),
        )

    async def complete_media(
        self, workspace_id: UUID, media_id: UUID, data: VersionCommand
    ) -> Media:
        media = await self.repo.get_media(workspace_id, media_id)
        if not media:
            raise ApiError(status_code=404, code="NOT_FOUND", message="Media not found")

        if media.version != data.expected_version:
            raise VersionConflictError(
                f"Version conflict: expected {data.expected_version}, got {media.version}"
            )

        now = datetime.now(UTC)
        try:
            sha256, size, dims = await self.blob_repo.finalize_upload(media_id)
            if sha256 != media.original_sha256:
                rejection = Error(
                    code="CHECKSUM_MISMATCH",
                    message=f"Checksum mismatch: expected {media.original_sha256}, got {sha256}",
                    request_id=uuid4(),
                    details=[],
                )
                updated = media.model_copy(
                    update={
                        "version": media.version + 1,
                        "updated_at": now,
                        "status": Status1.REJECTED,
                        "rejection": rejection,
                    }
                )
            else:
                updated = media.model_copy(
                    update={
                        "version": media.version + 1,
                        "updated_at": now,
                        "status": Status1.READY,
                        "normalized_sha256": sha256,
                        "byte_size": size,
                        "width": dims[0] if dims else None,
                        "height": dims[1] if dims else None,
                        "rejection": None,
                    }
                )
        except (ValueError, FileNotFoundError) as e:
            err_str = str(e)
            code = "FILE_TOO_LARGE" if "size" in err_str.lower() else "INVALID_ASSET"
            rejection = Error(
                code=code,
                message=err_str,
                request_id=uuid4(),
                details=[],
            )
            updated = media.model_copy(
                update={
                    "version": media.version + 1,
                    "updated_at": now,
                    "status": Status1.REJECTED,
                    "rejection": rejection,
                }
            )

        await self.repo.update_media(updated)
        return updated

    async def get_media(self, workspace_id: UUID, media_id: UUID) -> Media:
        media = await self.repo.get_media(workspace_id, media_id)
        if not media:
            raise ApiError(status_code=404, code="NOT_FOUND", message="Media not found")

        if media.status == Status1.READY:
            dl_url = await self.blob_repo.get_download_url(media_id, expires_in_seconds=600)
            now = datetime.now(UTC)
            return media.model_copy(
                update={
                    "download_url": AnyUrl(dl_url),
                    "download_url_expires_at": now + timedelta(seconds=600),
                }
            )
        return media
