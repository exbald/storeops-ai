"""Firestore-backed (write-through) variants of the in-memory module repositories.

Each subclass persists the entity to Firestore BEFORE delegating to the in-memory
implementation, so a failed write raises and leaves memory unchanged. Reads stay
in memory; load() fills memory at startup.

Requires a single API instance (Cloud Run max-instances=1); see
firestore_persistence.py for the constraint and document layout.
"""

from typing import Any
from uuid import UUID

from storeops_contracts.models import (
    Evidence,
    Investigation,
    Location,
    Media,
    PolicyVersion,
    Product,
    Promotion,
    Report,
    Store,
    Verification,
    Visit,
)

from apps.api.adapters.state.firestore_persistence import FirestoreWriteThrough
from apps.api.modules.catalog.repository import InMemoryCatalogRepository
from apps.api.modules.policies.repository import InMemoryPolicyRepository
from apps.api.modules.verification.repository import InMemoryVerificationRepository
from apps.api.modules.visits.repository import InMemoryVisitRepository

STORES = "stores"
LOCATIONS = "locations"
PRODUCTS = "products"
MEDIA = "media"
POLICY_PRODUCT_REFS = "policy_product_refs"
PROMOTIONS = "promotions"
POLICY_VERSIONS = "policy_versions"
VISITS = "visits"
INVESTIGATIONS = "investigations"
EVIDENCE = "evidence"
REPORTS = "reports"
VERIFICATIONS = "verifications"


def _ref_doc_id(workspace_id: UUID, product_id: UUID) -> str:
    return f"{workspace_id}_{product_id}"


class FirestoreBackedCatalogRepository(FirestoreWriteThrough, InMemoryCatalogRepository):
    def __init__(self, client: Any | None = None, project_id: str | None = None) -> None:
        InMemoryCatalogRepository.__init__(self)
        self._init_store(client, project_id)

    async def _load_entities(self) -> None:
        s = self._entity_store
        for ws, store in await s.load(STORES, Store):
            self._stores[(ws, store.id)] = store
            self._stores_by_code[(ws, store.code)] = store.id
        for ws, loc in await s.load(LOCATIONS, Location):
            self._locations[(ws, loc.id)] = loc
            self._locations_by_code[(ws, loc.code)] = loc.id
        for ws, prod in await s.load(PRODUCTS, Product):
            self._products[(ws, prod.id)] = prod
            self._products_by_sku[(ws, prod.sku)] = prod.id
        for ws, med in await s.load(MEDIA, Media):
            self._media[(ws, med.id)] = med
        for data in await s.load_raw(POLICY_PRODUCT_REFS):
            self._active_policy_product_references.add(
                (UUID(data["workspace_id"]), UUID(data["product_id"]))
            )

    async def create_store_with_backroom(
        self, store: Store, backroom: Location
    ) -> tuple[Store, Location]:
        await self._entity_store.put(LOCATIONS, backroom.workspace_id, backroom.id, backroom)
        await self._entity_store.put(STORES, store.workspace_id, store.id, store)
        return await super().create_store_with_backroom(store, backroom)

    async def update_store(self, store: Store) -> Store:
        await self._entity_store.put(STORES, store.workspace_id, store.id, store)
        return await super().update_store(store)

    async def create_location(self, location: Location) -> Location:
        await self._entity_store.put(LOCATIONS, location.workspace_id, location.id, location)
        return await super().create_location(location)

    async def update_location(self, location: Location) -> Location:
        await self._entity_store.put(LOCATIONS, location.workspace_id, location.id, location)
        return await super().update_location(location)

    async def create_product(self, product: Product) -> Product:
        await self._entity_store.put(PRODUCTS, product.workspace_id, product.id, product)
        return await super().create_product(product)

    async def update_product(self, product: Product) -> Product:
        await self._entity_store.put(PRODUCTS, product.workspace_id, product.id, product)
        return await super().update_product(product)

    async def create_media(self, media: Media) -> Media:
        await self._entity_store.put(MEDIA, media.workspace_id, media.id, media)
        return await super().create_media(media)

    async def update_media(self, media: Media) -> Media:
        await self._entity_store.put(MEDIA, media.workspace_id, media.id, media)
        return await super().update_media(media)

    async def add_active_policy_product_reference(
        self, workspace_id: UUID, product_id: UUID
    ) -> None:
        await self._entity_store.put_marker(
            POLICY_PRODUCT_REFS,
            _ref_doc_id(workspace_id, product_id),
            {"workspace_id": str(workspace_id), "product_id": str(product_id)},
        )
        await super().add_active_policy_product_reference(workspace_id, product_id)

    async def remove_active_policy_product_reference(
        self, workspace_id: UUID, product_id: UUID
    ) -> None:
        await self._entity_store.delete(POLICY_PRODUCT_REFS, _ref_doc_id(workspace_id, product_id))
        await super().remove_active_policy_product_reference(workspace_id, product_id)


class FirestoreBackedPolicyRepository(FirestoreWriteThrough, InMemoryPolicyRepository):
    def __init__(self, client: Any | None = None, project_id: str | None = None) -> None:
        InMemoryPolicyRepository.__init__(self)
        self._init_store(client, project_id)

    async def _load_entities(self) -> None:
        for ws, promo in await self._entity_store.load(PROMOTIONS, Promotion):
            self.promotions[(ws, promo.id)] = promo
        for ws, pv in await self._entity_store.load(POLICY_VERSIONS, PolicyVersion):
            self.policy_versions[(ws, pv.promotion_id, pv.version)] = pv
            self.policy_versions_by_id[(ws, pv.id)] = pv

    async def create_promotion(self, workspace_id: UUID, promotion: Promotion) -> Promotion:
        await self._entity_store.put(PROMOTIONS, workspace_id, promotion.id, promotion)
        return await super().create_promotion(workspace_id, promotion)

    async def update_promotion(self, workspace_id: UUID, promotion: Promotion) -> Promotion:
        await self._entity_store.put(PROMOTIONS, workspace_id, promotion.id, promotion)
        return await super().update_promotion(workspace_id, promotion)

    async def create_policy_version(
        self, workspace_id: UUID, policy_version: PolicyVersion
    ) -> PolicyVersion:
        await self._entity_store.put(
            POLICY_VERSIONS, workspace_id, policy_version.id, policy_version
        )
        return await super().create_policy_version(workspace_id, policy_version)


class FirestoreBackedVisitRepository(FirestoreWriteThrough, InMemoryVisitRepository):
    def __init__(self, client: Any | None = None, project_id: str | None = None) -> None:
        InMemoryVisitRepository.__init__(self)
        self._init_store(client, project_id)

    async def _load_entities(self) -> None:
        s = self._entity_store
        for ws, vis in await s.load(VISITS, Visit):
            self._visits[(ws, vis.id)] = vis
        for ws, inv in await s.load(INVESTIGATIONS, Investigation):
            self._investigations[(ws, inv.id)] = inv
        for ws, ev in await s.load(EVIDENCE, Evidence):
            self._evidence[(ws, ev.id)] = ev
        for ws, rep in await s.load(REPORTS, Report):
            self._reports[(ws, rep.id)] = rep

    async def create_visit(self, workspace_id: UUID, visit: Visit) -> Visit:
        await self._entity_store.put(VISITS, workspace_id, visit.id, visit)
        return await super().create_visit(workspace_id, visit)

    async def update_visit(self, workspace_id: UUID, visit: Visit) -> Visit:
        await self._entity_store.put(VISITS, workspace_id, visit.id, visit)
        return await super().update_visit(workspace_id, visit)

    async def create_investigation(
        self, workspace_id: UUID, investigation: Investigation
    ) -> Investigation:
        await self._entity_store.put(INVESTIGATIONS, workspace_id, investigation.id, investigation)
        return await super().create_investigation(workspace_id, investigation)

    async def update_investigation(
        self, workspace_id: UUID, investigation: Investigation
    ) -> Investigation:
        await self._entity_store.put(INVESTIGATIONS, workspace_id, investigation.id, investigation)
        return await super().update_investigation(workspace_id, investigation)

    async def save_evidence(self, workspace_id: UUID, evidence: Evidence) -> Evidence:
        await self._entity_store.put(EVIDENCE, workspace_id, evidence.id, evidence)
        return await super().save_evidence(workspace_id, evidence)

    async def save_report(self, workspace_id: UUID, report: Report) -> Report:
        await self._entity_store.put(REPORTS, workspace_id, report.id, report)
        return await super().save_report(workspace_id, report)


class FirestoreBackedVerificationRepository(FirestoreWriteThrough, InMemoryVerificationRepository):
    def __init__(self, client: Any | None = None, project_id: str | None = None) -> None:
        InMemoryVerificationRepository.__init__(self)
        self._init_store(client, project_id)

    async def _load_entities(self) -> None:
        for ws, ver in await self._entity_store.load(VERIFICATIONS, Verification):
            self._verifications[(ws, ver.id)] = ver

    async def save_verification(
        self, workspace_id: UUID, verification: Verification
    ) -> Verification:
        await self._entity_store.put(VERIFICATIONS, workspace_id, verification.id, verification)
        return await super().save_verification(workspace_id, verification)

    async def update_verification(
        self, workspace_id: UUID, verification: Verification
    ) -> Verification:
        await self._entity_store.put(VERIFICATIONS, workspace_id, verification.id, verification)
        return await super().update_verification(workspace_id, verification)
