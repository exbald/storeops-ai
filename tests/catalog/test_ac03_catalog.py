from uuid import uuid4

import pytest
from httpx import AsyncClient
from storeops_contracts.models import (
    Currency,
    Location,
    LocationList,
    Product,
    ProductList,
    Store,
    Type1,
)


@pytest.mark.asyncio
async def test_ac03_store_and_backroom_creation(client: AsyncClient, workspace_setup: dict):
    headers = workspace_setup["admin_headers"]
    headers_with_idem = {**headers, "Idempotency-Key": str(uuid4())}

    store_payload = {
        "code": "STORE-001",
        "name": "Downtown Megastore",
        "retailer": "RetailCo",
        "region": "Central",
        "format": "Hypermarket",
        "timezone": "Asia/Singapore",
        "distributor_location_id": None,
    }

    # 1. Create Store (requires ADMIN)
    res = await client.post("/stores", json=store_payload, headers=headers_with_idem)
    assert res.status_code == 201, res.text
    store_data = res.json()
    store = Store.model_validate(store_data)
    assert store.code == "STORE-001"
    assert store.currency == Currency.SGD
    assert store.active is True
    assert store.version == 1
    assert store.backroom_location_id is not None

    # 2. Verify automatically created backroom location
    loc_res = await client.get(f"/locations/{store.backroom_location_id}", headers=headers)
    assert loc_res.status_code == 200, loc_res.text
    backroom = Location.model_validate(loc_res.json())
    assert backroom.id == store.backroom_location_id
    assert backroom.type == Type1.BACKROOM
    assert backroom.store_id == store.id
    assert backroom.active is True

    # 3. Create Distributor Location
    dist_payload = {
        "code": "DIST-NORTH",
        "name": "Northern Regional Warehouse",
        "type": "DISTRIBUTOR",
    }
    dist_headers = {**headers, "Idempotency-Key": str(uuid4())}
    dist_res = await client.post("/locations", json=dist_payload, headers=dist_headers)
    assert dist_res.status_code == 201, dist_res.text
    dist_loc = Location.model_validate(dist_res.json())
    assert dist_loc.type == Type1.DISTRIBUTOR
    assert dist_loc.store_id is None

    # Verify distributor location is distinct and not copied to stores
    assert dist_loc.id != store.backroom_location_id
    store_locs_res = await client.get(f"/locations?store_id={store.id}", headers=headers)
    assert store_locs_res.status_code == 200
    store_locs = LocationList.model_validate(store_locs_res.json())
    assert len(store_locs.items) == 1
    assert store_locs.items[0].id == store.backroom_location_id


@pytest.mark.asyncio
async def test_ac03_arbitrary_products_and_edit_reload(client: AsyncClient, workspace_setup: dict):
    headers = workspace_setup["admin_headers"]

    # 1. Create arbitrary product
    product_payload = {
        "sku": "CUSTOM-SKU-9988",
        "name": "Organic Oat Milk 1L",
        "case_units": 12,
    }
    prod_res = await client.post(
        "/products",
        json=product_payload,
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert prod_res.status_code == 201, prod_res.text
    product = Product.model_validate(prod_res.json())
    assert product.sku == "CUSTOM-SKU-9988"
    assert product.name == "Organic Oat Milk 1L"
    assert product.case_units == 12
    assert product.version == 1
    assert product.active is True

    # 2. Edit product (optimistic concurrency version increment)
    update_payload = {
        "expected_version": 1,
        "name": "Organic Oat Milk 1L (Fortified)",
        "case_units": 24,
    }
    patch_res = await client.patch(f"/products/{product.id}", json=update_payload, headers=headers)
    assert patch_res.status_code == 200, patch_res.text
    updated_prod = Product.model_validate(patch_res.json())
    assert updated_prod.version == 2
    assert updated_prod.name == "Organic Oat Milk 1L (Fortified)"
    assert updated_prod.case_units == 24

    # 3. Reload from GET endpoint
    get_res = await client.get(f"/products/{product.id}", headers=headers)
    assert get_res.status_code == 200
    reloaded_prod = Product.model_validate(get_res.json())
    assert reloaded_prod == updated_prod

    # 4. List products
    list_res = await client.get("/products", headers=headers)
    assert list_res.status_code == 200
    prod_list = ProductList.model_validate(list_res.json())
    assert any(p.id == product.id for p in prod_list.items)


@pytest.mark.asyncio
async def test_ac03_uniqueness_and_conflicts(client: AsyncClient, workspace_setup: dict):
    headers = workspace_setup["admin_headers"]

    # Create first store
    store_payload = {
        "code": "UNIQUE-STORE",
        "name": "Store Alpha",
        "retailer": "RetailCo",
        "region": "West",
        "format": "Supermarket",
        "timezone": "Asia/Singapore",
        "distributor_location_id": None,
    }
    r1 = await client.post("/stores", json=store_payload, headers={**headers, "Idempotency-Key": str(uuid4())})
    assert r1.status_code == 201

    # Attempt to create duplicate store code in same workspace -> 409
    r2 = await client.post("/stores", json=store_payload, headers={**headers, "Idempotency-Key": str(uuid4())})
    assert r2.status_code == 409

    # Create product
    prod_payload = {
        "sku": "UNIQUE-SKU-1",
        "name": "Product One",
        "case_units": 6,
    }
    p1 = await client.post("/products", json=prod_payload, headers={**headers, "Idempotency-Key": str(uuid4())})
    assert p1.status_code == 201

    # Attempt duplicate SKU -> 409
    p2 = await client.post("/products", json=prod_payload, headers={**headers, "Idempotency-Key": str(uuid4())})
    assert p2.status_code == 409


@pytest.mark.asyncio
async def test_ac03_roles_and_workspace_isolation(client: AsyncClient, workspace_setup: dict):
    rep_headers = workspace_setup["rep_headers"]
    admin_headers = workspace_setup["admin_headers"]
    foreign_headers = workspace_setup["foreign_headers"]

    # 1. REP cannot create store (requires ADMIN) -> 403
    store_payload = {
        "code": "REP-STORE",
        "name": "Unauthorized Store",
        "retailer": "RetailCo",
        "region": "West",
        "format": "Supermarket",
        "timezone": "Asia/Singapore",
        "distributor_location_id": None,
    }
    res = await client.post("/stores", json=store_payload, headers={**rep_headers, "Idempotency-Key": str(uuid4())})
    assert res.status_code == 403

    # 2. Admin creates store
    create_res = await client.post("/stores", json=store_payload, headers={**admin_headers, "Idempotency-Key": str(uuid4())})
    assert create_res.status_code == 201
    store_id = create_res.json()["id"]

    # 3. REP can read store
    read_res = await client.get(f"/stores/{store_id}", headers=rep_headers)
    assert read_res.status_code == 200

    # 4. Foreign workspace gets 404
    foreign_res = await client.get(f"/stores/{store_id}", headers=foreign_headers)
    assert foreign_res.status_code == 404
