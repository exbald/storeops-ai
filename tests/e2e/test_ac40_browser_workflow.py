"""AC40: End-to-end browser workflow acceptance test.

Verifies the complete vertical slice:
Store setup -> Policy approval -> Rep visit -> Shelf photo -> Investigation -> Plan accept -> Action complete -> Re-verification -> Report.
"""

import hashlib
import io
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image


from tests.e2e.conftest import FrozenClock


def make_test_jpeg(width: int = 400, height: int = 300, color: str = "blue") -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color=color)
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_ac40_complete_browser_workflow_happy_path(
    e2e_client: AsyncClient,
    admin_headers: dict[str, str],
    auth_headers: dict[str, str],
    frozen_clock: FrozenClock,
):
    # 1. Admin creates distributor location
    loc_resp = await e2e_client.post(
        "/locations",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "code": "DIST-CENTRAL",
            "name": "Central Distribution Warehouse",
            "type": "DISTRIBUTOR",
        },
    )
    assert loc_resp.status_code == 201, loc_resp.text
    distributor_id = loc_resp.json()["id"]

    # 2. Admin creates store
    store_resp = await e2e_client.post(
        "/stores",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "code": "STR-001",
            "name": "Downtown Megastore",
            "retailer": "FairPrice",
            "region": "Central",
            "format": "SUPERMARKET",
            "timezone": "Asia/Singapore",
            "distributor_location_id": distributor_id,
        },
    )
    assert store_resp.status_code == 201, store_resp.text
    store_data = store_resp.json()
    store_id = store_data["id"]

    # 3. Admin creates catalog product
    product_resp = await e2e_client.post(
        "/products",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "sku": "SKU-BEV-001",
            "name": "Organic Green Tea 500ml",
            "case_units": 24,
        },
    )
    assert product_resp.status_code == 201, product_resp.text
    product_id = product_resp.json()["id"]

    # 4. Admin uploads agreement media
    dummy_doc_bytes = b"%PDF-1.4 mock pdf content"
    doc_sha256 = hashlib.sha256(dummy_doc_bytes).hexdigest()
    media_doc_resp = await e2e_client.post(
        "/media",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "kind": "AGREEMENT",
            "filename": "agreement.pdf",
            "mime_type": "application/pdf",
            "byte_size": len(dummy_doc_bytes),
            "sha256": doc_sha256,
            "store_id": None,
            "visit_id": None,
            "product_id": None,
            "zone_id": None,
            "zone_kind": None,
            "captured_at": None,
        },
    )
    assert media_doc_resp.status_code == 201, media_doc_resp.text
    doc_upload = media_doc_resp.json()
    agreement_media_id = doc_upload["media"]["id"]

    # Upload bytes
    put_doc = await e2e_client.put(
        str(doc_upload["upload_url"]),
        content=dummy_doc_bytes,
        headers={"Content-Type": "application/pdf"},
    )
    assert put_doc.status_code == 200

    complete_doc = await e2e_client.post(
        f"/media/{agreement_media_id}/complete",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )
    assert complete_doc.status_code == 200, complete_doc.text

    promo_resp = await e2e_client.post(
        "/promotions",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "name": "Q3 Green Tea Promo",
            "starts_on": str(date.today()),
            "ends_on": str(date.today()),
            "store_ids": [store_id],
            "agreement_media_id": agreement_media_id,
        },
    )
    assert promo_resp.status_code == 201, promo_resp.text
    promo_id = promo_resp.json()["id"]

    rule_id = str(uuid4())
    approve_resp = await e2e_client.post(
        f"/promotions/{promo_id}/approve",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": 1,
            "catalog_product_ids": [product_id],
            "rules": [
                {
                    "rule_id": rule_id,
                    "kind": "MIN_FACINGS",
                    "zone_id": "shelf-main",
                    "zone_kind": "SHELF",
                    "product_id": product_id,
                    "min_facings": 2,
                    "source": {
                        "kind": "DOCUMENT",
                        "media_id": agreement_media_id,
                        "page": 1,
                        "quote": "Minimum of 2 facings.",
                        "reviewer_note": None,
                    },
                }
            ],
        },
    )
    assert approve_resp.status_code == 201, approve_resp.text

    # 5. Rep views store and store health
    store_get = await e2e_client.get(f"/stores/{store_id}", headers=auth_headers)
    assert store_get.status_code == 200
    assert store_get.json()["id"] == store_id

    health_get = await e2e_client.get(
        f"/stores/{store_id}/health", headers=auth_headers
    )
    assert health_get.status_code == 200
    health_data = health_get.json()
    assert "freshness" in health_data
    assert "readiness" in health_data

    # 6. Rep begins visit
    visit_resp = await e2e_client.post(
        "/visits",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={
            "store_id": store_id,
            "notes": "Starting routine shelf check",
        },
    )
    assert visit_resp.status_code == 201, visit_resp.text
    visit_data = visit_resp.json()
    visit_id = visit_data["id"]
    assert visit_data["status"] == "OPEN"

    # 7. Rep uploads shelf photo
    shelf_bytes = make_test_jpeg(400, 300, color="blue")
    shelf_sha = hashlib.sha256(shelf_bytes).hexdigest()
    init_media_resp = await e2e_client.post(
        "/media",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={
            "kind": "VISIT_BEFORE",
            "filename": "shelf_before.jpg",
            "mime_type": "image/jpeg",
            "byte_size": len(shelf_bytes),
            "sha256": shelf_sha,
            "store_id": store_id,
            "visit_id": visit_id,
            "product_id": None,
            "zone_id": "shelf-main",
            "zone_kind": "SHELF",
            "captured_at": frozen_clock.now_utc().isoformat(),
        },
    )
    assert init_media_resp.status_code == 201, init_media_resp.text
    shelf_upload = init_media_resp.json()
    media_id = shelf_upload["media"]["id"]

    put_shelf = await e2e_client.put(
        str(shelf_upload["upload_url"]),
        content=shelf_bytes,
        headers={"Content-Type": "image/jpeg"},
    )
    assert put_shelf.status_code == 200

    complete_media_resp = await e2e_client.post(
        f"/media/{media_id}/complete",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )
    assert complete_media_resp.status_code == 200, complete_media_resp.text

    # 8. Rep updates visit notes
    patch_visit = await e2e_client.patch(
        f"/visits/{visit_id}",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": visit_data["version"],
            "notes": "Added shelf photo and checked facings",
        },
    )
    assert patch_visit.status_code == 200, patch_visit.text
    updated_visit = patch_visit.json()
    assert updated_visit["notes"] == "Added shelf photo and checked facings"

    # 9. Rep triggers investigation
    inv_post = await e2e_client.post(
        "/investigations",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={
            "store_id": store_id,
            "visit_id": visit_id,
            "promotion_id": promo_id,
            "media_ids": [media_id],
        },
    )
    assert inv_post.status_code == 202, inv_post.text
    job_data = inv_post.json()
    inv_id = job_data["resource_id"]

    # 10. Rep polls investigation and reviews actions
    inv_get = await e2e_client.get(
        f"/investigations/{inv_id}", headers=auth_headers
    )
    assert inv_get.status_code == 200, inv_get.text
    inv_data = inv_get.json()
    assert inv_data["id"] == inv_id
    assert len(inv_data["actions"]) >= 1

    # 11. Rep accepts plan revision
    accept_resp = await e2e_client.post(
        f"/investigations/{inv_id}/accept",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": inv_data["version"]},
    )
    assert accept_resp.status_code == 200, accept_resp.text
    accepted_inv = accept_resp.json()
    assert accepted_inv["state"] == "ACCEPTED"

    # 12. Rep completes action item
    action_0 = accepted_inv["actions"][0]
    action_patch = await e2e_client.patch(
        f"/investigations/{inv_id}/actions/{action_0['id']}",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": accepted_inv["version"],
            "status": "CLAIMED_DONE",
        },
    )
    assert action_patch.status_code == 200, action_patch.text
    updated_inv = action_patch.json()
    assert updated_inv["actions"][0]["status"] == "CLAIMED_DONE"

    # 13. Rep uploads after-action verification photo
    after_shelf_bytes = make_test_jpeg(400, 300, color="green")
    after_sha = hashlib.sha256(after_shelf_bytes).hexdigest()
    after_init = await e2e_client.post(
        "/media",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={
            "kind": "VISIT_AFTER",
            "filename": "shelf_after.jpg",
            "mime_type": "image/jpeg",
            "byte_size": len(after_shelf_bytes),
            "sha256": after_sha,
            "store_id": store_id,
            "visit_id": visit_id,
            "product_id": None,
            "zone_id": "shelf-main",
            "zone_kind": "SHELF",
            "captured_at": frozen_clock.now_utc().isoformat(),
        },
    )
    assert after_init.status_code == 201, after_init.text
    after_upload = after_init.json()
    after_media_id = after_upload["media"]["id"]

    put_after = await e2e_client.put(
        str(after_upload["upload_url"]),
        content=after_shelf_bytes,
        headers={"Content-Type": "image/jpeg"},
    )
    assert put_after.status_code == 200

    await e2e_client.post(
        f"/media/{after_media_id}/complete",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )

    # 14. Rep verifies investigation
    verify_resp = await e2e_client.post(
        f"/investigations/{inv_id}/verify",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": updated_inv["version"],
            "after_media_ids": [after_media_id],
        },
    )
    assert verify_resp.status_code == 202, verify_resp.text
    verify_job = verify_resp.json()
    assert verify_job["status"] == "SUCCEEDED"
    verification_id = verify_job["resource_id"]

    # 15. Rep lists verifications
    verif_list = await e2e_client.get(
        f"/investigations/{inv_id}/verifications",
        headers=auth_headers,
    )
    assert verif_list.status_code == 200
    assert len(verif_list.json()["items"]) >= 1

    # 16. Rep reads verification report
    verif_detail = await e2e_client.get(
        f"/verifications/{verification_id}",
        headers=auth_headers,
    )
    assert verif_detail.status_code == 200
    report_id = verif_detail.json()["report_id"]

    report_resp = await e2e_client.get(
        f"/reports/{report_id}",
        headers=auth_headers,
    )
    assert report_resp.status_code == 200
    report_data = report_resp.json()
    assert report_data["id"] == report_id
    assert report_data["outcome"] in ["PASS", "FAIL", "PARTIAL", "INCONCLUSIVE", "NO_ACTION"]


@pytest.mark.asyncio
async def test_ac40_concurrency_fencing_and_idempotency(
    e2e_client: AsyncClient,
    admin_headers: dict[str, str],
    auth_headers: dict[str, str],
):
    # Setup store
    store_resp = await e2e_client.post(
        "/stores",
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
        json={
            "code": "STR-002",
            "name": "Fencing Store",
            "retailer": "FairPrice",
            "region": "East",
            "format": "CONVENIENCE",
            "timezone": "Asia/Singapore",
            "distributor_location_id": None,
        },
    )
    assert store_resp.status_code == 201, store_resp.text
    store_id = store_resp.json()["id"]

    # Rep creates visit
    visit_resp = await e2e_client.post(
        "/visits",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={
            "store_id": store_id,
            "notes": "Testing OCC",
        },
    )
    assert visit_resp.status_code == 201, visit_resp.text
    visit_id = visit_resp.json()["id"]

    # Stale version update on visit returns 409 VERSION_CONFLICT
    conflict_resp = await e2e_client.patch(
        f"/visits/{visit_id}",
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": 9999,
            "notes": "Stale update",
        },
    )
    assert conflict_resp.status_code == 409
    assert conflict_resp.json()["code"] == "VERSION_CONFLICT"

    # Idempotent replay on visit creation returns identical 201 response
    idemp_key = str(uuid4())
    create_body = {
        "store_id": store_id,
        "notes": "Idempotent visit",
    }
    r1 = await e2e_client.post(
        "/visits",
        headers={**auth_headers, "Idempotency-Key": idemp_key},
        json=create_body,
    )
    assert r1.status_code == 201
    r2 = await e2e_client.post(
        "/visits",
        headers={**auth_headers, "Idempotency-Key": idemp_key},
        json=create_body,
    )
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
