from typing import Any, Protocol
from uuid import UUID


class AnalyticsRepository(Protocol):
    async def commit_import_batch(
        self,
        workspace_id: UUID,
        batch_id: str,
        kind: str,
        import_id: UUID,
        source_sha256: str,
        rows: list[dict[str, Any]],
    ) -> int:
        """Atomically commit staged sales or inventory rows and batch manifest."""
        ...

    async def get_sales_window(
        self,
        workspace_id: UUID,
        store_id: UUID,
        start_date: str,
        end_date: str,
        batch_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve sales facts for a store across a frozen set of committed batch IDs."""
        ...

    async def get_latest_inventory(
        self,
        workspace_id: UUID,
        location_ids: list[UUID],
        as_of_time: str,
        batch_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve latest inventory records for locations at or before as_of_time."""
        ...
