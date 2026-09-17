"""Ports for Verification module dependencies."""

from typing import Protocol
from uuid import UUID

from storeops_contracts.models import (
    Evidence,
    Investigation,
    Media,
    PolicyVersion,
    Product,
    Promotion,
    Report,
    Store,
    Visit,
)


class VerificationVisitPort(Protocol):
    """Port for interacting with Visit, Investigation, Evidence, and Report persistence."""

    async def get_visit(self, workspace_id: UUID, visit_id: UUID) -> Visit | None: ...

    async def update_visit(self, workspace_id: UUID, visit: Visit) -> Visit: ...

    async def get_investigation(
        self, workspace_id: UUID, investigation_id: UUID
    ) -> Investigation | None: ...

    async def update_investigation(
        self, workspace_id: UUID, investigation: Investigation
    ) -> Investigation: ...

    async def save_evidence(
        self, workspace_id: UUID, evidence: Evidence
    ) -> Evidence: ...

    async def save_report(self, workspace_id: UUID, report: Report) -> Report: ...

    async def get_report(
        self, workspace_id: UUID, report_id: UUID
    ) -> Report | None: ...


class VerificationPolicyPort(Protocol):
    """Port for interacting with Policies and Promotions."""

    async def get_promotion(
        self, workspace_id: UUID, promotion_id: UUID
    ) -> Promotion | None: ...

    async def get_policy_version_by_id(
        self, workspace_id: UUID, version_id: UUID
    ) -> PolicyVersion | None: ...


class VerificationCatalogPort(Protocol):
    """Port for interacting with Stores, Media, and Products."""

    async def get_store(self, workspace_id: UUID, store_id: UUID) -> Store | None: ...

    async def get_media(self, workspace_id: UUID, media_id: UUID) -> Media | None: ...

    async def get_product(
        self, workspace_id: UUID, product_id: UUID
    ) -> Product | None: ...
