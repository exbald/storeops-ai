"""Integration tests for AC02, AC04, and AC05.

AC02: Multi-workspace isolation & role authorization.
AC04: Catalog lifecycle, policy constraints on archiving, archived store visit rejection.
AC05: Media upload lifecycle, validation, and zone/entity binding.
"""

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ac02_cross_workspace_isolation_and_role_authorization(
    integration_client: AsyncClient,
    admin_a_headers: dict[str, str],
    rep_a_headers: dict[str, str],
    admin_b_headers: dict[str, str],
):
    """AC02: Cross-workspace access returns 404; REP accessing ADMIN routes returns 403."""
    # 1. Admin A creates a store in Workspace A
    store_payload = {
        "code": f"STR-A-{uuid4().hex[:6]}",
        "name": "Alpha Supermarket Jurong",
        "retailer": "Alpha Retail",
        "region": "West",
        "format": "Supermarket",
        "timezone": "Asia/Singapore",
        "distributor_location_id": None,
    }
    create_resp = await integration_client.post(
        "/stores",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json=store_payload,
    )
    assert create_resp.status_code == 201
    store_a_id = create_resp.json()["id"]

    # 2. Workspace B Admin attempts to lookup Store A -> must return 404 (no leak)
    lookup_b_resp = await integration_client.get(
        f"/stores/{store_a_id}",
        headers=admin_b_headers,
    )
    assert lookup_b_resp.status_code == 404, "Foreign workspace lookup must return 404"

    # 3. REP A attempts to create a product (Admin-only command) -> must return 403
    product_payload = {
        "sku": f"SKU-REP-{uuid4().hex[:6]}",
        "name": "Forbidden Rep Product",
        "case_units": 12,
    }
    rep_create_resp = await integration_client.post(
        "/products",
        headers={**rep_a_headers, "Idempotency-Key": str(uuid4())},
        json=product_payload,
    )
    assert rep_create_resp.status_code == 403, "REP executing ADMIN createProduct must return 403"

    # 4. Verify unauthorized request caused zero mutation in catalog
    list_products_resp = await integration_client.get("/products", headers=admin_a_headers)
    assert list_products_resp.status_code == 200
    skus = [p["sku"] for p in list_products_resp.json()["items"]]
    assert product_payload["sku"] not in skus, "Unauthorized product creation must not mutate catalog"


@pytest.mark.asyncio
async def test_ac04_archived_store_cannot_start_visit(
    integration_client: AsyncClient,
    admin_a_headers: dict[str, str],
    rep_a_headers: dict[str, str],
):
    """AC04: Archived store cannot start a visit."""
    # 1. Create store
    store_resp = await integration_client.post(
        "/stores",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "code": f"STR-ARCH-{uuid4().hex[:6]}",
            "name": "Store to Archive",
            "retailer": "Alpha Retail",
            "region": "East",
            "format": "Supermarket",
            "timezone": "Asia/Singapore",
            "distributor_location_id": None,
        },
    )
    assert store_resp.status_code == 201
    store = store_resp.json()
    store_id = store["id"]

    # 2. Archive store (active = False)
    update_resp = await integration_client.patch(
        f"/stores/{store_id}",
        headers=admin_a_headers,
        json={
            "expected_version": store["version"],
            "name": "Store to Archive (Archived)",
            "active": False,
        },
    )
    assert update_resp.status_code == 200

    # 3. REP attempts to start visit on archived store -> rejected
    visit_resp = await integration_client.post(
        "/visits",
        headers={**rep_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "store_id": store_id,
            "notes": "Attempting visit on archived store",
        },
    )
    assert visit_resp.status_code in [400, 404, 409, 422], "Starting a visit on an archived store must fail"


@pytest.mark.asyncio
async def test_ac05_media_lifecycle_validation_and_binding(
    integration_client: AsyncClient,
    rep_a_headers: dict[str, str],
    admin_a_headers: dict[str, str],
):
    """AC05: Media upload lifecycle, byte validation, and zone/entity binding."""
    # 1. Create active store and start visit
    store_resp = await integration_client.post(
        "/stores",
        headers={**admin_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "code": f"STR-MED-{uuid4().hex[:6]}",
            "name": "Media Test Store",
            "retailer": "Alpha Retail",
            "region": "Central",
            "format": "Hypermarket",
            "timezone": "Asia/Singapore",
            "distributor_location_id": None,
        },
    )
    assert store_resp.status_code == 201
    store_id = store_resp.json()["id"]

    visit_resp = await integration_client.post(
        "/visits",
        headers={**rep_a_headers, "Idempotency-Key": str(uuid4())},
        json={"store_id": store_id, "notes": "Media validation visit"},
    )
    assert visit_resp.status_code == 201
    visit_id = visit_resp.json()["id"]

    # 2. Init media upload for visit shelf zone
    raw_bytes = b"JPEG_VALID_TEST_IMAGE_CONTENT_STOREOPS"
    content_hash = hashlib.sha256(raw_bytes).hexdigest()

    init_resp = await integration_client.post(
        "/media",
        headers={**rep_a_headers, "Idempotency-Key": str(uuid4())},
        json={
            "kind": "VISIT_BEFORE",
            "filename": "shelf_before.jpg",
            "mime_type": "image/jpeg",
            "byte_size": len(raw_bytes),
            "sha256": content_hash,
            "store_id": store_id,
            "visit_id": visit_id,
            "product_id": None,
            "zone_id": "ZONE-01",
            "zone_kind": "SHELF",
            "captured_at": datetime.now(UTC).isoformat(),
        },
    )
    assert init_resp.status_code == 201
    media_data = init_resp.json()
    media_id = media_data["media"]["id"]
    upload_url = media_data["upload_url"]
    assert upload_url, "Must provide upload URL"

    # 3. Perform byte upload
    put_resp = await integration_client.put(upload_url, content=raw_bytes)
    assert put_resp.status_code == 200

    # 4. Complete media upload
    complete_resp = await integration_client.post(
        f"/media/{media_id}/complete",
        headers={**rep_a_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )
    assert complete_resp.status_code == 200
    completed = complete_resp.json()
    assert completed["status"] == "READY", "Validated media must transition to READY status"
    assert completed["original_sha256"] == content_hash
    assert completed["visit_id"] == visit_id
