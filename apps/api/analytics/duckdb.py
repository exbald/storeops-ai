import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import duckdb

from apps.api.ports.analytics import AnalyticsRepository


class DuckDBAnalyticsRepository(AnalyticsRepository):
    def __init__(self, db_path: str = ":memory:") -> None:
        self._con = duckdb.connect(db_path)
        self._lock = asyncio.Lock()
        self._init_tables()

    def _init_tables(self) -> None:
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS import_batches (
                workspace_id VARCHAR NOT NULL,
                batch_id VARCHAR NOT NULL,
                kind VARCHAR NOT NULL,
                import_id VARCHAR NOT NULL,
                source_sha256 VARCHAR NOT NULL,
                row_count BIGINT NOT NULL,
                committed_at TIMESTAMP NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sales_facts (
                workspace_id VARCHAR NOT NULL,
                batch_id VARCHAR NOT NULL,
                store_id VARCHAR NOT NULL,
                sku VARCHAR NOT NULL,
                business_date DATE NOT NULL,
                units BIGINT NOT NULL,
                revenue DECIMAL(12, 2) NOT NULL,
                currency VARCHAR NOT NULL
            );

            CREATE TABLE IF NOT EXISTS inventory_facts (
                workspace_id VARCHAR NOT NULL,
                batch_id VARCHAR NOT NULL,
                location_id VARCHAR NOT NULL,
                sku VARCHAR NOT NULL,
                observed_at TIMESTAMP NOT NULL,
                quantity BIGINT NOT NULL,
                unit VARCHAR NOT NULL,
                normalized_units BIGINT NOT NULL
            );
            """
        )

    async def commit_import_batch(
        self,
        workspace_id: UUID,
        batch_id: str,
        kind: str,
        import_id: UUID,
        source_sha256: str,
        rows: list[dict[str, Any]],
    ) -> int:
        async with self._lock:
            # Check if batch was already committed for this workspace to prevent physical duplicate facts
            existing = self._con.execute(
                "SELECT COUNT(*) FROM import_batches WHERE workspace_id = ? AND batch_id = ?",
                [str(workspace_id), batch_id],
            ).fetchone()
            if existing and existing[0] > 0:
                return len(rows)

            now = datetime.now(UTC)
            self._con.execute(
                """
                INSERT INTO import_batches VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    str(workspace_id),
                    batch_id,
                    kind,
                    str(import_id),
                    source_sha256,
                    len(rows),
                    now,
                ],
            )

            if kind == "SALES":
                for row in rows:
                    self._con.execute(
                        """
                        INSERT INTO sales_facts VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            str(workspace_id),
                            batch_id,
                            str(row["store_id"]),
                            str(row["sku"]),
                            str(row["business_date"]),
                            int(row["units"]),
                            Decimal(str(row["revenue"])),
                            str(row["currency"]),
                        ],
                    )
            elif kind == "INVENTORY":
                for row in rows:
                    self._con.execute(
                        """
                        INSERT INTO inventory_facts VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            str(workspace_id),
                            batch_id,
                            str(row["location_id"]),
                            str(row["sku"]),
                            str(row["observed_at"]),
                            int(row["quantity"]),
                            str(row["unit"]),
                            int(row["normalized_units"]),
                        ],
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
        async with self._lock:
            # If batch_ids is provided but empty, return empty list
            if batch_ids is not None and len(batch_ids) == 0:
                return []

            # Latest committed revision wins per logical key (store_id, sku, business_date)
            batch_filter = ""
            params: list[Any] = [str(workspace_id), str(store_id), start_date, end_date]
            if batch_ids:
                placeholders = ", ".join(["?"] * len(batch_ids))
                batch_filter = f"AND s.batch_id IN ({placeholders})"
                params.extend(batch_ids)

            query = f"""
            WITH ranked AS (
                SELECT s.workspace_id, s.batch_id, s.store_id, s.sku, s.business_date,
                       s.units, s.revenue, s.currency, b.committed_at,
                       ROW_NUMBER() OVER(
                           PARTITION BY s.workspace_id, s.store_id, s.sku, s.business_date
                           ORDER BY b.committed_at DESC, s.batch_id DESC
                       ) as rn
                FROM sales_facts s
                JOIN import_batches b ON s.batch_id = b.batch_id
                WHERE s.workspace_id = ?
                  AND s.store_id = ?
                  AND s.business_date >= ?
                  AND s.business_date <= ?
                  {batch_filter}
            )
            SELECT store_id, sku, business_date, units, revenue, currency, batch_id
            FROM ranked
            WHERE rn = 1
            ORDER BY business_date ASC, sku ASC
            """
            cursor = self._con.execute(query, params)
            results = []
            for row in cursor.fetchall():
                results.append(
                    {
                        "store_id": UUID(row[0]),
                        "sku": row[1],
                        "business_date": str(row[2]),
                        "units": int(row[3]),
                        "revenue": Decimal(str(row[4])),
                        "currency": row[5],
                        "batch_id": row[6],
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
        async with self._lock:
            if not location_ids:
                return []
            if batch_ids is not None and len(batch_ids) == 0:
                return []

            loc_placeholders = ", ".join(["?"] * len(location_ids))
            batch_filter = ""
            params: list[Any] = [str(workspace_id), as_of_time]
            params.extend([str(lid) for lid in location_ids])

            if batch_ids:
                b_placeholders = ", ".join(["?"] * len(batch_ids))
                batch_filter = f"AND i.batch_id IN ({b_placeholders})"
                params.extend(batch_ids)

            query = f"""
            WITH ranked AS (
                SELECT i.location_id, i.sku, i.observed_at, i.quantity, i.unit,
                       i.normalized_units, i.batch_id, b.committed_at,
                       ROW_NUMBER() OVER(
                           PARTITION BY i.workspace_id, i.location_id, i.sku
                           ORDER BY i.observed_at DESC, b.committed_at DESC, i.batch_id DESC
                       ) as rn
                FROM inventory_facts i
                JOIN import_batches b ON i.batch_id = b.batch_id
                WHERE i.workspace_id = ?
                  AND i.observed_at <= ?
                  AND i.location_id IN ({loc_placeholders})
                  {batch_filter}
            )
            SELECT location_id, sku, observed_at, quantity, unit, normalized_units, batch_id
            FROM ranked
            WHERE rn = 1
            ORDER BY location_id ASC, sku ASC
            """
            cursor = self._con.execute(query, params)
            results = []
            for row in cursor.fetchall():
                results.append(
                    {
                        "location_id": UUID(row[0]),
                        "sku": row[1],
                        "observed_at": str(row[2]),
                        "quantity": int(row[3]),
                        "unit": row[4],
                        "normalized_units": int(row[5]),
                        "batch_id": row[6],
                    }
                )
            return results

    async def get_active_batches(
        self, workspace_id: UUID, kind: str | None = None
    ) -> list[dict[str, Any]]:
        async with self._lock:
            query = "SELECT batch_id, kind, source_sha256, row_count, committed_at FROM import_batches WHERE workspace_id = ?"
            params: list[Any] = [str(workspace_id)]
            if kind:
                query += " AND kind = ?"
                params.append(kind)
            query += " ORDER BY committed_at DESC"
            cursor = self._con.execute(query, params)
            results = []
            for row in cursor.fetchall():
                results.append(
                    {
                        "batch_id": row[0],
                        "kind": row[1],
                        "source_sha256": row[2],
                        "row_count": int(row[3]),
                        "committed_at": row[4],
                    }
                )
            return results
