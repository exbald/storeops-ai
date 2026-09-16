import hashlib
import io
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from storeops_contracts.models import (
    Media,
    MediaUpload,
    Status1,
    ZoneKind,
)


def make_test_jpeg(width: int = 200, height: int = 150) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color="blue")
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_ac05_valid_media_init_upload_and_complete(client: AsyncClient, workspace_setup: dict):
    headers = workspace_setup["admin_headers"]
    product_id = uuid4()
    visit_id = uuid4()

    jpeg_bytes = make_test_jpeg(400, 300)
    sha256_hex = hashlib.sha256(jpeg_bytes).hexdigest()
    byte_size = len(jpeg_bytes)

    init_payload = {
        "kind": "PRODUCT_REFERENCE",
        "filename": "shelf_display.jpg",
        "mime_type": "image/jpeg",
        "byte_size": byte_size,
        "sha256": sha256_hex,
        "store_id": None,
        "visit_id": str(visit_id),
        "product_id": str(product_id),
        "zone_id": "AISLE-3B",
        "zone_kind": "SHELF",
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
    assert upload.media.product_id == product_id
    assert upload.media.zone_id == "AISLE-3B"
    assert upload.media.zone_kind == ZoneKind.SHELF
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
async def test_ac05_media_checksum_mismatch_and_rejection(client: AsyncClient, workspace_setup: dict):
    headers = workspace_setup["admin_headers"]

    raw_bytes = make_test_jpeg(100, 100)
    stated_sha = hashlib.sha256(raw_bytes).hexdigest()

    init_payload = {
        "kind": "VISIT_BEFORE",
        "filename": "shelf.jpg",
        "mime_type": "image/jpeg",
        "byte_size": len(raw_bytes),
        "sha256": stated_sha,
        "store_id": None,
        "visit_id": None,
        "product_id": None,
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
        "product_id": None,
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
