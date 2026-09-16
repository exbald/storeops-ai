from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_ac06_sales_staging_and_commit(client, data_setup, analytics_repo):
    admin_headers = data_setup["admin_headers"]
    rep_headers = data_setup["rep_headers"]
    upload_csv = data_setup["upload_csv_media"]
    store_1 = data_setup["store_1"]
    workspace = data_setup["workspace"]

    # 1. Prepare valid sales CSV
    sales_csv = (
        b"store_code,sku,business_date,units,revenue,currency\n"
        b"STR-01,SKU-COKE-330,2026-09-10,25,75.00,SGD\n"
        b"STR-01,SKU-SPRITE-330,2026-09-10,10,30.00,SGD\n"
    )

    media_id = await upload_csv(sales_csv)

    # REP cannot create import (ADMIN required)
    forbidden_res = await client.post(
        "/imports",
        json={"kind": "SALES", "media_id": media_id},
        headers={**rep_headers, "Idempotency-Key": str(uuid4())},
    )
    assert forbidden_res.status_code == 403

    # 2. Create import as ADMIN
    create_res = await client.post(
        "/imports",
        json={"kind": "SALES", "media_id": media_id},
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    assert create_res.status_code == 202
    job_data = create_res.json()
    import_id = job_data["resource_id"]

    # 3. Inspect import status
    get_res = await client.get(f"/imports/{import_id}", headers=admin_headers)
    assert get_res.status_code == 200
    imp_data = get_res.json()
    assert imp_data["status"] == "VALIDATED"
    assert imp_data["row_count"] == 2
    assert imp_data["error_count"] == 0
    assert imp_data["errors"] == []
    assert imp_data["batch_id"] is None
    assert imp_data["committed_at"] is None

    # 4. Verify that validation alone added NO analytical facts
    uncommitted_facts = await analytics_repo.get_sales_window(
        workspace_id=workspace.id,
        store_id=store_1.id,
        start_date="2026-09-01",
        end_date="2026-09-20",
    )
    assert len(uncommitted_facts) == 0

    # 5. Explicitly commit import
    commit_res = await client.post(
        f"/imports/{import_id}/commit",
        json={"expected_version": 1},
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    assert commit_res.status_code == 202

    # 6. Verify import is now COMMITTED with batch_id and committed_at
    get_res2 = await client.get(f"/imports/{import_id}", headers=admin_headers)
    assert get_res2.status_code == 200
    imp_data2 = get_res2.json()
    assert imp_data2["status"] == "COMMITTED"
    assert imp_data2["batch_id"] is not None
    assert imp_data2["committed_at"] is not None
    assert imp_data2["version"] == 2

    # 7. Verify analytical facts are now visible
    committed_facts = await analytics_repo.get_sales_window(
        workspace_id=workspace.id,
        store_id=store_1.id,
        start_date="2026-09-01",
        end_date="2026-09-20",
    )
    assert len(committed_facts) == 2
    skus = {f["sku"] for f in committed_facts}
    assert skus == {"SKU-COKE-330", "SKU-SPRITE-330"}


@pytest.mark.asyncio
async def test_ac06_inventory_staging_and_case_normalization(
    client, data_setup, analytics_repo
):
    admin_headers = data_setup["admin_headers"]
    upload_csv = data_setup["upload_csv_media"]
    store_1_loc = data_setup["store_1_loc"]
    workspace = data_setup["workspace"]

    # CASE unit test: prod_coke has case_units=24. Quantity 3 CASE -> normalized 72 units.
    inventory_csv = (
        b"location_code,sku,observed_at,quantity,unit\n"
        b"LOC-STR01,SKU-COKE-330,2026-09-10T12:00:00Z,3,CASE\n"
        b"LOC-STR01,SKU-SPRITE-330,2026-09-10T12:00:00Z,5,UNIT\n"
    )

    media_id = await upload_csv(inventory_csv)

    # Create import
    create_res = await client.post(
        "/imports",
        json={"kind": "INVENTORY", "media_id": media_id},
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    assert create_res.status_code == 202
    import_id = create_res.json()["resource_id"]

    # Check VALIDATED
    get_res = await client.get(f"/imports/{import_id}", headers=admin_headers)
    assert get_res.json()["status"] == "VALIDATED"

    # Commit
    commit_res = await client.post(
        f"/imports/{import_id}/commit",
        json={"expected_version": 1},
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    assert commit_res.status_code == 202

    # Verify inventory facts with normalized units
    inv_facts = await analytics_repo.get_latest_inventory(
        workspace_id=workspace.id,
        location_ids=[store_1_loc.id],
        as_of_time="2026-09-11T00:00:00Z",
    )
    assert len(inv_facts) == 2
    coke_inv = next(f for f in inv_facts if f["sku"] == "SKU-COKE-330")
    assert coke_inv["quantity"] == 3
    assert coke_inv["unit"] == "CASE"
    assert coke_inv["normalized_units"] == 72  # 3 * 24

    sprite_inv = next(f for f in inv_facts if f["sku"] == "SKU-SPRITE-330")
    assert sprite_inv["quantity"] == 5
    assert sprite_inv["unit"] == "UNIT"
    assert sprite_inv["normalized_units"] == 5
