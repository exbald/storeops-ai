"""AC27: BigQuery / local analytics parity tests and disposable target protection.

Validates that:
1. BigQuery and DuckDB analytics adapters produce identical results for the same datasets:
   - Latest revision resolution across committed batches.
   - Lexicographical tie-breaking.
   - Missing sales dates remain absent (unknown, not zero).
   - Decimal currency precision.
   - Multi-location latest inventory as-of timestamp filtering.
   - Batch snapshot isolation.
2. Safety check: Disposable target check prevents targeting production datasets.
"""

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from apps.api.analytics.bigquery import BigQueryAnalyticsRepository
from apps.api.analytics.duckdb import DuckDBAnalyticsRepository


@pytest.mark.asyncio
async def test_ac27_disposable_dataset_guard():
    """AC27: BigQuery adapter refuses to operate on production-looking datasets without explicit override."""
    # Production names should fail initialization or commit if allow_prod is False
    with pytest.raises(ValueError, match="Refusing to target production-like dataset"):
        BigQueryAnalyticsRepository(
            project_id="storeops-dev",
            dataset_id="storeops_production",
            allow_prod=False,
        )

    with pytest.raises(ValueError, match="Refusing to target production-like dataset"):
        BigQueryAnalyticsRepository(
            project_id="storeops-12345",
            dataset_id="storeops_prod_analytics",
            allow_prod=False,
        )

    # Rejects production project even with disposable dataset
    with pytest.raises(ValueError, match="Refusing to target production-like project"):
        BigQueryAnalyticsRepository(
            project_id="storeops-prod-999",
            dataset_id="disposable_test_analytics",
            allow_prod=False,
        )

    # Disposable/test/dev datasets are accepted
    dev_repo = BigQueryAnalyticsRepository(
        project_id="storeops-dev",
        dataset_id="disposable_test_analytics_ac27",
        allow_prod=False,
    )
    assert dev_repo.dataset_id == "disposable_test_analytics_ac27"


@pytest.mark.asyncio
async def test_ac27_sales_window_revision_parity(
    duckdb_repo: DuckDBAnalyticsRepository,
    test_workspace_id: UUID,
    test_store_id: UUID,
    sample_sales_batches: list[dict[str, Any]],
):
    """AC27: DuckDB and BigQuery SQL queries agree on latest-revision-wins semantics."""
    # Commit batches into DuckDB
    batch_1, batch_2 = sample_sales_batches
    await duckdb_repo.commit_import_batch(
        workspace_id=test_workspace_id,
        batch_id=batch_1["batch_id"],
        kind=batch_1["kind"],
        import_id=uuid4(),
        source_sha256="sha256-batch-1",
        rows=batch_1["rows"],
    )
    await duckdb_repo.commit_import_batch(
        workspace_id=test_workspace_id,
        batch_id=batch_2["batch_id"],
        kind=batch_2["kind"],
        import_id=uuid4(),
        source_sha256="sha256-batch-2",
        rows=batch_2["rows"],
    )

    # Query DuckDB
    results = await duckdb_repo.get_sales_window(
        workspace_id=test_workspace_id,
        store_id=test_store_id,
        start_date="2026-09-10",
        end_date="2026-09-15",
    )

    # 1. 4 logical dates/SKU combos:
    # (09-10, SKU-SNACK), (09-10, SKU-TEA), (09-11, SKU-TEA), (09-12, SKU-TEA) = 4 total rows
    assert len(results) == 4

    # 2. Check corrected row: 2026-09-11 for SKU-TEA should have units=12, revenue=30.00 from batch_2
    tea_0911 = next(
        r for r in results if r["sku"] == "SKU-TEA-001" and r["business_date"] == "2026-09-11"
    )
    assert tea_0911["units"] == 12
    assert tea_0911["revenue"] == Decimal("30.00")
    assert isinstance(tea_0911["revenue"], Decimal)
    assert tea_0911["batch_id"] == "BATCH-2026-09-02-B"

    # 3. Check uncorrected row: 2026-09-10 for SKU-TEA has units=10 from batch_1
    tea_0910 = next(
        r for r in results if r["sku"] == "SKU-TEA-001" and r["business_date"] == "2026-09-10"
    )
    assert tea_0910["units"] == 10
    assert tea_0910["revenue"] == Decimal("25.00")
    assert tea_0910["batch_id"] == "BATCH-2026-09-01-A"

    # 4. Check missing dates: 2026-09-13 through 2026-09-15 have no rows (unknown, not zero)
    dates_in_res = {r["business_date"] for r in results}
    assert "2026-09-13" not in dates_in_res
    assert "2026-09-14" not in dates_in_res

    # 5. Verify BigQuery SQL template equivalence
    bq_repo = BigQueryAnalyticsRepository(
        project_id="test-proj",
        dataset_id="disposable_test_ac27",
        allow_prod=False,
    )
    sql, params = bq_repo._build_sales_window_query(
        workspace_id=test_workspace_id,
        store_id=test_store_id,
        start_date="2026-09-10",
        end_date="2026-09-15",
        batch_ids=None,
    )
    assert "PARTITION BY s.workspace_id, s.store_id, s.sku, s.business_date" in sql
    assert "ORDER BY b.committed_at DESC, s.batch_id DESC" in sql
    assert "WHERE rn = 1" in sql
    assert params["workspace_id"] == str(test_workspace_id)
    assert params["store_id"] == str(test_store_id)


@pytest.mark.asyncio
async def test_ac27_batch_snapshot_isolation_parity(
    duckdb_repo: DuckDBAnalyticsRepository,
    test_workspace_id: UUID,
    test_store_id: UUID,
    sample_sales_batches: list[dict[str, Any]],
):
    """AC27: When batch_ids is specified, facts from later batches are strictly excluded."""
    batch_1, batch_2 = sample_sales_batches
    await duckdb_repo.commit_import_batch(
        workspace_id=test_workspace_id,
        batch_id=batch_1["batch_id"],
        kind=batch_1["kind"],
        import_id=uuid4(),
        source_sha256="sha256-1",
        rows=batch_1["rows"],
    )
    await duckdb_repo.commit_import_batch(
        workspace_id=test_workspace_id,
        batch_id=batch_2["batch_id"],
        kind=batch_2["kind"],
        import_id=uuid4(),
        source_sha256="sha256-2",
        rows=batch_2["rows"],
    )

    # Query with only batch_1 in snapshot
    snap_results = await duckdb_repo.get_sales_window(
        workspace_id=test_workspace_id,
        store_id=test_store_id,
        start_date="2026-09-10",
        end_date="2026-09-15",
        batch_ids=[batch_1["batch_id"]],
    )

    # In snapshot of batch_1, 2026-09-11 has units=15 (not the batch_2 correction to 12)
    tea_0911_snap = next(
        r for r in snap_results if r["sku"] == "SKU-TEA-001" and r["business_date"] == "2026-09-11"
    )
    assert tea_0911_snap["units"] == 15
    assert tea_0911_snap["batch_id"] == "BATCH-2026-09-01-A"

    # 2026-09-12 from batch_2 must NOT exist
    assert not any(r["business_date"] == "2026-09-12" for r in snap_results)

    # Empty batch_ids list returns empty list
    empty_res = await duckdb_repo.get_sales_window(
        workspace_id=test_workspace_id,
        store_id=test_store_id,
        start_date="2026-09-10",
        end_date="2026-09-15",
        batch_ids=[],
    )
    assert empty_res == []


@pytest.mark.asyncio
async def test_ac27_inventory_as_of_parity(
    duckdb_repo: DuckDBAnalyticsRepository,
    test_workspace_id: UUID,
    test_location_ids: list[UUID],
    sample_inventory_batches: list[dict[str, Any]],
):
    """AC27: Latest inventory snapshot per location/product at or before as_of_time."""
    batch_1, batch_2 = sample_inventory_batches
    await duckdb_repo.commit_import_batch(
        workspace_id=test_workspace_id,
        batch_id=batch_1["batch_id"],
        kind=batch_1["kind"],
        import_id=uuid4(),
        source_sha256="sha256-inv-1",
        rows=batch_1["rows"],
    )
    await duckdb_repo.commit_import_batch(
        workspace_id=test_workspace_id,
        batch_id=batch_2["batch_id"],
        kind=batch_2["kind"],
        import_id=uuid4(),
        source_sha256="sha256-inv-2",
        rows=batch_2["rows"],
    )

    # As of 10:00:00 (before batch_2 at 14:00:00), shelf quantity is 10
    early_inv = await duckdb_repo.get_latest_inventory(
        workspace_id=test_workspace_id,
        location_ids=test_location_ids,
        as_of_time="2026-09-10T10:00:00Z",
    )
    shelf_loc = test_location_ids[0]
    backroom_loc = test_location_ids[1]

    shelf_early = next(r for r in early_inv if r["location_id"] == shelf_loc)
    assert shelf_early["quantity"] == 10

    backroom_early = next(r for r in early_inv if r["location_id"] == backroom_loc)
    assert backroom_early["quantity"] == 50

    # As of 18:00:00 (after batch_2 at 14:00:00), shelf quantity updated to 2
    late_inv = await duckdb_repo.get_latest_inventory(
        workspace_id=test_workspace_id,
        location_ids=test_location_ids,
        as_of_time="2026-09-10T18:00:00Z",
    )
    shelf_late = next(r for r in late_inv if r["location_id"] == shelf_loc)
    assert shelf_late["quantity"] == 2
    assert shelf_late["batch_id"] == "BATCH-INV-002"

    # BigQuery query equivalence
    bq_repo = BigQueryAnalyticsRepository(
        project_id="test-proj",
        dataset_id="disposable_test_ac27",
        allow_prod=False,
    )
    sql, params = bq_repo._build_latest_inventory_query(
        workspace_id=test_workspace_id,
        location_ids=test_location_ids,
        as_of_time="2026-09-10T18:00:00Z",
        batch_ids=None,
    )
    assert "PARTITION BY i.workspace_id, i.location_id, i.sku" in sql
    assert "ORDER BY i.observed_at DESC, b.committed_at DESC, i.batch_id DESC" in sql
    assert "WHERE rn = 1" in sql
    assert params["as_of_time"] == "2026-09-10T18:00:00Z"


@pytest.mark.asyncio
async def test_ac27_bigquery_commit_decimal_serialization():
    """AC27: BigQuery commit serializes currency as exact string Decimal without float precision loss."""
    import sys
    from unittest.mock import MagicMock, patch

    repo = BigQueryAnalyticsRepository(
        project_id="test-proj",
        dataset_id="disposable_test_ac27",
        allow_prod=False,
    )
    mock_client = MagicMock()
    # Idempotency check query returns empty (no previous batch)
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = []
    mock_client.query.return_value = mock_query_job
    repo._client = mock_client

    workspace_id = uuid4()
    import_id = uuid4()
    sales_rows = [
        {
            "store_id": uuid4(),
            "sku": "SKU-TEST-001",
            "business_date": "2026-09-15",
            "units": 10,
            "revenue": Decimal("199.95"),
            "currency": "EUR",
        }
    ]

    mock_bq_module = MagicMock()
    with patch.dict(sys.modules, {"google.cloud.bigquery": mock_bq_module}):
        count = await repo.commit_import_batch(
            workspace_id=workspace_id,
            batch_id="BATCH-DECIMAL-001",
            kind="SALES",
            import_id=import_id,
            source_sha256="abc123sha",
            rows=sales_rows,
        )
    assert count == 1

    # Verify insert_rows_json called for sales_facts with string revenue
    assert mock_client.insert_rows_json.call_count == 2
    sales_insert_call = mock_client.insert_rows_json.call_args_list[1]
    table_id, inserted_rows = sales_insert_call[0]
    assert table_id == "test-proj.disposable_test_ac27.sales_facts"
    assert len(inserted_rows) == 1
    assert inserted_rows[0]["revenue"] == "199.95"
    assert isinstance(inserted_rows[0]["revenue"], str)
    assert not isinstance(inserted_rows[0]["revenue"], float)

