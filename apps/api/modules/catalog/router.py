import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from storeops_contracts.models import (
    Location,
    LocationCreate,
    LocationList,
    LocationUpdate,
    Media,
    MediaInit,
    MediaUpload,
    Product,
    ProductCreate,
    ProductList,
    ProductUpdate,
    Store,
    StoreCreate,
    StoreList,
    StoreUpdate,
    Type1,
    VersionCommand,
)

from apps.api.core.auth import (
    WorkspaceContext,
    get_state_repository,
    require_workspace,
)
from apps.api.modules.catalog.dependencies import (
    get_blob_repository,
    get_catalog_repository,
)
from apps.api.modules.catalog.repository import CatalogRepository
from apps.api.modules.catalog.service import CatalogService
from apps.api.ports.blob import BlobRepository
from apps.api.ports.state import StateRepository

router = APIRouter()

require_rep = require_workspace(required_role="REP")
require_admin = require_workspace(required_role="ADMIN")


def get_catalog_service(
    catalog_repo: Annotated[CatalogRepository, Depends(get_catalog_repository)],
    blob_repo: Annotated[BlobRepository, Depends(get_blob_repository)],
) -> CatalogService:
    return CatalogService(repo=catalog_repo, blob_repo=blob_repo)


# ==============================================================================
# 1. Stores
# ==============================================================================


@router.get(
    "/stores",
    response_model=StoreList,
    operation_id="listStores",
    tags=["Catalog"],
)
async def list_stores(
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
    active: Annotated[bool | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> StoreList:
    return await service.list_stores(
        workspace_id=ctx.workspace_id,
        active=active,
        cursor=cursor,
        limit=limit,
    )


@router.post(
    "/stores",
    response_model=Store,
    status_code=status.HTTP_201_CREATED,
    operation_id="createStore",
    tags=["Catalog"],
)
async def create_store(
    request: Request,
    payload: StoreCreate,
    ctx: Annotated[WorkspaceContext, Depends(require_admin)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
    state_repo: Annotated[StateRepository, Depends(get_state_repository)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Store:
    raw_body = await request.body()
    body_hash = hashlib.sha256(raw_body).hexdigest()
    is_cached, cached_data = await state_repo.check_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route="/stores",
        key=idempotency_key,
        body_hash=body_hash,
    )
    if is_cached and cached_data:
        return Store.model_validate(cached_data)

    workspace = await state_repo.get_workspace(ctx.workspace_id)
    if not workspace:
        from apps.api.core.errors import ApiError
        raise ApiError(status_code=404, code="NOT_FOUND", message="Workspace not found")

    store = await service.create_store(workspace, payload)

    await state_repo.save_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route="/stores",
        key=idempotency_key,
        body_hash=body_hash,
        status_code=201,
        response_body=store.model_dump(mode="json"),
    )
    return store


@router.get(
    "/stores/{store_id}",
    response_model=Store,
    operation_id="getStore",
    tags=["Catalog"],
)
async def get_store(
    store_id: UUID,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> Store:
    return await service.get_store(ctx.workspace_id, store_id)


@router.patch(
    "/stores/{store_id}",
    response_model=Store,
    operation_id="updateStore",
    tags=["Catalog"],
)
async def update_store(
    store_id: UUID,
    payload: StoreUpdate,
    ctx: Annotated[WorkspaceContext, Depends(require_admin)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> Store:
    return await service.update_store(ctx.workspace_id, store_id, payload)


# ==============================================================================
# 2. Locations
# ==============================================================================


@router.get(
    "/locations",
    response_model=LocationList,
    operation_id="listLocations",
    tags=["Catalog"],
)
async def list_locations(
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
    store_id: Annotated[UUID | None, Query()] = None,
    type: Annotated[Type1 | None, Query()] = None,
    active: Annotated[bool | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> LocationList:
    return await service.list_locations(
        workspace_id=ctx.workspace_id,
        store_id=store_id,
        type=type,
        active=active,
        cursor=cursor,
        limit=limit,
    )


@router.post(
    "/locations",
    response_model=Location,
    status_code=status.HTTP_201_CREATED,
    operation_id="createLocation",
    tags=["Catalog"],
)
async def create_location(
    request: Request,
    payload: LocationCreate,
    ctx: Annotated[WorkspaceContext, Depends(require_admin)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
    state_repo: Annotated[StateRepository, Depends(get_state_repository)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Location:
    raw_body = await request.body()
    body_hash = hashlib.sha256(raw_body).hexdigest()
    is_cached, cached_data = await state_repo.check_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route="/locations",
        key=idempotency_key,
        body_hash=body_hash,
    )
    if is_cached and cached_data:
        return Location.model_validate(cached_data)

    loc = await service.create_location(ctx.workspace_id, payload)

    await state_repo.save_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route="/locations",
        key=idempotency_key,
        body_hash=body_hash,
        status_code=201,
        response_body=loc.model_dump(mode="json"),
    )
    return loc


@router.get(
    "/locations/{location_id}",
    response_model=Location,
    operation_id="getLocation",
    tags=["Catalog"],
)
async def get_location(
    location_id: UUID,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> Location:
    return await service.get_location(ctx.workspace_id, location_id)


@router.patch(
    "/locations/{location_id}",
    response_model=Location,
    operation_id="updateLocation",
    tags=["Catalog"],
)
async def update_location(
    location_id: UUID,
    payload: LocationUpdate,
    ctx: Annotated[WorkspaceContext, Depends(require_admin)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> Location:
    return await service.update_location(ctx.workspace_id, location_id, payload)


# ==============================================================================
# 3. Products
# ==============================================================================


@router.get(
    "/products",
    response_model=ProductList,
    operation_id="listProducts",
    tags=["Catalog"],
)
async def list_products(
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
    active: Annotated[bool | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ProductList:
    return await service.list_products(
        workspace_id=ctx.workspace_id,
        active=active,
        cursor=cursor,
        limit=limit,
    )


@router.post(
    "/products",
    response_model=Product,
    status_code=status.HTTP_201_CREATED,
    operation_id="createProduct",
    tags=["Catalog"],
)
async def create_product(
    request: Request,
    payload: ProductCreate,
    ctx: Annotated[WorkspaceContext, Depends(require_admin)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
    state_repo: Annotated[StateRepository, Depends(get_state_repository)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Product:
    raw_body = await request.body()
    body_hash = hashlib.sha256(raw_body).hexdigest()
    is_cached, cached_data = await state_repo.check_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route="/products",
        key=idempotency_key,
        body_hash=body_hash,
    )
    if is_cached and cached_data:
        return Product.model_validate(cached_data)

    prod = await service.create_product(ctx.workspace_id, payload)

    await state_repo.save_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route="/products",
        key=idempotency_key,
        body_hash=body_hash,
        status_code=201,
        response_body=prod.model_dump(mode="json"),
    )
    return prod


@router.get(
    "/products/{product_id}",
    response_model=Product,
    operation_id="getProduct",
    tags=["Catalog"],
)
async def get_product(
    product_id: UUID,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> Product:
    return await service.get_product(ctx.workspace_id, product_id)


@router.patch(
    "/products/{product_id}",
    response_model=Product,
    operation_id="updateProduct",
    tags=["Catalog"],
)
async def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    ctx: Annotated[WorkspaceContext, Depends(require_admin)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> Product:
    return await service.update_product(ctx.workspace_id, product_id, payload)


# ==============================================================================
# 4. Media
# ==============================================================================


@router.post(
    "/media",
    response_model=MediaUpload,
    status_code=status.HTTP_201_CREATED,
    operation_id="initMedia",
    tags=["Media"],
)
async def init_media(
    request: Request,
    payload: MediaInit,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
    state_repo: Annotated[StateRepository, Depends(get_state_repository)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> MediaUpload:
    raw_body = await request.body()
    body_hash = hashlib.sha256(raw_body).hexdigest()
    is_cached, cached_data = await state_repo.check_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route="/media",
        key=idempotency_key,
        body_hash=body_hash,
    )
    if is_cached and cached_data:
        return MediaUpload.model_validate(cached_data)

    upload = await service.init_media(ctx.workspace_id, payload)

    await state_repo.save_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route="/media",
        key=idempotency_key,
        body_hash=body_hash,
        status_code=201,
        response_body=upload.model_dump(mode="json"),
    )
    return upload


@router.post(
    "/media/{media_id}/complete",
    response_model=Media,
    operation_id="completeMedia",
    tags=["Media"],
)
async def complete_media(
    request: Request,
    media_id: UUID,
    payload: VersionCommand,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
    state_repo: Annotated[StateRepository, Depends(get_state_repository)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> Media:
    raw_body = await request.body()
    body_hash = hashlib.sha256(raw_body).hexdigest()
    route_path = f"/media/{media_id}/complete"
    is_cached, cached_data = await state_repo.check_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route=route_path,
        key=idempotency_key,
        body_hash=body_hash,
    )
    if is_cached and cached_data:
        return Media.model_validate(cached_data)

    media = await service.complete_media(ctx.workspace_id, media_id, payload)

    await state_repo.save_idempotency(
        uid=ctx.user.uid,
        method="POST",
        route=route_path,
        key=idempotency_key,
        body_hash=body_hash,
        status_code=200,
        response_body=media.model_dump(mode="json"),
    )
    return media


@router.get(
    "/media/{media_id}",
    response_model=Media,
    operation_id="getMedia",
    tags=["Media"],
)
async def get_media(
    media_id: UUID,
    ctx: Annotated[WorkspaceContext, Depends(require_rep)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> Media:
    return await service.get_media(ctx.workspace_id, media_id)


# Helper endpoint for uploading raw bytes in local development/tests
@router.put("/media/upload/{media_id}", tags=["Media"])
async def upload_media_bytes(
    media_id: UUID,
    request: Request,
    blob_repo: Annotated[BlobRepository, Depends(get_blob_repository)],
) -> Response:
    raw_bytes = await request.body()
    path = blob_repo._file_path(media_id)  # type: ignore
    path.write_bytes(raw_bytes)
    return Response(status_code=200)
