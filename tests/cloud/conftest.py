"""Pytest fixtures for cloud parity, evaluation, and deployment tests (T12)."""

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from apps.api.analytics.duckdb import DuckDBAnalyticsRepository


@pytest.fixture
def test_workspace_id() -> UUID:
    return uuid4()


@pytest.fixture
def test_store_id() -> UUID:
    return uuid4()


@pytest.fixture
def test_location_ids() -> list[UUID]:
    return [uuid4(), uuid4()]


@pytest.fixture
def duckdb_repo() -> DuckDBAnalyticsRepository:
    return DuckDBAnalyticsRepository(db_path=":memory:")


@pytest.fixture
def sample_sales_batches(test_store_id: UUID) -> list[dict[str, Any]]:
    """Two batches of sales data: batch_1 with initial values, batch_2 correcting some rows."""
    sku_1 = "SKU-TEA-001"
    sku_2 = "SKU-SNACK-002"

    batch_1 = {
        "batch_id": "BATCH-2026-09-01-A",
        "kind": "SALES",
        "rows": [
            {
                "store_id": test_store_id,
                "sku": sku_1,
                "business_date": "2026-09-10",
                "units": 10,
                "revenue": Decimal("25.00"),
                "currency": "USD",
            },
            {
                "store_id": test_store_id,
                "sku": sku_1,
                "business_date": "2026-09-11",
                "units": 15,
                "revenue": Decimal("37.50"),
                "currency": "USD",
            },
            {
                "store_id": test_store_id,
                "sku": sku_2,
                "business_date": "2026-09-10",
                "units": 5,
                "revenue": Decimal("10.00"),
                "currency": "USD",
            },
        ],
    }

    # batch_2 corrects 2026-09-11 for sku_1 with lower units, and adds 2026-09-12
    batch_2 = {
        "batch_id": "BATCH-2026-09-02-B",
        "kind": "SALES",
        "rows": [
            {
                "store_id": test_store_id,
                "sku": sku_1,
                "business_date": "2026-09-11",
                "units": 12,  # corrected from 15
                "revenue": Decimal("30.00"),  # corrected from 37.50
                "currency": "USD",
            },
            {
                "store_id": test_store_id,
                "sku": sku_1,
                "business_date": "2026-09-12",
                "units": 8,
                "revenue": Decimal("20.00"),
                "currency": "USD",
            },
        ],
    }

    return [batch_1, batch_2]


@pytest.fixture
def sample_inventory_batches(test_location_ids: list[UUID]) -> list[dict[str, Any]]:
    """Two batches of inventory data across store and backroom locations."""
    loc_shelf = test_location_ids[0]
    loc_backroom = test_location_ids[1]
    sku_1 = "SKU-TEA-001"

    batch_1 = {
        "batch_id": "BATCH-INV-001",
        "kind": "INVENTORY",
        "rows": [
            {
                "location_id": loc_shelf,
                "sku": sku_1,
                "observed_at": "2026-09-10T08:00:00Z",
                "quantity": 10,
                "unit": "EACH",
                "normalized_units": 10,
            },
            {
                "location_id": loc_backroom,
                "sku": sku_1,
                "observed_at": "2026-09-10T08:00:00Z",
                "quantity": 50,
                "unit": "CASE",
                "normalized_units": 50,
            },
        ],
    }

    # batch_2 observes shelf later in the day with depleted count
    batch_2 = {
        "batch_id": "BATCH-INV-002",
        "kind": "INVENTORY",
        "rows": [
            {
                "location_id": loc_shelf,
                "sku": sku_1,
                "observed_at": "2026-09-10T14:00:00Z",
                "quantity": 2,
                "unit": "EACH",
                "normalized_units": 2,
            },
        ],
    }

    return [batch_1, batch_2]
