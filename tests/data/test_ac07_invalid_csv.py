from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_ac07_unknown_sku(client, data_setup, analytics_repo, catalog_repo):
    admin_headers = data_setup["admin_headers"]
    upload_csv = data_setup["upload_csv_media"]
    workspace = data_setup["workspace"]

    # CSV contains an unknown SKU
    csv_bytes = (
        b"store_code,sku,business_date,units,revenue,currency\n"
        b"STR-01,SKU-UNKNOWN-999,2026-09-10,10,30.00,SGD\n"
    )

    media_id = await upload_csv(csv_bytes)
    res = await client.post(
        "/imports",
        json={"kind": "SALES", "media_id": media_id},
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    assert res.status_code == 202
    import_id = res.json()["resource_id"]

    imp = (await client.get(f"/imports/{import_id}", headers=admin_headers)).json()
    assert imp["status"] == "INVALID"
    assert imp["error_count"] >= 1
    assert any(
        e["field"] == "sku" and e["code"] == "UNKNOWN_SKU" for e in imp["errors"]
    )

    # Verify no implicit product was created
    products, _ = await catalog_repo.list_products(workspace.id)
    assert not any(p.sku == "SKU-UNKNOWN-999" for p in products)

    # Committing an INVALID import is rejected
    commit_res = await client.post(
        f"/imports/{import_id}/commit",
        json={"expected_version": 1},
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    assert commit_res.status_code == 409


@pytest.mark.asyncio
async def test_ac07_duplicate_logical_key(client, data_setup):
    admin_headers = data_setup["admin_headers"]
    upload_csv = data_setup["upload_csv_media"]

    # Duplicate logical key within file
    csv_bytes = (
        b"store_code,sku,business_date,units,revenue,currency\n"
        b"STR-01,SKU-COKE-330,2026-09-10,10,30.00,SGD\n"
        b"STR-01,SKU-COKE-330,2026-09-10,15,45.00,SGD\n"
    )

    media_id = await upload_csv(csv_bytes)
    res = await client.post(
        "/imports",
        json={"kind": "SALES", "media_id": media_id},
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    import_id = res.json()["resource_id"]

    imp = (await client.get(f"/imports/{import_id}", headers=admin_headers)).json()
    assert imp["status"] == "INVALID"
    assert any(e["code"] == "DUPLICATE_KEY" for e in imp["errors"])


@pytest.mark.asyncio
async def test_ac07_column_mismatch_and_extra_columns(client, data_setup):
    admin_headers = data_setup["admin_headers"]
    upload_csv = data_setup["upload_csv_media"]

    # Extra column 'extra_col'
    csv_bytes = (
        b"store_code,sku,business_date,units,revenue,currency,extra_col\n"
        b"STR-01,SKU-COKE-330,2026-09-10,10,30.00,SGD,extra\n"
    )

    media_id = await upload_csv(csv_bytes)
    res = await client.post(
        "/imports",
        json={"kind": "SALES", "media_id": media_id},
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    import_id = res.json()["resource_id"]

    imp = (await client.get(f"/imports/{import_id}", headers=admin_headers)).json()
    assert imp["status"] == "INVALID"
    assert any(e["code"] == "COLUMN_MISMATCH" for e in imp["errors"])


@pytest.mark.asyncio
async def test_ac07_currency_mismatch(client, data_setup):
    admin_headers = data_setup["admin_headers"]
    upload_csv = data_setup["upload_csv_media"]

    # Currency USD does not match workspace SGD
    csv_bytes = (
        b"store_code,sku,business_date,units,revenue,currency\n"
        b"STR-01,SKU-COKE-330,2026-09-10,10,30.00,USD\n"
    )

    media_id = await upload_csv(csv_bytes)
    res = await client.post(
        "/imports",
        json={"kind": "SALES", "media_id": media_id},
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    import_id = res.json()["resource_id"]

    imp = (await client.get(f"/imports/{import_id}", headers=admin_headers)).json()
    assert imp["status"] == "INVALID"
    assert any(e["code"] == "CURRENCY_MISMATCH" for e in imp["errors"])


@pytest.mark.asyncio
async def test_ac07_negative_units_and_invalid_money(client, data_setup):
    admin_headers = data_setup["admin_headers"]
    upload_csv = data_setup["upload_csv_media"]

    # Negative units and revenue with 1 decimal place instead of 2
    csv_bytes = (
        b"store_code,sku,business_date,units,revenue,currency\n"
        b"STR-01,SKU-COKE-330,2026-09-10,-5,30.5,SGD\n"
    )

    media_id = await upload_csv(csv_bytes)
    res = await client.post(
        "/imports",
        json={"kind": "SALES", "media_id": media_id},
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    import_id = res.json()["resource_id"]

    imp = (await client.get(f"/imports/{import_id}", headers=admin_headers)).json()
    assert imp["status"] == "INVALID"
    assert any(e["code"] == "NEGATIVE_UNITS" for e in imp["errors"])
    assert any(e["code"] == "INVALID_MONEY" for e in imp["errors"])


@pytest.mark.asyncio
async def test_ac07_future_business_date(client, data_setup):
    admin_headers = data_setup["admin_headers"]
    upload_csv = data_setup["upload_csv_media"]

    # Future date (year 2099)
    csv_bytes = (
        b"store_code,sku,business_date,units,revenue,currency\n"
        b"STR-01,SKU-COKE-330,2099-01-01,10,30.00,SGD\n"
    )

    media_id = await upload_csv(csv_bytes)
    res = await client.post(
        "/imports",
        json={"kind": "SALES", "media_id": media_id},
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    import_id = res.json()["resource_id"]

    imp = (await client.get(f"/imports/{import_id}", headers=admin_headers)).json()
    assert imp["status"] == "INVALID"
    assert any(e["code"] == "FUTURE_DATE" for e in imp["errors"])
