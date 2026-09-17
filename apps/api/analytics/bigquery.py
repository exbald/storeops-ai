"""Google Cloud BigQuery implementation of AnalyticsRepository.

Used in CLOUD profile. Validated in T12 parity testing.
Enforces disposable target safety and identical semantics to DuckDB.
"""

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from apps.api.ports.analytics import AnalyticsRepository

logger = logging.getLogger("storeops.analytics.bigquery")


class BigQueryAnalyticsRepository(AnalyticsRepository):
    """Google Cloud BigQuery implementation of AnalyticsRepository.

    Provides exact parity with DuckDBAnalyticsRepository for:
    - Latest revision resolution across committed import batches.
    - Deterministic tie-breaking on (committed_at DESC, batch_id DESC).
    - Missing sales dates preservation (unknown, not zero).
    - Exact decimal currency arithmetic.
    - Snapshot isolation via batch_ids filtering.
    """

    def __init__(
        self,
        project_id: str | None = None,
        dataset_id: str | None = None,
        allow_prod: bool = False,
    ) -> None:
        self.project_id = project_id or "storeops-dev"
        self.dataset_id = dataset_id or "disposable_test_analytics"
        self.allow_prod = allow_prod

        # Safety check: Prevent targeting production datasets or projects without explicit override
        if not self.allow_prod:
            ds_lower = self.dataset_id.lower()
            proj_lower = self.project_id.lower()
            if "prod" in proj_lower and not ("test" in proj_lower or "dev" in proj_lower or "disposable" in proj_lower):
                raise ValueError(
                    f"Refusing to target production-like project '{self.project_id}' without allow_prod=True"
                )
            if "prod" in ds_lower and not ("test" in ds_lower or "dev" in ds_lower or "disposable" in ds_lower):
                raise ValueError(
                    f"Refusing to target production-like dataset '{self.dataset_id}' without allow_prod=True"
                )

        try:
            from google.cloud import bigquery  # type: ignore

            self._client = bigquery.Client(project=self.project_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("BigQuery client initialization failed or skipped: %s", exc)
            self._client = None

    def _get_table_id(self, table_name: str) -> str:
        return f"`{self.project_id}.{self.dataset_id}.{table_name}`"

    def _build_sales_window_query(
        self,
        workspace_id: UUID,
        store_id: UUID,
        start_date: str,
        end_date: str,
        batch_ids: list[str] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        table_sales = self._get_table_id("sales_facts")
        table_batches = self._get_table_id("import_batches")

        batch_filter = ""
        params: dict[str, Any] = {
            "workspace_id": str(workspace_id),
            "store_id": str(store_id),
            "start_date": start_date,
            "end_date": end_date,
        }

        if batch_ids is not None:
            batch_filter = "AND s.batch_id IN UNNEST(@batch_ids)"
            params["batch_ids"] = batch_ids

        query = f"""
        WITH ranked AS (
            SELECT s.workspace_id, s.batch_id, s.store_id, s.sku, s.business_date,
                   s.units, s.revenue, s.currency, b.committed_at,
                   ROW_NUMBER() OVER(
                       PARTITION BY s.workspace_id, s.store_id, s.sku, s.business_date
                       ORDER BY b.committed_at DESC, s.batch_id DESC
                   ) as rn
            FROM {table_sales} s
            JOIN {table_batches} b ON s.batch_id = b.batch_id
            WHERE s.workspace_id = @workspace_id
              AND s.store_id = @store_id
              AND s.business_date >= @start_date
              AND s.business_date <= @end_date
              {batch_filter}
        )
        SELECT store_id, sku, business_date, units, revenue, currency, batch_id
        FROM ranked
        WHERE rn = 1
        ORDER BY business_date ASC, sku ASC
        """
        return query, params

    def _build_latest_inventory_query(
        self,
        workspace_id: UUID,
        location_ids: list[UUID],
        as_of_time: str,
        batch_ids: list[str] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        table_inv = self._get_table_id("inventory_facts")
        table_batches = self._get_table_id("import_batches")

        batch_filter = ""
        params: dict[str, Any] = {
            "workspace_id": str(workspace_id),
            "as_of_time": as_of_time,
            "location_ids": [str(lid) for lid in location_ids],
        }

        if batch_ids is not None:
            batch_filter = "AND i.batch_id IN UNNEST(@batch_ids)"
            params["batch_ids"] = batch_ids

        query = f"""
        WITH ranked AS (
            SELECT i.location_id, i.sku, i.observed_at, i.quantity, i.unit,
                   i.normalized_units, i.batch_id, b.committed_at,
                   ROW_NUMBER() OVER(
                       PARTITION BY i.workspace_id, i.location_id, i.sku
                       ORDER BY i.observed_at DESC, b.committed_at DESC, i.batch_id DESC
                   ) as rn
            FROM {table_inv} i
            JOIN {table_batches} b ON i.batch_id = b.batch_id
            WHERE i.workspace_id = @workspace_id
              AND i.observed_at <= @as_of_time
              AND i.location_id IN UNNEST(@location_ids)
              {batch_filter}
        )
        SELECT location_id, sku, observed_at, quantity, unit, normalized_units, batch_id
        FROM ranked
        WHERE rn = 1
        ORDER BY location_id ASC, sku ASC
        """
        return query, params

    async def commit_import_batch(
        self,
        workspace_id: UUID,
        batch_id: str,
        kind: str,
        import_id: UUID,
        source_sha256: str,
        rows: list[dict[str, Any]],
    ) -> int:
        if self._client is None:
            raise RuntimeError(
                "BigQuery client not available. Live cloud credentials required."
            )

        # Re-check idempotency in BigQuery
        check_query = f"""
        SELECT COUNT(1) as cnt
        FROM {self._get_table_id('import_batches')}
        WHERE workspace_id = @workspace_id AND batch_id = @batch_id
        """
        from google.cloud import bigquery  # type: ignore

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("workspace_id", "STRING", str(workspace_id)),
                bigquery.ScalarQueryParameter("batch_id", "STRING", batch_id),
            ]
        )
        query_job = self._client.query(check_query, job_config=job_config)
        results = list(query_job.result())
        if results and results[0]["cnt"] > 0:
            return len(rows)

        # Insert manifest
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        manifest_row = {
            "workspace_id": str(workspace_id),
            "batch_id": batch_id,
            "kind": kind,
            "import_id": str(import_id),
            "source_sha256": source_sha256,
            "row_count": len(rows),
            "committed_at": now.isoformat(),
        }
        self._client.insert_rows_json(
            self._get_table_id("import_batches").strip("`"), [manifest_row]
        )

        # Insert facts
        if kind == "SALES":
            sales_rows = [
                {
                    "workspace_id": str(workspace_id),
                    "batch_id": batch_id,
                    "store_id": str(r["store_id"]),
                    "sku": str(r["sku"]),
                    "business_date": str(r["business_date"]),
                    "units": int(r["units"]),
                    "revenue": str(r["revenue"]) if isinstance(r["revenue"], Decimal) else str(Decimal(str(r["revenue"]))),
                    "currency": str(r["currency"]),
                }
                for r in rows
            ]
            self._client.insert_rows_json(
                self._get_table_id("sales_facts").strip("`"), sales_rows
            )
        elif kind == "INVENTORY":
            inv_rows = [
                {
                    "workspace_id": str(workspace_id),
                    "batch_id": batch_id,
                    "location_id": str(r["location_id"]),
                    "sku": str(r["sku"]),
                    "observed_at": str(r["observed_at"]),
                    "quantity": int(r["quantity"]),
                    "unit": str(r["unit"]),
                    "normalized_units": int(r["normalized_units"]),
                }
                for r in rows
            ]
            self._client.insert_rows_json(
                self._get_table_id("inventory_facts").strip("`"), inv_rows
            )

        return len(rows)

    async def get_sales_window(
        self,
        workspace_id: UUID,
        store_id: UUID,
        start_date: str,
        end_date: str,
        batch_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if batch_ids is not None and len(batch_ids) == 0:
            return []

        if self._client is None:
            raise RuntimeError(
                "BigQuery client not available. Live cloud credentials required."
            )

        from google.cloud import bigquery  # type: ignore

        query, params = self._build_sales_window_query(
            workspace_id, store_id, start_date, end_date, batch_ids
        )
        query_params = [
            bigquery.ScalarQueryParameter("workspace_id", "STRING", params["workspace_id"]),
            bigquery.ScalarQueryParameter("store_id", "STRING", params["store_id"]),
            bigquery.ScalarQueryParameter("start_date", "DATE", params["start_date"]),
            bigquery.ScalarQueryParameter("end_date", "DATE", params["end_date"]),
        ]
        if "batch_ids" in params:
            query_params.append(
                bigquery.ArrayQueryParameter("batch_ids", "STRING", params["batch_ids"])
            )

        job_config = bigquery.QueryJobConfig(query_parameters=query_params)
        query_job = self._client.query(query, job_config=job_config)

        results: list[dict[str, Any]] = []
        for row in query_job.result():
            results.append(
                {
                    "store_id": UUID(row["store_id"]),
                    "sku": row["sku"],
                    "business_date": str(row["business_date"]),
                    "units": int(row["units"]),
                    "revenue": Decimal(str(row["revenue"])),
                    "currency": row["currency"],
                    "batch_id": row["batch_id"],
                }
            )
        return results

    async def get_latest_inventory(
        self,
        workspace_id: UUID,
        location_ids: list[UUID],
        as_of_time: str,
        batch_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not location_ids:
            return []
        if batch_ids is not None and len(batch_ids) == 0:
            return []

        if self._client is None:
            raise RuntimeError(
                "BigQuery client not available. Live cloud credentials required."
            )

        from google.cloud import bigquery  # type: ignore

        query, params = self._build_latest_inventory_query(
            workspace_id, location_ids, as_of_time, batch_ids
        )
        query_params = [
            bigquery.ScalarQueryParameter("workspace_id", "STRING", params["workspace_id"]),
            bigquery.ScalarQueryParameter("as_of_time", "TIMESTAMP", params["as_of_time"]),
            bigquery.ArrayQueryParameter("location_ids", "STRING", params["location_ids"]),
        ]
        if "batch_ids" in params:
            query_params.append(
                bigquery.ArrayQueryParameter("batch_ids", "STRING", params["batch_ids"])
            )

        job_config = bigquery.QueryJobConfig(query_parameters=query_params)
        query_job = self._client.query(query, job_config=job_config)

        results: list[dict[str, Any]] = []
        for row in query_job.result():
            results.append(
                {
                    "location_id": UUID(row["location_id"]),
                    "sku": row["sku"],
                    "observed_at": str(row["observed_at"]),
                    "quantity": int(row["quantity"]),
                    "unit": row["unit"],
                    "normalized_units": int(row["normalized_units"]),
                    "batch_id": row["batch_id"],
                }
            )
        return results

    async def get_active_batches(
        self, workspace_id: UUID, kind: str | None = None
    ) -> list[dict[str, Any]]:
        if self._client is None:
            raise RuntimeError(
                "BigQuery client not available. Live cloud credentials required."
            )

        from google.cloud import bigquery  # type: ignore

        query = f"""
        SELECT batch_id, kind, source_sha256, row_count, committed_at
        FROM {self._get_table_id('import_batches')}
        WHERE workspace_id = @workspace_id
        """
        query_params = [
            bigquery.ScalarQueryParameter("workspace_id", "STRING", str(workspace_id))
        ]
        if kind:
            query += " AND kind = @kind"
            query_params.append(bigquery.ScalarQueryParameter("kind", "STRING", kind))
        query += " ORDER BY committed_at DESC"

        job_config = bigquery.QueryJobConfig(query_parameters=query_params)
        query_job = self._client.query(query, job_config=job_config)

        results = []
        for row in query_job.result():
            results.append(
                {
                    "batch_id": row["batch_id"],
                    "kind": row["kind"],
                    "source_sha256": row["source_sha256"],
                    "row_count": int(row["row_count"]),
                    "committed_at": row["committed_at"],
                }
            )
        return results
