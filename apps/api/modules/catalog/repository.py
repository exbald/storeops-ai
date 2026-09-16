from typing import Protocol
from uuid import UUID

from storeops_contracts.models import (
    Location,
    Media,
    Product,
    Store,
    Type1,
)


class CatalogRepository(Protocol):
    async def get_store(self, workspace_id: UUID, store_id: UUID) -> Store | None:
        ...

    async def get_store_by_code(self, workspace_id: UUID, code: str) -> Store | None:
        ...

    async def create_store_with_backroom(
        self, store: Store, backroom: Location
    ) -> tuple[Store, Location]:
        ...

    async def update_store(self, store: Store) -> Store:
        ...

    async def list_stores(
        self,
        workspace_id: UUID,
        active: bool | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Store], str | None]:
        ...

    async def get_location(self, workspace_id: UUID, location_id: UUID) -> Location | None:
        ...

    async def get_location_by_code(self, workspace_id: UUID, code: str) -> Location | None:
        ...

    async def create_location(self, location: Location) -> Location:
        ...

    async def update_location(self, location: Location) -> Location:
        ...

    async def list_locations(
        self,
        workspace_id: UUID,
        store_id: UUID | None = None,
        type: Type1 | None = None,
        active: bool | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Location], str | None]:
        ...

    async def get_product(self, workspace_id: UUID, product_id: UUID) -> Product | None:
        ...

    async def get_product_by_sku(self, workspace_id: UUID, sku: str) -> Product | None:
        ...

    async def create_product(self, product: Product) -> Product:
        ...

    async def update_product(self, product: Product) -> Product:
        ...

    async def list_products(
        self,
        workspace_id: UUID,
        active: bool | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Product], str | None]:
        ...

    async def get_media(self, workspace_id: UUID, media_id: UUID) -> Media | None:
        ...

    async def create_media(self, media: Media) -> Media:
        ...

    async def update_media(self, media: Media) -> Media:
        ...

    async def add_active_policy_product_reference(self, workspace_id: UUID, product_id: UUID) -> None:
        ...

    async def remove_active_policy_product_reference(self, workspace_id: UUID, product_id: UUID) -> None:
        ...

    async def has_active_policy_product_reference(self, workspace_id: UUID, product_id: UUID) -> bool:
        ...


class InMemoryCatalogRepository(CatalogRepository):
    def __init__(self) -> None:
        self._stores: dict[tuple[UUID, UUID], Store] = {}
        self._stores_by_code: dict[tuple[UUID, str], UUID] = {}
        self._locations: dict[tuple[UUID, UUID], Location] = {}
        self._locations_by_code: dict[tuple[UUID, str], UUID] = {}
        self._products: dict[tuple[UUID, UUID], Product] = {}
        self._products_by_sku: dict[tuple[UUID, str], UUID] = {}
        self._media: dict[tuple[UUID, UUID], Media] = {}
        self._active_policy_product_references: set[tuple[UUID, UUID]] = set()

    async def get_store(self, workspace_id: UUID, store_id: UUID) -> Store | None:
        return self._stores.get((workspace_id, store_id))

    async def get_store_by_code(self, workspace_id: UUID, code: str) -> Store | None:
        store_id = self._stores_by_code.get((workspace_id, code))
        if store_id:
            return self._stores.get((workspace_id, store_id))
        return None

    async def create_store_with_backroom(
        self, store: Store, backroom: Location
    ) -> tuple[Store, Location]:
        self._stores[(store.workspace_id, store.id)] = store
        self._stores_by_code[(store.workspace_id, store.code)] = store.id
        self._locations[(backroom.workspace_id, backroom.id)] = backroom
        self._locations_by_code[(backroom.workspace_id, backroom.code)] = backroom.id
        return store, backroom

    async def update_store(self, store: Store) -> Store:
        self._stores[(store.workspace_id, store.id)] = store
        self._stores_by_code[(store.workspace_id, store.code)] = store.id
        return store

    async def list_stores(
        self,
        workspace_id: UUID,
        active: bool | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Store], str | None]:
        stores = [
            s for (ws, _), s in self._stores.items()
            if ws == workspace_id and (active is None or s.active == active)
        ]
        stores.sort(key=lambda s: s.created_at)
        start_idx = 0
        if cursor:
            for idx, s in enumerate(stores):
                if str(s.id) == cursor:
                    start_idx = idx + 1
                    break
        slice_items = stores[start_idx : start_idx + limit]
        next_cursor = str(slice_items[-1].id) if len(stores) > start_idx + limit else None
        return slice_items, next_cursor

    async def get_location(self, workspace_id: UUID, location_id: UUID) -> Location | None:
        return self._locations.get((workspace_id, location_id))

    async def get_location_by_code(self, workspace_id: UUID, code: str) -> Location | None:
        loc_id = self._locations_by_code.get((workspace_id, code))
        if loc_id:
            return self._locations.get((workspace_id, loc_id))
        return None

    async def create_location(self, location: Location) -> Location:
        self._locations[(location.workspace_id, location.id)] = location
        self._locations_by_code[(location.workspace_id, location.code)] = location.id
        return location

    async def update_location(self, location: Location) -> Location:
        self._locations[(location.workspace_id, location.id)] = location
        self._locations_by_code[(location.workspace_id, location.code)] = location.id
        return location

    async def list_locations(
        self,
        workspace_id: UUID,
        store_id: UUID | None = None,
        type: Type1 | None = None,
        active: bool | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Location], str | None]:
        locs = [
            loc for (ws, _), loc in self._locations.items()
            if ws == workspace_id
            and (store_id is None or loc.store_id == store_id)
            and (type is None or loc.type == type)
            and (active is None or loc.active == active)
        ]
        locs.sort(key=lambda l: l.created_at)
        start_idx = 0
        if cursor:
            for idx, l in enumerate(locs):
                if str(l.id) == cursor:
                    start_idx = idx + 1
                    break
        slice_items = locs[start_idx : start_idx + limit]
        next_cursor = str(slice_items[-1].id) if len(locs) > start_idx + limit else None
        return slice_items, next_cursor

    async def get_product(self, workspace_id: UUID, product_id: UUID) -> Product | None:
        return self._products.get((workspace_id, product_id))

    async def get_product_by_sku(self, workspace_id: UUID, sku: str) -> Product | None:
        prod_id = self._products_by_sku.get((workspace_id, sku))
        if prod_id:
            return self._products.get((workspace_id, prod_id))
        return None

    async def create_product(self, product: Product) -> Product:
        self._products[(product.workspace_id, product.id)] = product
        self._products_by_sku[(product.workspace_id, product.sku)] = product.id
        return product

    async def update_product(self, product: Product) -> Product:
        self._products[(product.workspace_id, product.id)] = product
        self._products_by_sku[(product.workspace_id, product.sku)] = product.id
        return product

    async def list_products(
        self,
        workspace_id: UUID,
        active: bool | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Product], str | None]:
        prods = [
            p for (ws, _), p in self._products.items()
            if ws == workspace_id and (active is None or p.active == active)
        ]
        prods.sort(key=lambda p: p.created_at)
        start_idx = 0
        if cursor:
            for idx, p in enumerate(prods):
                if str(p.id) == cursor:
                    start_idx = idx + 1
                    break
        slice_items = prods[start_idx : start_idx + limit]
        next_cursor = str(slice_items[-1].id) if len(prods) > start_idx + limit else None
        return slice_items, next_cursor

    async def get_media(self, workspace_id: UUID, media_id: UUID) -> Media | None:
        return self._media.get((workspace_id, media_id))

    async def create_media(self, media: Media) -> Media:
        self._media[(media.workspace_id, media.id)] = media
        return media

    async def update_media(self, media: Media) -> Media:
        self._media[(media.workspace_id, media.id)] = media
        return media

    async def add_active_policy_product_reference(self, workspace_id: UUID, product_id: UUID) -> None:
        self._active_policy_product_references.add((workspace_id, product_id))

    async def remove_active_policy_product_reference(self, workspace_id: UUID, product_id: UUID) -> None:
        self._active_policy_product_references.discard((workspace_id, product_id))

    async def has_active_policy_product_reference(self, workspace_id: UUID, product_id: UUID) -> bool:
        return (workspace_id, product_id) in self._active_policy_product_references
