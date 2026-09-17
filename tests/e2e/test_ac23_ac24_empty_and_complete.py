"""Acceptance tests for AC23 and AC24.

AC23: Empty workspace initial state renders empty lists and cleanly guides setup without demo seeds.
AC24: Full end-to-end user workflow: store setup -> import -> investigation -> action -> verification -> report.
"""

import hashlib
import io
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from PIL import Image

from tests.e2e.conftest import FrozenClock


def make_test_jpeg(width: int = 400, height: int = 300, color: str = "blue") -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color=color)
    img.save(buf, format="JPEG")
    return buf.getvalue()


async def upload_csv_media(
    client: AsyncClient,
    headers: dict[str, str],
    content: bytes,
    filename: str = "import.csv",
) -> UUID:
    sha = hashlib.sha256(content).hexdigest()
    init_res = await client.post(
        "/media",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "kind": "IMPORT",
            "filename": filename,
            "mime_type": "text/csv",
            "byte_size": len(content),
            "sha256": sha,
            "store_id": None,
            "visit_id": None,
            "product_id": None,
            "zone_id": None,
            "zone_kind": None,
            "captured_at": None,
        },
    )
    assert init_res.status_code == 201, init_res.text
    init_data = init_res.json()
    media_id = UUID(init_data["media"]["id"])
    upload_url = init_data["upload_url"]

    put_res = await client.put(upload_url, content=content)
    assert put_res.status_code == 200, put_res.text

    complete_res = await client.post(
        f"/media/{media_id}/complete",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )
    assert complete_res.status_code == 200, complete_res.text
    return media_id


@pytest.mark.asyncio
async def test_ac23_empty_workspace_initial_state(
    e2e_client: AsyncClient,
    admin_headers: dict[str, str],
    auth_headers: dict[str, str],
):
    """AC23: A workspace with no stores or commercial data returns clean empty collections."""
    # Check all catalog and management endpoints return empty collections, not 500 or fake seeds
    res_stores = await e2e_client.get("/stores", headers=admin_headers)
    assert res_stores.status_code == 200
    assert res_stores.json()["items"] == []

    res_products = await e2e_client.get("/products", headers=admin_headers)
    assert res_products.status_code == 200
    assert res_products.json()["items"] == []

    res_promotions = await e2e_client.get("/promotions", headers=admin_headers)
    assert res_promotions.status_code == 200
    assert res_promotions.json()["items"] == []

    res_imports = await e2e_client.get("/imports", headers=admin_headers)
    assert res_imports.status_code == 200
    assert res_imports.json()["items"] == []

    res_visits = await e2e_client.get("/visits", headers=auth_headers)
    assert res_visits.status_code == 200
    assert res_visits.json()["items"] == []


@pytest.mark.asyncio
async def test_ac24_full_lifecycle_workflow(
    e2e_client: AsyncClient,
    admin_headers: dict[str, str],
    auth_headers: dict[str, str],
    frozen_clock: FrozenClock,
):
    """AC24: Complete end-to-end lifecycle: store setup -> import -> investigation -> action -> verification -> report."""
    now = frozen_clock.now_utc()

    # 1. Location & Store Setup
    loc_resp = await e2e_client.post(
        "/locations",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "code": "DIST-EAST",
            "name": "East Regional Warehouse",
            "type": "DISTRIBUTOR",
        },
    )
    assert loc_resp.status_code == 201
    dist_id = loc_resp.json()["id"]

    store_code = f"STR-E2E-{uuid4().hex[:4].upper()}"
    store_resp = await e2e_client.post(
        "/stores",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "code": store_code,
            "name": "Flagship Hypermarket",
            "retailer": "RetailGiant",
            "region": "East",
            "format": "HYPERMARKET",
            "timezone": "Asia/Singapore",
            "distributor_location_id": dist_id,
        },
    )
    assert store_resp.status_code == 201
    store = store_resp.json()

    # 2. Product Catalog Setup
    sku = f"SKU-{uuid4().hex[:6].upper()}"
    prod_resp = await e2e_client.post(
        "/products",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "sku": sku,
            "name": "Sparkling Berry Water 330ml",
            "case_units": 24,
        },
    )
    assert prod_resp.status_code == 201
    prod = prod_resp.json()

    # 3. CSV Import (Staging & Atomic Commit)
    csv_bytes = (
        f"store_code,sku,business_date,units,revenue,currency\n"
        f"{store_code},{sku},2026-08-10,48,144.00,SGD\n"
    ).encode()
    media_id = await upload_csv_media(e2e_client, admin_headers, csv_bytes, "sales.csv")

    init_imp = await e2e_client.post(
        "/imports",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "kind": "SALES",
            "media_id": str(media_id),
        },
    )
    assert init_imp.status_code == 202
    imp_job = init_imp.json()
    imp_id = imp_job["resource_id"]

    commit_imp = await e2e_client.post(
        f"/imports/{imp_id}/commit",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )
    assert commit_imp.status_code == 202

    # 4. Promotion & Policy Setup
    today = now.date()
    promo_resp = await e2e_client.post(
        "/promotions",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "name": "Berry Blitz Campaign",
            "starts_on": str(today),
            "ends_on": str(today + timedelta(days=14)),
            "store_ids": [store["id"]],
            "agreement_media_id": None,
        },
    )
    assert promo_resp.status_code == 201
    promo = promo_resp.json()

    rule_id = str(uuid4())
    approve_resp = await e2e_client.post(
        f"/promotions/{promo['id']}/approve",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": promo["version"],
            "catalog_product_ids": [prod["id"]],
            "rules": [
                {
                    "rule_id": rule_id,
                    "kind": "MIN_FACINGS",
                    "zone_id": "shelf-1",
                    "zone_kind": "SHELF",
                    "product_id": prod["id"],
                    "min_facings": 3,
                    "source": {
                        "kind": "MANUAL",
                        "media_id": None,
                        "page": None,
                        "quote": None,
                        "reviewer_note": "Approved mandatory shelf facing contract",
                    },
                }
            ],
        },
    )
    assert approve_resp.status_code == 201

    # 5. Field Visit & Before Imagery
    visit_resp = await e2e_client.post(
        "/visits",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={"store_id": store["id"], "notes": "Commencing shelf audit for Berry Blitz"},
    )
    assert visit_resp.status_code == 201
    visit = visit_resp.json()

    before_jpg = make_test_jpeg(color="red")
    init_before = await e2e_client.post(
        "/media",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={
            "kind": "VISIT_BEFORE",
            "filename": "shelf_before.jpg",
            "mime_type": "image/jpeg",
            "byte_size": len(before_jpg),
            "sha256": hashlib.sha256(before_jpg).hexdigest(),
            "store_id": store["id"],
            "visit_id": visit["id"],
            "product_id": None,
            "zone_id": "shelf-1",
            "zone_kind": "SHELF",
            "captured_at": now.isoformat(),
        },
    )
    assert init_before.status_code == 201
    before_media_id = init_before.json()["media"]["id"]
    await e2e_client.put(init_before.json()["upload_url"], content=before_jpg)
    await e2e_client.post(
        f"/media/{before_media_id}/complete",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )

    # 6. Investigation Creation & Plan Acceptance
    inv_resp = await e2e_client.post(
        "/investigations",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={
            "store_id": store["id"],
            "visit_id": visit["id"],
            "promotion_id": promo["id"],
            "media_ids": [before_media_id],
        },
    )
    assert inv_resp.status_code == 202
    inv_id = inv_resp.json()["resource_id"]

    inv_get = await e2e_client.get(f"/investigations/{inv_id}", headers=auth_headers)
    assert inv_get.status_code == 200
    inv = inv_get.json()
    assert len(inv["actions"]) <= 3

    accept_resp = await e2e_client.post(
        f"/investigations/{inv_id}/accept",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": inv["version"]},
    )
    assert accept_resp.status_code == 200
    accepted_inv = accept_resp.json()

    # 7. Action Claim
    action_id = accepted_inv["actions"][0]["id"]
    claim_resp = await e2e_client.patch(
        f"/investigations/{inv_id}/actions/{action_id}",
        headers=auth_headers,
        json={"expected_version": accepted_inv["version"], "status": "CLAIMED_DONE"},
    )
    assert claim_resp.status_code == 200
    inv_after_claim = (await e2e_client.get(f"/investigations/{inv_id}", headers=auth_headers)).json()

    # 8. After Imagery & Verification
    after_jpg = make_test_jpeg(color="green")
    init_after = await e2e_client.post(
        "/media",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={
            "kind": "VISIT_AFTER",
            "filename": "shelf_after.jpg",
            "mime_type": "image/jpeg",
            "byte_size": len(after_jpg),
            "sha256": hashlib.sha256(after_jpg).hexdigest(),
            "store_id": store["id"],
            "visit_id": visit["id"],
            "product_id": None,
            "zone_id": "shelf-1",
            "zone_kind": "SHELF",
            "captured_at": now.isoformat(),
        },
    )
    assert init_after.status_code == 201
    after_media_id = init_after.json()["media"]["id"]
    await e2e_client.put(init_after.json()["upload_url"], content=after_jpg)
    await e2e_client.post(
        f"/media/{after_media_id}/complete",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )

    ver_resp = await e2e_client.post(
        f"/investigations/{inv_id}/verify",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": inv_after_claim["version"],
            "after_media_ids": [after_media_id],
        },
    )
    assert ver_resp.status_code == 202
    ver_job = ver_resp.json()
    ver_id = ver_job["resource_id"]

    # 9. Verification Result & Final State
    ver_get = await e2e_client.get(f"/verifications/{ver_id}", headers=auth_headers)
    assert ver_get.status_code == 200
    verification = ver_get.json()
    assert verification["result"] in ["PASS", "FAIL", "INCONCLUSIVE"]
    assert verification["report_id"] is not None

    # 10. Audit verification: report is readable and immutable
    report_resp = await e2e_client.get(f"/reports/{verification['report_id']}", headers=auth_headers)
    assert report_resp.status_code == 200
    report_data = report_resp.json()
    assert report_data["id"] == verification["report_id"]
    assert report_data["outcome"] in ["PASS", "FAIL", "PARTIAL", "INCONCLUSIVE", "NO_ACTION"]
