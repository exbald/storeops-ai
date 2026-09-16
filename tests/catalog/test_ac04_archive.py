from uuid import uuid4

import pytest
from httpx import AsyncClient
from storeops_contracts.models import Product, Store

from apps.api.modules.catalog.dependencies import get_catalog_repository


@pytest.mark.asyncio
async def test_ac04_product_archive_rejection_with_active_policy(client: AsyncClient, workspace_setup: dict):
    headers = workspace_setup["admin_headers"]

    # 1. Create product
    prod_res = await client.post(
        "/products",
        json={"sku": "PROD-POLICY-1", "name": "Feature Product", "case_units": 10},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert prod_res.status_code == 201
    prod = Product.model_validate(prod_res.json())

    # 2. Simulate an active policy requiring this product in the repository
    catalog_repo = get_catalog_repository()
    await catalog_repo.add_active_policy_product_reference(workspace_setup["workspace_id"], prod.id)

    # 3. Attempt to archive product (active=False) -> MUST return 409 Conflict
    archive_res = await client.patch(
        f"/products/{prod.id}",
        json={"expected_version": 1, "active": False},
        headers=headers,
    )
    assert archive_res.status_code == 409, archive_res.text
    err = archive_res.json()
    assert err["code"] == "POLICY_CONFLICT"
    assert "active policy" in err["message"].lower()

    # Verify product is still active
    recheck_res = await client.get(f"/products/{prod.id}", headers=headers)
    assert recheck_res.status_code == 200
    assert recheck_res.json()["active"] is True

    # 4. Remove policy reference and archive -> Succeeds
    await catalog_repo.remove_active_policy_product_reference(workspace_setup["workspace_id"], prod.id)
    archive_ok_res = await client.patch(
        f"/products/{prod.id}",
        json={"expected_version": 1, "active": False},
        headers=headers,
    )
    assert archive_ok_res.status_code == 200
    archived_prod = Product.model_validate(archive_ok_res.json())
    assert archived_prod.active is False
    assert archived_prod.version == 2


@pytest.mark.asyncio
async def test_ac04_store_archive_and_concurrency(client: AsyncClient, workspace_setup: dict):
    headers = workspace_setup["admin_headers"]

    # 1. Create store
    store_res = await client.post(
        "/stores",
        json={
            "code": "STORE-ARCH-1",
            "name": "Branch to Close",
            "retailer": "RetailCo",
            "region": "East",
            "format": "Convenience",
            "timezone": "Asia/Singapore",
            "distributor_location_id": None,
        },
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert store_res.status_code == 201
    store = Store.model_validate(store_res.json())

    # 2. Version mismatch concurrency check -> 409
    conflict_res = await client.patch(
        f"/stores/{store.id}",
        json={"expected_version": 999, "name": "Conflict Name"},
        headers=headers,
    )
    assert conflict_res.status_code == 409
    assert conflict_res.json()["code"] == "VERSION_CONFLICT"

    # 3. Archive store
    arch_res = await client.patch(
        f"/stores/{store.id}",
        json={"expected_version": 1, "active": False},
        headers=headers,
    )
    assert arch_res.status_code == 200
    archived_store = Store.model_validate(arch_res.json())
    assert archived_store.active is False
    assert archived_store.version == 2

    # 4. Filter active vs archived in list
    active_list = await client.get("/stores?active=true", headers=headers)
    assert active_list.status_code == 200
    assert not any(s["id"] == str(store.id) for s in active_list.json()["items"])

    all_list = await client.get("/stores", headers=headers)
    assert all_list.status_code == 200
    assert any(s["id"] == str(store.id) for s in all_list.json()["items"])
