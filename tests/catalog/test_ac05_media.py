import hashlib
import io
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from storeops_contracts.models import (
    Media,
    MediaUpload,
    Product,
    Status1,
    Store,
)


def make_test_jpeg(width: int = 200, height: int = 150) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color="blue")
    img.save(buf, format="JPEG")
    return buf.getvalue()


def make_exif_jpeg(width: int = 200, height: int = 150) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color="green")
    exif = img.getexif()
    exif[0x0112] = 6  # Orientation: Rotate 90 CW
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_ac05_valid_product_reference_media(client: AsyncClient, workspace_setup: dict):
    headers = workspace_setup["admin_headers"]

    # Create product to bind reference media
    prod_res = await client.post(
        "/products",
        json={"sku": "PROD-REF-01", "name": "Reference Product", "case_units": 12},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert prod_res.status_code == 201
    product = Product.model_validate(prod_res.json())

    jpeg_bytes = make_test_jpeg(400, 300)
    sha256_hex = hashlib.sha256(jpeg_bytes).hexdigest()
    byte_size = len(jpeg_bytes)

    init_payload = {
        "kind": "PRODUCT_REFERENCE",
        "filename": "product_hero.jpg",
        "mime_type": "image/jpeg",
        "byte_size": byte_size,
        "sha256": sha256_hex,
        "store_id": None,
        "visit_id": None,
        "product_id": str(product.id),
        "zone_id": None,
        "zone_kind": None,
        "captured_at": None,
    }

    # 1. Init Media -> MediaUpload with PENDING_UPLOAD
    init_res = await client.post(
        "/media",
        json=init_payload,
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert init_res.status_code == 201, init_res.text
    upload = MediaUpload.model_validate(init_res.json())
    assert upload.media.status == Status1.PENDING_UPLOAD
    assert upload.media.product_id == product.id
    assert upload.upload_url is not None
    assert upload.expires_at is not None

    media_id = upload.media.id

    # 2. Upload bytes to the provided upload URL
    upload_res = await client.put(
        str(upload.upload_url),
        content=jpeg_bytes,
        headers={"Content-Type": "image/jpeg"},
    )
    assert upload_res.status_code == 200, upload_res.text

    # 3. Complete Media -> READY with validated width/height
    complete_res = await client.post(
        f"/media/{media_id}/complete",
        json={"expected_version": 1},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert complete_res.status_code == 200, complete_res.text
    completed_media = Media.model_validate(complete_res.json())
    assert completed_media.status == Status1.READY
    assert completed_media.width == 400
    assert completed_media.height == 300
    assert completed_media.rejection is None

    # 4. Get Media -> metadata and expiring download URL
    get_res = await client.get(f"/media/{media_id}", headers=headers)
    assert get_res.status_code == 200
    got_media = Media.model_validate(get_res.json())
    assert got_media.status == Status1.READY
    assert got_media.download_url is not None
    assert got_media.download_url_expires_at is not None

    # 5. Foreign workspace cannot get media -> 404
    foreign_res = await client.get(f"/media/{media_id}", headers=workspace_setup["foreign_headers"])
    assert foreign_res.status_code == 404


@pytest.mark.asyncio
async def test_ac05_exif_normalization_and_hash_handling(client: AsyncClient, workspace_setup: dict):
    headers = workspace_setup["admin_headers"]

    # Create product to bind
    prod_res = await client.post(
        "/products",
        json={"sku": "PROD-EXIF-01", "name": "Exif Product", "case_units": 6},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    product = Product.model_validate(prod_res.json())

    # Create JPEG with EXIF orientation metadata
    exif_jpeg_bytes = make_exif_jpeg(width=300, height=200)
    raw_sha256 = hashlib.sha256(exif_jpeg_bytes).hexdigest()

    init_res = await client.post(
        "/media",
        json={
            "kind": "PRODUCT_REFERENCE",
            "filename": "exif_photo.jpg",
            "mime_type": "image/jpeg",
            "byte_size": len(exif_jpeg_bytes),
            "sha256": raw_sha256,
            "store_id": None,
            "visit_id": None,
            "product_id": str(product.id),
            "zone_id": None,
            "zone_kind": None,
            "captured_at": None,
        },
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert init_res.status_code == 201
    upload = MediaUpload.model_validate(init_res.json())
    media_id = upload.media.id

    # Upload EXIF bytes
    upload_res = await client.put(str(upload.upload_url), content=exif_jpeg_bytes)
    assert upload_res.status_code == 200

    # Complete upload: must succeed and NOT fail checksum mismatch
    complete_res = await client.post(
        f"/media/{media_id}/complete",
        json={"expected_version": 1},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert complete_res.status_code == 200
    media = Media.model_validate(complete_res.json())
    assert media.status == Status1.READY
    assert media.rejection is None
    assert media.original_sha256 == raw_sha256
    assert media.normalized_sha256 is not None
    # EXIF stripped and image rotated: dimensions transposed (200, 300)
    assert media.width == 200
    assert media.height == 300


@pytest.mark.asyncio
async def test_ac05_media_checksum_mismatch_and_rejection(client: AsyncClient, workspace_setup: dict):
    headers = workspace_setup["admin_headers"]

    # Create store for visit media
    store_res = await client.post(
        "/stores",
        json={
            "code": "ST-VISIT-01",
            "name": "Visit Store",
            "retailer": "Retailer A",
            "region": "West",
            "format": "SUPERMARKET",
            "timezone": "America/Los_Angeles",
            "distributor_location_id": None,
        },
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    store = Store.model_validate(store_res.json())

    raw_bytes = make_test_jpeg(100, 100)
    stated_sha = hashlib.sha256(raw_bytes).hexdigest()

    init_payload = {
        "kind": "VISIT_BEFORE",
        "filename": "shelf.jpg",
        "mime_type": "image/jpeg",
        "byte_size": len(raw_bytes),
        "sha256": stated_sha,
        "store_id": str(store.id),
        "visit_id": str(uuid4()),
        "product_id": None,
        "zone_id": "AISLE-1",
        "zone_kind": "SHELF",
        "captured_at": "2026-09-17T00:00:00Z",
    }
    init_res = await client.post(
        "/media",
        json=init_payload,
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert init_res.status_code == 201
    upload = MediaUpload.model_validate(init_res.json())
    media_id = upload.media.id

    # Upload different bytes (tampered/mismatched checksum)
    tampered_bytes = make_test_jpeg(120, 120)
    await client.put(str(upload.upload_url), content=tampered_bytes)

    # Complete -> rejected with CHECKSUM_MISMATCH
    complete_res = await client.post(
        f"/media/{media_id}/complete",
        json={"expected_version": 1},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert complete_res.status_code == 200
    media = Media.model_validate(complete_res.json())
    assert media.status == Status1.REJECTED
    assert media.rejection is not None
    assert media.rejection.code == "CHECKSUM_MISMATCH"


@pytest.mark.asyncio
async def test_ac05_media_oversize_image_rejection(client: AsyncClient, workspace_setup: dict):
    headers = workspace_setup["admin_headers"]

    prod_res = await client.post(
        "/products",
        json={"sku": "PROD-OVERSIZE", "name": "Big Product", "case_units": 1},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    product = Product.model_validate(prod_res.json())

    # Image larger than 5 MB
    oversize_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * (6 * 1024 * 1024)
    sha256_hex = hashlib.sha256(oversize_bytes).hexdigest()

    init_payload = {
        "kind": "PRODUCT_REFERENCE",
        "filename": "giant_poster.jpg",
        "mime_type": "image/jpeg",
        "byte_size": len(oversize_bytes),
        "sha256": sha256_hex,
        "store_id": None,
        "visit_id": None,
        "product_id": str(product.id),
        "zone_id": None,
        "zone_kind": None,
        "captured_at": None,
    }
    init_res = await client.post(
        "/media",
        json=init_payload,
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert init_res.status_code == 201
    upload = MediaUpload.model_validate(init_res.json())
    media_id = upload.media.id

    await client.put(str(upload.upload_url), content=oversize_bytes)

    complete_res = await client.post(
        f"/media/{media_id}/complete",
        json={"expected_version": 1},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert complete_res.status_code == 200
    media = Media.model_validate(complete_res.json())
    assert media.status == Status1.REJECTED
    assert media.rejection is not None
    assert media.rejection.code in ("FILE_TOO_LARGE", "INVALID_ASSET")


@pytest.mark.asyncio
async def test_ac05_media_binding_and_rbac_rules(client: AsyncClient, workspace_setup: dict):
    admin_headers = workspace_setup["admin_headers"]
    rep_headers = workspace_setup["rep_headers"]

    # 1. REP cannot create reference media (ADMIN only per SEMANTICS) -> 403
    rep_init_res = await client.post(
        "/media",
        json={
            "kind": "PRODUCT_REFERENCE",
            "filename": "ref.jpg",
            "mime_type": "image/jpeg",
            "byte_size": 100,
            "sha256": "a" * 64,
            "store_id": None,
            "visit_id": None,
            "product_id": str(uuid4()),
            "zone_id": None,
            "zone_kind": None,
            "captured_at": None,
        },
        headers={**rep_headers, "Idempotency-Key": str(uuid4())},
    )
    assert rep_init_res.status_code == 403

    # 2. REP cannot create agreement media -> 403
    rep_agree_res = await client.post(
        "/media",
        json={
            "kind": "AGREEMENT",
            "filename": "contract.pdf",
            "mime_type": "application/pdf",
            "byte_size": 100,
            "sha256": "b" * 64,
            "store_id": None,
            "visit_id": None,
            "product_id": None,
            "zone_id": None,
            "zone_kind": None,
            "captured_at": None,
        },
        headers={**rep_headers, "Idempotency-Key": str(uuid4())},
    )
    assert rep_agree_res.status_code == 403

    # 3. Binding validation: PRODUCT_REFERENCE requires product_id -> 422
    missing_prod = await client.post(
        "/media",
        json={
            "kind": "PRODUCT_REFERENCE",
            "filename": "ref.jpg",
            "mime_type": "image/jpeg",
            "byte_size": 100,
            "sha256": "c" * 64,
            "store_id": None,
            "visit_id": None,
            "product_id": None,
            "zone_id": None,
            "zone_kind": None,
            "captured_at": None,
        },
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    assert missing_prod.status_code == 422

    # 4. Inapplicable fields: AGREEMENT cannot have store_id or product_id -> 422
    agree_invalid = await client.post(
        "/media",
        json={
            "kind": "AGREEMENT",
            "filename": "contract.pdf",
            "mime_type": "application/pdf",
            "byte_size": 100,
            "sha256": "d" * 64,
            "store_id": None,
            "visit_id": None,
            "product_id": str(uuid4()),
            "zone_id": None,
            "zone_kind": None,
            "captured_at": None,
        },
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    assert agree_invalid.status_code == 422

    # 5. Mime type compatibility: IMPORT must be text/csv -> 422
    import_bad_mime = await client.post(
        "/media",
        json={
            "kind": "IMPORT",
            "filename": "data.jpg",
            "mime_type": "image/jpeg",
            "byte_size": 100,
            "sha256": "e" * 64,
            "store_id": None,
            "visit_id": None,
            "product_id": None,
            "zone_id": None,
            "zone_kind": None,
            "captured_at": None,
        },
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    assert import_bad_mime.status_code == 422

    # 6. REP CAN create visit media when bound correctly
    store_res = await client.post(
        "/stores",
        json={
            "code": "ST-REP-01",
            "name": "Rep Store",
            "retailer": "Retailer A",
            "region": "West",
            "format": "SUPERMARKET",
            "timezone": "America/Los_Angeles",
            "distributor_location_id": None,
        },
        headers={**admin_headers, "Idempotency-Key": str(uuid4())},
    )
    store = Store.model_validate(store_res.json())

    visit_jpeg = make_test_jpeg(100, 100)
    rep_visit_res = await client.post(
        "/media",
        json={
            "kind": "VISIT_BEFORE",
            "filename": "rep_photo.jpg",
            "mime_type": "image/jpeg",
            "byte_size": len(visit_jpeg),
            "sha256": hashlib.sha256(visit_jpeg).hexdigest(),
            "store_id": str(store.id),
            "visit_id": str(uuid4()),
            "product_id": None,
            "zone_id": "ZONE-1",
            "zone_kind": "SHELF",
            "captured_at": "2026-09-17T01:00:00Z",
        },
        headers={**rep_headers, "Idempotency-Key": str(uuid4())},
    )
    assert rep_visit_res.status_code == 201
