import logging
from typing import Any
from uuid import UUID

from apps.api.ports.analytics import AnalyticsRepository

logger = logging.getLogger("storeops.analytics.bigquery")


class BigQueryAnalyticsRepository(AnalyticsRepository):
    """Google Cloud BigQuery implementation of AnalyticsRepository.

    Used in CLOUD profile. Validated in T12 parity testing.
    """

    def __init__(
        self, project_id: str | None = None, dataset_id: str | None = None
    ) -> None:
        self.project_id = project_id
        self.dataset_id = dataset_id
        try:
            from google.cloud import bigquery  # type: ignore

            self._client = bigquery.Client(project=self.project_id)
        except (ImportError, RuntimeError, ValueError):
            self._client = None

    async def commit_import_batch(
        self,
        workspace_id: UUID,
        batch_id: str,
        kind: str,
        import_id: UUID,
        source_sha256: str,
        rows: list[dict[str, Any]],
    ) -> int:
        raise NotImplementedError(
            "BigQuery adapter commit will be implemented in T12 cloud parity gate"
        )

    async def get_sales_window(
        self,
        workspace_id: UUID,
        store_id: UUID,
        start_date: str,
        end_date: str,
        batch_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "BigQuery adapter queries will be implemented in T12 cloud parity gate"
        )

    async def get_latest_inventory(
        self,
        workspace_id: UUID,
        location_ids: list[UUID],
        as_of_time: str,
        batch_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "BigQuery adapter queries will be implemented in T12 cloud parity gate"
        )
