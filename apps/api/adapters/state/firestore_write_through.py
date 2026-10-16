"""Firestore-backed (write-through) variants of the in-memory module repositories.

Each mutator runs the in-memory implementation FIRST (it applies the repository's
invariants), then persists the result to Firestore. If persisting raises, the
in-memory change is reverted and the error propagates, so the request fails and a
rejected mutation never reaches Firestore. Reads stay in memory; load() fills
memory at startup.

Requires a single API instance (Cloud Run max-instances=1); see
firestore_persistence.py for the constraint and document layout.
"""

import logging
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

from apps.api.adapters.state.firestore_persistence import FirestoreWriteThrough, UndoLog
from apps.api.modules.catalog.repository import InMemoryCatalogRepository
from apps.api.modules.policies.repository import InMemoryPolicyRepository
from apps.api.modules.verification.repository import InMemoryVerificationRepository
from apps.api.modules.visits.repository import InMemoryVisitRepository

logger = logging.getLogger(__name__)

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

    def _store_undo(self, store: Store) -> UndoLog:
        ws = store.workspace_id
        return (
            UndoLog()
            .track(self._stores, (ws, store.id))
            .track(self._stores_by_code, (ws, store.code))
        )

    def _location_undo(self, location: Location, undo: UndoLog | None = None) -> UndoLog:
        ws = location.workspace_id
        return (
            (undo or UndoLog())
            .track(self._locations, (ws, location.id))
            .track(self._locations_by_code, (ws, location.code))
        )

    def _product_undo(self, product: Product) -> UndoLog:
        ws = product.workspace_id
        return (
            UndoLog()
            .track(self._products, (ws, product.id))
            .track(self._products_by_sku, (ws, product.sku))
        )

    async def _put_store_with_backroom(self, created: tuple[Store, Location]) -> None:
        store, backroom = created
        await self._entity_store.put(LOCATIONS, backroom.workspace_id, backroom.id, backroom)
        try:
            await self._entity_store.put(STORES, store.workspace_id, store.id, store)
        except BaseException:
            # Do not leave an orphan backroom document that would reappear on load().
            try:
                await self._entity_store.delete(LOCATIONS, str(backroom.id))
            except Exception:
                logger.exception("Could not remove orphan backroom document %s", backroom.id)
            raise

    async def create_store_with_backroom(
        self, store: Store, backroom: Location
    ) -> tuple[Store, Location]:
        undo = self._location_undo(backroom, self._store_undo(store))
        return await self._write_through(
            undo,
            lambda: super(FirestoreBackedCatalogRepository, self).create_store_with_backroom(
                store, backroom
            ),
            self._put_store_with_backroom,
        )

    async def update_store(self, store: Store) -> Store:
        return await self._write_through(
            self._store_undo(store),
            lambda: super(FirestoreBackedCatalogRepository, self).update_store(store),
            lambda s: self._entity_store.put(STORES, s.workspace_id, s.id, s),
        )

    async def create_location(self, location: Location) -> Location:
        return await self._write_through(
            self._location_undo(location),
            lambda: super(FirestoreBackedCatalogRepository, self).create_location(location),
            lambda loc: self._entity_store.put(LOCATIONS, loc.workspace_id, loc.id, loc),
        )

    async def update_location(self, location: Location) -> Location:
        return await self._write_through(
            self._location_undo(location),
            lambda: super(FirestoreBackedCatalogRepository, self).update_location(location),
            lambda loc: self._entity_store.put(LOCATIONS, loc.workspace_id, loc.id, loc),
        )

    async def create_product(self, product: Product) -> Product:
        return await self._write_through(
            self._product_undo(product),
            lambda: super(FirestoreBackedCatalogRepository, self).create_product(product),
            lambda p: self._entity_store.put(PRODUCTS, p.workspace_id, p.id, p),
        )

    async def update_product(self, product: Product) -> Product:
        return await self._write_through(
            self._product_undo(product),
            lambda: super(FirestoreBackedCatalogRepository, self).update_product(product),
            lambda p: self._entity_store.put(PRODUCTS, p.workspace_id, p.id, p),
        )

    async def create_media(self, media: Media) -> Media:
        return await self._write_through(
            UndoLog().track(self._media, (media.workspace_id, media.id)),
            lambda: super(FirestoreBackedCatalogRepository, self).create_media(media),
            lambda m: self._entity_store.put(MEDIA, m.workspace_id, m.id, m),
        )

    async def update_media(self, media: Media) -> Media:
        return await self._write_through(
            UndoLog().track(self._media, (media.workspace_id, media.id)),
            lambda: super(FirestoreBackedCatalogRepository, self).update_media(media),
            lambda m: self._entity_store.put(MEDIA, m.workspace_id, m.id, m),
        )

    async def add_active_policy_product_reference(
        self, workspace_id: UUID, product_id: UUID
    ) -> None:
        await self._write_through(
            UndoLog().track(self._active_policy_product_references, (workspace_id, product_id)),
            lambda: super(
                FirestoreBackedCatalogRepository, self
            ).add_active_policy_product_reference(workspace_id, product_id),
            lambda _: self._entity_store.put_marker(
                POLICY_PRODUCT_REFS,
                _ref_doc_id(workspace_id, product_id),
                {"workspace_id": str(workspace_id), "product_id": str(product_id)},
            ),
        )

    async def remove_active_policy_product_reference(
        self, workspace_id: UUID, product_id: UUID
    ) -> None:
        await self._write_through(
            UndoLog().track(self._active_policy_product_references, (workspace_id, product_id)),
            lambda: super(
                FirestoreBackedCatalogRepository, self
            ).remove_active_policy_product_reference(workspace_id, product_id),
            lambda _: self._entity_store.delete(
                POLICY_PRODUCT_REFS, _ref_doc_id(workspace_id, product_id)
            ),
        )


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
        return await self._write_through(
            UndoLog().track(self.promotions, (workspace_id, promotion.id)),
            lambda: super(FirestoreBackedPolicyRepository, self).create_promotion(
                workspace_id, promotion
            ),
            lambda p: self._entity_store.put(PROMOTIONS, workspace_id, p.id, p),
        )

    async def update_promotion(self, workspace_id: UUID, promotion: Promotion) -> Promotion:
        return await self._write_through(
            UndoLog().track(self.promotions, (workspace_id, promotion.id)),
            lambda: super(FirestoreBackedPolicyRepository, self).update_promotion(
                workspace_id, promotion
            ),
            lambda p: self._entity_store.put(PROMOTIONS, workspace_id, p.id, p),
        )

    async def create_policy_version(
        self, workspace_id: UUID, policy_version: PolicyVersion
    ) -> PolicyVersion:
        undo = (
            UndoLog()
            .track(
                self.policy_versions,
                (workspace_id, policy_version.promotion_id, policy_version.version),
            )
            .track(self.policy_versions_by_id, (workspace_id, policy_version.id))
        )
        return await self._write_through(
            undo,
            lambda: super(FirestoreBackedPolicyRepository, self).create_policy_version(
                workspace_id, policy_version
            ),
            lambda pv: self._entity_store.put(POLICY_VERSIONS, workspace_id, pv.id, pv),
        )


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
        return await self._write_through(
            UndoLog().track(self._visits, (workspace_id, visit.id)),
            lambda: super(FirestoreBackedVisitRepository, self).create_visit(workspace_id, visit),
            lambda v: self._entity_store.put(VISITS, workspace_id, v.id, v),
        )

    async def update_visit(self, workspace_id: UUID, visit: Visit) -> Visit:
        return await self._write_through(
            UndoLog().track(self._visits, (workspace_id, visit.id)),
            lambda: super(FirestoreBackedVisitRepository, self).update_visit(workspace_id, visit),
            lambda v: self._entity_store.put(VISITS, workspace_id, v.id, v),
        )

    async def create_investigation(
        self, workspace_id: UUID, investigation: Investigation
    ) -> Investigation:
        return await self._write_through(
            UndoLog().track(self._investigations, (workspace_id, investigation.id)),
            lambda: super(FirestoreBackedVisitRepository, self).create_investigation(
                workspace_id, investigation
            ),
            lambda i: self._entity_store.put(INVESTIGATIONS, workspace_id, i.id, i),
        )

    async def update_investigation(
        self, workspace_id: UUID, investigation: Investigation
    ) -> Investigation:
        return await self._write_through(
            UndoLog().track(self._investigations, (workspace_id, investigation.id)),
            lambda: super(FirestoreBackedVisitRepository, self).update_investigation(
                workspace_id, investigation
            ),
            lambda i: self._entity_store.put(INVESTIGATIONS, workspace_id, i.id, i),
        )

    async def save_evidence(self, workspace_id: UUID, evidence: Evidence) -> Evidence:
        return await self._write_through(
            UndoLog().track(self._evidence, (workspace_id, evidence.id)),
            lambda: super(FirestoreBackedVisitRepository, self).save_evidence(
                workspace_id, evidence
            ),
            lambda e: self._entity_store.put(EVIDENCE, workspace_id, e.id, e),
        )

    async def save_report(self, workspace_id: UUID, report: Report) -> Report:
        return await self._write_through(
            UndoLog().track(self._reports, (workspace_id, report.id)),
            lambda: super(FirestoreBackedVisitRepository, self).save_report(workspace_id, report),
            lambda r: self._entity_store.put(REPORTS, workspace_id, r.id, r),
        )


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
        return await self._write_through(
            UndoLog().track(self._verifications, (workspace_id, verification.id)),
            lambda: super(FirestoreBackedVerificationRepository, self).save_verification(
                workspace_id, verification
            ),
            lambda v: self._entity_store.put(VERIFICATIONS, workspace_id, v.id, v),
        )

    async def update_verification(
        self, workspace_id: UUID, verification: Verification
    ) -> Verification:
        return await self._write_through(
            UndoLog().track(self._verifications, (workspace_id, verification.id)),
            lambda: super(FirestoreBackedVerificationRepository, self).update_verification(
                workspace_id, verification
            ),
            lambda v: self._entity_store.put(VERIFICATIONS, workspace_id, v.id, v),
        )
