"""BigQuery commit_import_batch: insert errors surface, manifest is the last write."""

from decimal import Decimal
from uuid import uuid4

import pytest

from apps.api.analytics.bigquery import BigQueryAnalyticsRepository


def _repo(client) -> BigQueryAnalyticsRepository:
    return BigQueryAnalyticsRepository(
        project_id="storeops-ai", dataset_id="storeops_dev", client=client
    )


def _sales_rows():
    return [
        {
            "store_id": uuid4(),
            "sku": "SKU-1",
            "business_date": "2026-09-10",
            "units": 3,
            "revenue": Decimal("7.50"),
            "currency": "USD",
        }
    ]


def _inventory_rows():
    return [
        {
            "location_id": uuid4(),
            "sku": "SKU-1",
            "observed_at": "2026-09-10T08:00:00+00:00",
            "quantity": 2,
            "unit": "CASE",
            "normalized_units": 24,
        }
    ]


def test_injected_client_is_used(fake_bigquery_client):
    assert _repo(fake_bigquery_client)._client is fake_bigquery_client


async def test_sales_facts_written_before_manifest(fake_bigquery_client):
    repo = _repo(fake_bigquery_client)
    count = await repo.commit_import_batch(uuid4(), "b1", "SALES", uuid4(), "f" * 64, _sales_rows())

    assert count == 1
    tables = [t for t, _ in fake_bigquery_client.inserts]
    assert tables == ["storeops-ai.storeops_dev.sales_facts", "storeops-ai.storeops_dev.import_batches"]
    fact = fake_bigquery_client.inserts[0][1][0]
    assert fact["revenue"] == "7.50"
    manifest = fake_bigquery_client.inserts[1][1][0]
    assert manifest["kind"] == "SALES" and manifest["row_count"] == 1


async def test_inventory_facts_written_before_manifest(fake_bigquery_client):
    repo = _repo(fake_bigquery_client)
    await repo.commit_import_batch(uuid4(), "b2", "INVENTORY", uuid4(), "f" * 64, _inventory_rows())
    tables = [t.rsplit(".", 1)[-1] for t, _ in fake_bigquery_client.inserts]
    assert tables == ["inventory_facts", "import_batches"]


async def test_fact_insert_errors_raise_and_skip_manifest(fake_bigquery_client):
    fake_bigquery_client.insert_errors["sales_facts"] = [{"index": 0, "errors": [{"reason": "invalid"}]}]
    repo = _repo(fake_bigquery_client)

    with pytest.raises(RuntimeError, match="sales_facts"):
        await repo.commit_import_batch(uuid4(), "b3", "SALES", uuid4(), "f" * 64, _sales_rows())

    tables = [t.rsplit(".", 1)[-1] for t, _ in fake_bigquery_client.inserts]
    assert "import_batches" not in tables


async def test_manifest_insert_errors_raise(fake_bigquery_client):
    fake_bigquery_client.insert_errors["import_batches"] = [{"index": 0, "errors": [{"reason": "x"}]}]
    with pytest.raises(RuntimeError, match="import_batches"):
        await _repo(fake_bigquery_client).commit_import_batch(
            uuid4(), "b4", "SALES", uuid4(), "f" * 64, _sales_rows()
        )


async def test_empty_batch_writes_manifest_only(fake_bigquery_client):
    await _repo(fake_bigquery_client).commit_import_batch(uuid4(), "b5", "SALES", uuid4(), "f" * 64, [])
    tables = [t.rsplit(".", 1)[-1] for t, _ in fake_bigquery_client.inserts]
    assert tables == ["import_batches"]


async def test_already_committed_batch_is_idempotent(fake_bigquery_client):
    fake_bigquery_client.existing_batches = 1
    count = await _repo(fake_bigquery_client).commit_import_batch(
        uuid4(), "b6", "SALES", uuid4(), "f" * 64, _sales_rows()
    )
    assert count == 1
    assert fake_bigquery_client.inserts == []
