from uuid import uuid4

import pytest
from httpx import AsyncClient
from storeops_contracts.models import Error


@pytest.mark.asyncio
async def test_ac35_catalog_constraints_and_validation(client: AsyncClient, workspace_setup: dict):
    headers = workspace_setup["admin_headers"]

    # 1. Invalid store code (contains illegal spaces/symbols) -> 422
    bad_store_payload = {
        "code": "BAD STORE CODE WITH SPACES!",
        "name": "Invalid Store",
        "retailer": "RetailCo",
        "region": "West",
        "format": "Supermarket",
        "timezone": "Asia/Singapore",
        "distributor_location_id": None,
    }
    r1 = await client.post("/stores", json=bad_store_payload, headers={**headers, "Idempotency-Key": str(uuid4())})
    assert r1.status_code == 422
    err1 = Error.model_validate(r1.json())
    assert err1.code == "VALIDATION_ERROR"
    assert len(err1.details) > 0

    # 2. Invalid product SKU (empty or invalid pattern) -> 422
    bad_prod_payload = {
        "sku": "@#$INVALID",
        "name": "Invalid SKU Product",
        "case_units": 10,
    }
    r2 = await client.post("/products", json=bad_prod_payload, headers={**headers, "Idempotency-Key": str(uuid4())})
    assert r2.status_code == 422
    err2 = Error.model_validate(r2.json())
    assert err2.code == "VALIDATION_ERROR"

    # 3. Product with negative or zero case_units -> 422
    zero_case_payload = {
        "sku": "VALID-SKU-1",
        "name": "Zero Case Product",
        "case_units": 0,
    }
    r3 = await client.post("/products", json=zero_case_payload, headers={**headers, "Idempotency-Key": str(uuid4())})
    assert r3.status_code == 422

    # 4. Unknown store lookup -> 404 Actionable Error
    unknown_id = uuid4()
    r4 = await client.get(f"/stores/{unknown_id}", headers=headers)
    assert r4.status_code == 404
    err4 = Error.model_validate(r4.json())
    assert err4.code == "NOT_FOUND"

    # 5. Unknown product lookup -> 404 Actionable Error
    r5 = await client.get(f"/products/{unknown_id}", headers=headers)
    assert r5.status_code == 404
    err5 = Error.model_validate(r5.json())
    assert err5.code == "NOT_FOUND"

    # 6. Unknown location lookup -> 404 Actionable Error
    r6 = await client.get(f"/locations/{unknown_id}", headers=headers)
    assert r6.status_code == 404
    err6 = Error.model_validate(r6.json())
    assert err6.code == "NOT_FOUND"
