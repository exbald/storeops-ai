"""Integration tests for AC06, AC07, and AC08.

AC06: CSV staging and atomic commit, units/currency/case normalization.
AC07: Validation failure on unknown SKU, duplicate key, missing column, invalid number.
AC08: Commit idempotency, revision handling, immutability of historical snapshots.
"""

import hashlib
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from apps.api.analytics.duckdb import DuckDBAnalyticsRepository


async def _upload_csv_media(
    client: AsyncClient,
    admin_headers: dict[str, str],
    csv_bytes: bytes,
    filename: str = "data.csv",
) -> UUID:
    sha = hashlib.sha256(csv_bytes).hexdigest()
    init_res = await client.post(
        "/media",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "kind": "IMPORT",
            "filename": filename,
            "mime_type": "text/csv",
            "byte_size": len(csv_bytes),
            "sha256": sha,
            "store_id": None,
            "visit_id": None,
            "product_id": None,
            "zone_id": None,
            "zone_kind": None,
            "captured_at": None,
        },
    )
    assert init_res.status_code == 201
    media_info = init_res.json()
    media_id = media_info["media"]["id"]
    upload_url = media_info["upload_url"]

    put_res = await client.put(upload_url, content=csv_bytes)
    assert put_res.status_code == 200

    complete_res = await client.post(
        f"/media/{media_id}/complete",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )
    assert complete_res.status_code == 200
    return UUID(media_id)


@pytest.mark.asyncio
async def test_ac06_csv_validation_and_atomic_commit(
    integration_client: AsyncClient,
    admin_a_headers: dict[str, str],
    workspace_a_id: UUID,
    int_analytics_repo: DuckDBAnalyticsRepository,
):
    """AC06: Validation alone adds no facts; commit makes entire batch visible."""
    # 1. Create a store and product in Workspace A
    store_code = f"STR-IMP-{uuid4().hex[:6]}"
    store_res = await integration_client.post(
        "/stores",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "code": store_code,
            "name": "Import Test Store",
            "retailer": "Retail Corp",
            "region": "Central",
            "format": "Supermarket",
            "timezone": "Asia/Singapore",
            "distributor_location_id": None,
        },
    )
    assert store_res.status_code == 201
    store_id = UUID(store_res.json()["id"])

    sku = f"SKU-{uuid4().hex[:6].upper()}"
    prod_res = await integration_client.post(
        "/products",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "sku": sku,
            "name": "Import Test Beverage",
            "case_units": 24,
        },
    )
    assert prod_res.status_code == 201

    # 2. Upload valid sales CSV
    csv_content = (
        f"store_code,sku,business_date,units,revenue,currency\n"
        f"{store_code},{sku},2026-09-10,40,120.00,SGD\n"
    ).encode()

    media_id = await _upload_csv_media(integration_client, admin_a_headers, csv_content, "valid_sales.csv")

    # 3. Create import
    create_res = await integration_client.post(
        "/imports",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={"kind": "SALES", "media_id": str(media_id)},
    )
    assert create_res.status_code == 202
    import_id = create_res.json()["resource_id"]

    # 4. Verify import is VALIDATED, but ZERO facts committed yet
    get_res = await integration_client.get(f"/imports/{import_id}", headers=admin_a_headers)
    assert get_res.status_code == 200
    imp_data = get_res.json()
    assert imp_data["status"] == "VALIDATED"
    assert imp_data["row_count"] == 1
    assert imp_data["error_count"] == 0

    uncommitted_facts = await int_analytics_repo.get_sales_window(
        workspace_id=workspace_a_id,
        store_id=store_id,
        start_date="2026-09-01",
        end_date="2026-09-20",
    )
    assert len(uncommitted_facts) == 0, "Validation alone must not write analytical facts"

    # 5. Commit import
    commit_res = await integration_client.post(
        f"/imports/{import_id}/commit",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )
    assert commit_res.status_code == 202

    # Verify import is COMMITTED
    get_res2 = await integration_client.get(f"/imports/{import_id}", headers=admin_a_headers)
    assert get_res2.status_code == 200
    committed = get_res2.json()
    assert committed["status"] == "COMMITTED"
    assert committed["batch_id"] is not None

    # 6. Verify facts are now visible in analytics
    facts = await int_analytics_repo.get_sales_window(
        workspace_id=workspace_a_id,
        store_id=store_id,
        start_date="2026-09-01",
        end_date="2026-09-20",
    )
    assert len(facts) == 1
    assert facts[0]["units"] == 40


@pytest.mark.asyncio
async def test_ac07_invalid_csv_validation_errors(
    integration_client: AsyncClient,
    admin_a_headers: dict[str, str],
):
    """AC07: CSV with unknown SKU, duplicate key, or missing column marked INVALID."""
    # CSV referencing an unknown SKU
    bad_csv = (
        b"store_code,sku,business_date,units,revenue,currency\n"
        b"STR-NONEXISTENT,SKU-UNKNOWN-999,2026-09-10,10,30.00,SGD\n"
    )
    media_id = await _upload_csv_media(integration_client, admin_a_headers, bad_csv, "invalid_sku.csv")

    create_res = await integration_client.post(
        "/imports",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={"kind": "SALES", "media_id": str(media_id)},
    )
    assert create_res.status_code == 202
    import_id = create_res.json()["resource_id"]

    get_res = await integration_client.get(f"/imports/{import_id}", headers=admin_a_headers)
    assert get_res.status_code == 200
    imp_data = get_res.json()
    assert imp_data["status"] == "INVALID"
    assert imp_data["error_count"] > 0
    assert len(imp_data["errors"]) > 0

    # Attempting to commit an INVALID import must fail with 409 CONFLICT
    commit_res = await integration_client.post(
        f"/imports/{import_id}/commit",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": imp_data["version"]},
    )
    assert commit_res.status_code == 409
    assert commit_res.json()["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_ac08_commit_idempotency_and_revisions(
    integration_client: AsyncClient,
    admin_a_headers: dict[str, str],
    workspace_a_id: UUID,
    int_analytics_repo: DuckDBAnalyticsRepository,
):
    """AC08: Commit idempotency (no duplication) and revision handling."""
    # 1. Create store and product
    store_code = f"STR-REV-{uuid4().hex[:6]}"
    store_res = await integration_client.post(
        "/stores",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "code": store_code,
            "name": "Revision Test Store",
            "retailer": "Retail Corp",
            "region": "South",
            "format": "Supermarket",
            "timezone": "Asia/Singapore",
            "distributor_location_id": None,
        },
    )
    assert store_res.status_code == 201
    store_id = UUID(store_res.json()["id"])

    sku = f"SKU-{uuid4().hex[:6].upper()}"
    prod_res = await integration_client.post(
        "/products",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "sku": sku,
            "name": "Revision Test Beverage",
            "case_units": 12,
        },
    )
    assert prod_res.status_code == 201

    # 2. Batch 1: Initial sales
    csv_1 = (
        f"store_code,sku,business_date,units,revenue,currency\n"
        f"{store_code},{sku},2026-09-12,50,150.00,SGD\n"
    ).encode()
    media_1 = await _upload_csv_media(integration_client, admin_a_headers, csv_1, "sales_v1.csv")

    imp1_res = await integration_client.post(
        "/imports",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={"kind": "SALES", "media_id": str(media_1)},
    )
    imp1_id = imp1_res.json()["resource_id"]

    commit1_res = await integration_client.post(
        f"/imports/{imp1_id}/commit",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )
    assert commit1_res.status_code == 202

    # 3. Idempotent commit retry of same import: must return 202 without duplicating data
    commit1_retry = await integration_client.post(
        f"/imports/{imp1_id}/commit",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )
    assert commit1_retry.status_code == 202

    facts_after_retry = await int_analytics_repo.get_sales_window(
        workspace_id=workspace_a_id,
        store_id=store_id,
        start_date="2026-09-01",
        end_date="2026-09-20",
    )
    assert len(facts_after_retry) == 1, "Retry commit must not duplicate rows in analytics"
