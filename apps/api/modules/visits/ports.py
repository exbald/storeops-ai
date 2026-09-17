from typing import Protocol
from uuid import UUID

from storeops_contracts.models import Media, PolicyVersion, Product, Promotion, Store


class VisitCatalogPort(Protocol):
    """Catalog read port for visit and investigation processing."""

    async def get_store(self, workspace_id: UUID, store_id: UUID) -> Store | None: ...

    async def get_media(self, workspace_id: UUID, media_id: UUID) -> Media | None: ...

    async def get_product(
        self, workspace_id: UUID, product_id: UUID
    ) -> Product | None: ...


class VisitPolicyPort(Protocol):
    """Policy read port for visit and investigation processing."""

    async def get_promotion(
        self, workspace_id: UUID, promotion_id: UUID
    ) -> Promotion | None: ...

    async def get_policy_version(
        self, workspace_id: UUID, version_id: UUID
    ) -> PolicyVersion | None: ...

    async def get_latest_policy_version(
        self, workspace_id: UUID, promotion_id: UUID
    ) -> PolicyVersion | None: ...
