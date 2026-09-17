import asyncio
import base64
import binascii
from typing import Protocol
from uuid import UUID

from storeops_contracts.models import (
    Evidence,
    Investigation,
    Report,
    Visit,
)

from apps.api.core.errors import ApiError


class VisitRepository(Protocol):
    async def create_visit(self, workspace_id: UUID, visit: Visit) -> Visit:
        """Persist a new visit."""
        ...

    async def get_visit(self, workspace_id: UUID, visit_id: UUID) -> Visit | None:
        """Fetch visit by ID in workspace."""
        ...

    async def update_visit(self, workspace_id: UUID, visit: Visit) -> Visit:
        """Update an existing visit."""
        ...

    async def list_visits(
        self,
        workspace_id: UUID,
        store_id: UUID | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Visit], str | None]:
        """List visits with optional store filtering and pagination."""
        ...

    async def create_investigation(
        self, workspace_id: UUID, investigation: Investigation
    ) -> Investigation:
        """Persist a new investigation."""
        ...

    async def get_investigation(
        self, workspace_id: UUID, investigation_id: UUID
    ) -> Investigation | None:
        """Fetch investigation by ID in workspace."""
        ...

    async def update_investigation(
        self, workspace_id: UUID, investigation: Investigation
    ) -> Investigation:
        """Update an existing investigation."""
        ...

    async def list_investigations(
        self,
        workspace_id: UUID,
        store_id: UUID | None = None,
        visit_id: UUID | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Investigation], str | None]:
        """List investigations with optional store/visit filtering and pagination."""
        ...

    async def save_evidence(self, workspace_id: UUID, evidence: Evidence) -> Evidence:
        """Persist an evidence item."""
        ...

    async def get_evidence(
        self, workspace_id: UUID, evidence_id: UUID
    ) -> Evidence | None:
        """Fetch evidence item by ID in workspace."""
        ...

    async def list_evidence(
        self,
        workspace_id: UUID,
        investigation_id: UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Evidence], str | None]:
        """List evidence items for an investigation with pagination."""
        ...

    async def save_report(self, workspace_id: UUID, report: Report) -> Report:
        """Persist a final report."""
        ...

    async def get_report(self, workspace_id: UUID, report_id: UUID) -> Report | None:
        """Fetch report by ID in workspace."""
        ...


class InMemoryVisitRepository:
    """In-memory implementation of VisitRepository for testing and LOCAL profile."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        # (workspace_id, visit_id) -> Visit
        self._visits: dict[tuple[UUID, UUID], Visit] = {}
        # (workspace_id, investigation_id) -> Investigation
        self._investigations: dict[tuple[UUID, UUID], Investigation] = {}
        # (workspace_id, evidence_id) -> Evidence
        self._evidence: dict[tuple[UUID, UUID], Evidence] = {}
        # (workspace_id, report_id) -> Report
        self._reports: dict[tuple[UUID, UUID], Report] = {}

    def clear(self) -> None:
        self._visits.clear()
        self._investigations.clear()
        self._evidence.clear()
        self._reports.clear()

    async def create_visit(self, workspace_id: UUID, visit: Visit) -> Visit:
        async with self._lock:
            self._visits[(workspace_id, visit.id)] = visit.model_copy(deep=True)
            return visit.model_copy(deep=True)

    async def get_visit(self, workspace_id: UUID, visit_id: UUID) -> Visit | None:
        async with self._lock:
            vis = self._visits.get((workspace_id, visit_id))
            return vis.model_copy(deep=True) if vis else None

    async def update_visit(self, workspace_id: UUID, visit: Visit) -> Visit:
        async with self._lock:
            self._visits[(workspace_id, visit.id)] = visit.model_copy(deep=True)
            return visit.model_copy(deep=True)

    async def list_visits(
        self,
        workspace_id: UUID,
        store_id: UUID | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Visit], str | None]:
        items = [
            v.model_copy(deep=True)
            for (ws, _), v in self._visits.items()
            if ws == workspace_id and (store_id is None or v.store_id == store_id)
        ]
        # Sort descending by (created_at, id)
        items.sort(key=lambda x: (x.created_at, x.id), reverse=True)

        start_idx = 0
        if cursor:
            try:
                decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
                start_idx = int(decoded)
            except (ValueError, binascii.Error) as err:
                raise ApiError(
                    status_code=422,
                    code="INVALID_CURSOR",
                    message="Malformed pagination cursor",
                ) from err

        paginated = items[start_idx : start_idx + limit]
        next_cursor = None
        if start_idx + limit < len(items):
            next_cursor = base64.urlsafe_b64encode(
                str(start_idx + limit).encode()
            ).decode()

        return paginated, next_cursor

    async def create_investigation(
        self, workspace_id: UUID, investigation: Investigation
    ) -> Investigation:
        async with self._lock:
            self._investigations[(workspace_id, investigation.id)] = (
                investigation.model_copy(deep=True)
            )
            return investigation.model_copy(deep=True)

    async def get_investigation(
        self, workspace_id: UUID, investigation_id: UUID
    ) -> Investigation | None:
        async with self._lock:
            inv = self._investigations.get((workspace_id, investigation_id))
            return inv.model_copy(deep=True) if inv else None

    async def update_investigation(
        self, workspace_id: UUID, investigation: Investigation
    ) -> Investigation:
        async with self._lock:
            self._investigations[(workspace_id, investigation.id)] = (
                investigation.model_copy(deep=True)
            )
            return investigation.model_copy(deep=True)

    async def list_investigations(
        self,
        workspace_id: UUID,
        store_id: UUID | None = None,
        visit_id: UUID | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Investigation], str | None]:
        async with self._lock:
            items = [
                inv.model_copy(deep=True)
                for (ws, _), inv in self._investigations.items()
                if ws == workspace_id
                and (store_id is None or inv.store_id == store_id)
                and (visit_id is None or inv.visit_id == visit_id)
            ]
        items.sort(key=lambda x: (x.created_at, x.id), reverse=True)

        start_idx = 0
        if cursor:
            try:
                decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
                start_idx = int(decoded)
            except (ValueError, binascii.Error) as err:
                raise ApiError(
                    status_code=422,
                    code="INVALID_CURSOR",
                    message="Malformed pagination cursor",
                ) from err

        paginated = items[start_idx : start_idx + limit]
        next_cursor = None
        if start_idx + limit < len(items):
            next_cursor = base64.urlsafe_b64encode(
                str(start_idx + limit).encode()
            ).decode()

        return paginated, next_cursor

    async def save_evidence(self, workspace_id: UUID, evidence: Evidence) -> Evidence:
        async with self._lock:
            self._evidence[(workspace_id, evidence.id)] = evidence.model_copy(deep=True)
            return evidence.model_copy(deep=True)

    async def get_evidence(
        self, workspace_id: UUID, evidence_id: UUID
    ) -> Evidence | None:
        async with self._lock:
            ev = self._evidence.get((workspace_id, evidence_id))
            return ev.model_copy(deep=True) if ev else None

    async def list_evidence(
        self,
        workspace_id: UUID,
        investigation_id: UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Evidence], str | None]:
        async with self._lock:
            items = [
                ev.model_copy(deep=True)
                for (ws, _), ev in self._evidence.items()
                if ws == workspace_id and ev.investigation_id == investigation_id
            ]
        items.sort(key=lambda x: (x.retrieved_at, x.id), reverse=True)

        start_idx = 0
        if cursor:
            try:
                decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
                start_idx = int(decoded)
            except (ValueError, binascii.Error) as err:
                raise ApiError(
                    status_code=422,
                    code="INVALID_CURSOR",
                    message="Malformed pagination cursor",
                ) from err

        paginated = items[start_idx : start_idx + limit]
        next_cursor = None
        if start_idx + limit < len(items):
            next_cursor = base64.urlsafe_b64encode(
                str(start_idx + limit).encode()
            ).decode()

        return paginated, next_cursor

    async def save_report(self, workspace_id: UUID, report: Report) -> Report:
        async with self._lock:
            self._reports[(workspace_id, report.id)] = report.model_copy(deep=True)
            return report.model_copy(deep=True)

    async def get_report(self, workspace_id: UUID, report_id: UUID) -> Report | None:
        async with self._lock:
            rep = self._reports.get((workspace_id, report_id))
            return rep.model_copy(deep=True) if rep else None
