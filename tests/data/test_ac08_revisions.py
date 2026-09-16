from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_ac08_commit_retry_and_revisions(client, data_setup, analytics_repo):
    admin_headers = data_setup["admin_headers"]
    upload_csv = data_setup["upload_csv_media"]
    store_1 = data_setup["store_1"]
    workspace = data_setup["workspace"]

    # 1. First file: 25 units on 2026-09-10
    batch1_csv = (
        b"store_code,sku,business_date,units,revenue,currency\n"
        b"STR-01,SKU-COKE-330,2026-09-10,25,75.00,SGD\n"
    )

    media_1 = await upload_csv(batch1_csv)
    res1 = await client.post(
        "/imports",
        json={"kind": "SALES", "media_id": media_1},
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    import_1_id = res1.json()["resource_id"]

    # Commit batch 1
    commit1_res = await client.post(
        f"/imports/{import_1_id}/commit",
        json={"expected_version": 1},
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    assert commit1_res.status_code == 202
    imp1 = (await client.get(f"/imports/{import_1_id}", headers=admin_headers)).json()
    batch_1_id = imp1["batch_id"]
    assert batch_1_id is not None

    # Retry commit on same import (idempotent replay)
    retry_commit_res = await client.post(
        f"/imports/{import_1_id}/commit",
        json={"expected_version": 2},  # Version incremented after commit
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    assert retry_commit_res.status_code == 202

    # Verify rows in batch 1
    facts_v1 = await analytics_repo.get_sales_window(
        workspace_id=workspace.id,
        store_id=store_1.id,
        start_date="2026-09-01",
        end_date="2026-09-20",
        batch_ids=[batch_1_id],
    )
    assert len(facts_v1) == 1
    assert facts_v1[0]["units"] == 25

    # 2. Correcting file: units corrected to 35 for same store, sku, date
    batch2_csv = (
        b"store_code,sku,business_date,units,revenue,currency\n"
        b"STR-01,SKU-COKE-330,2026-09-10,35,105.00,SGD\n"
    )

    media_2 = await upload_csv(batch2_csv)
    res2 = await client.post(
        "/imports",
        json={"kind": "SALES", "media_id": media_2},
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    import_2_id = res2.json()["resource_id"]

    # Commit batch 2
    commit2_res = await client.post(
        f"/imports/{import_2_id}/commit",
        json={"expected_version": 1},
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    assert commit2_res.status_code == 202
    imp2 = (await client.get(f"/imports/{import_2_id}", headers=admin_headers)).json()
    batch_2_id = imp2["batch_id"]
    assert batch_2_id != batch_1_id

    # 3. Snapshot isolation check:
    # A query frozen to batch_1_id still returns units=25 (old evidence unchanged!)
    facts_old_snapshot = await analytics_repo.get_sales_window(
        workspace_id=workspace.id,
        store_id=store_1.id,
        start_date="2026-09-01",
        end_date="2026-09-20",
        batch_ids=[batch_1_id],
    )
    assert len(facts_old_snapshot) == 1
    assert facts_old_snapshot[0]["units"] == 25

    # A query across both batches (or new snapshot containing batch_2_id) returns corrected units=35!
    facts_new_snapshot = await analytics_repo.get_sales_window(
        workspace_id=workspace.id,
        store_id=store_1.id,
        start_date="2026-09-01",
        end_date="2026-09-20",
        batch_ids=[batch_1_id, batch_2_id],
    )
    assert len(facts_new_snapshot) == 1
    assert facts_new_snapshot[0]["units"] == 35
    assert facts_new_snapshot[0]["revenue"] == 105.00
    assert facts_new_snapshot[0]["batch_id"] == batch_2_id
