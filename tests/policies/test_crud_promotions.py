"""Tests for Promotion CRUD, permissions, idempotency and validation."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_create_promotion_success(
    client, workspace_setup, sample_store, sample_agreement_media
):
    headers = {
        **workspace_setup["admin_headers"],
        "Idempotency-Key": "promo-create-001",
    }
    today = datetime.now(tz=UTC).date()
    payload = {
        "name": "Spring Coffee Campaign 2026",
        "starts_on": str(today),
        "ends_on": str(today + timedelta(days=30)),
        "store_ids": [str(sample_store.id)],
        "agreement_media_id": str(sample_agreement_media.id),
    }

    resp = await client.post("/promotions", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Spring Coffee Campaign 2026"
    assert data["version"] == 1
    assert data["draft_revision"] == 1
    assert data["archived"] is False
    assert data["agreement_media_id"] == str(sample_agreement_media.id)
    assert data["extracted_rules"] == []
    assert data["extraction_gaps"] == []
    assert data["approved_policy"] is None
    assert len(data["store_ids"]) == 1


@pytest.mark.asyncio
async def test_create_promotion_role_authorization(
    client, workspace_setup, sample_store
):
    headers = {
        **workspace_setup["rep_headers"],
        "Idempotency-Key": "promo-rep-fail",
    }
    today = datetime.now(tz=UTC).date()
    payload = {
        "name": "Unauthorized Promotion",
        "starts_on": str(today),
        "ends_on": str(today + timedelta(days=10)),
        "store_ids": [str(sample_store.id)],
        "agreement_media_id": None,
    }
    resp = await client.post("/promotions", json=payload, headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_promotion_invalid_dates(client, workspace_setup, sample_store):
    headers = {
        **workspace_setup["admin_headers"],
        "Idempotency-Key": "promo-invalid-dates",
    }
    today = datetime.now(tz=UTC).date()
    payload = {
        "name": "Bad Dates Campaign",
        "starts_on": str(today),
        "ends_on": str(today - timedelta(days=5)),  # starts_on > ends_on
        "store_ids": [str(sample_store.id)],
        "agreement_media_id": None,
    }
    resp = await client.post("/promotions", json=payload, headers=headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_promotion_unknown_store(client, workspace_setup):
    headers = {
        **workspace_setup["admin_headers"],
        "Idempotency-Key": "promo-unknown-store",
    }
    today = datetime.now(tz=UTC).date()
    payload = {
        "name": "Unknown Store Campaign",
        "starts_on": str(today),
        "ends_on": str(today + timedelta(days=10)),
        "store_ids": [str(uuid4())],
        "agreement_media_id": None,
    }
    resp = await client.post("/promotions", json=payload, headers=headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_promotion_idempotency(client, workspace_setup, sample_store):
    headers = {
        **workspace_setup["admin_headers"],
        "Idempotency-Key": "promo-idem-key",
    }
    today = datetime.now(tz=UTC).date()
    payload = {
        "name": "Idempotent Campaign",
        "starts_on": str(today),
        "ends_on": str(today + timedelta(days=14)),
        "store_ids": [str(sample_store.id)],
        "agreement_media_id": None,
    }

    # First call -> 201 Created
    r1 = await client.post("/promotions", json=payload, headers=headers)
    assert r1.status_code == 201
    promo_id = r1.json()["id"]

    # Second call with identical payload -> cached 201
    r2 = await client.post("/promotions", json=payload, headers=headers)
    assert r2.status_code == 201
    assert r2.json()["id"] == promo_id

    # Third call with different payload -> 409 Conflict
    diff_payload = {**payload, "name": "Modified Payload"}
    r3 = await client.post("/promotions", json=diff_payload, headers=headers)
    assert r3.status_code == 409


@pytest.mark.asyncio
async def test_get_and_list_promotions(client, workspace_setup, sample_store):
    headers_admin = {
        **workspace_setup["admin_headers"],
        "Idempotency-Key": "promo-get-list-1",
    }
    today = datetime.now(tz=UTC).date()
    payload = {
        "name": "Listing Test Promo",
        "starts_on": str(today),
        "ends_on": str(today + timedelta(days=7)),
        "store_ids": [str(sample_store.id)],
        "agreement_media_id": None,
    }
    created = await client.post("/promotions", json=payload, headers=headers_admin)
    assert created.status_code == 201
    promo_id = created.json()["id"]

    # REP can read promotion
    headers_rep = workspace_setup["rep_headers"]
    get_res = await client.get(f"/promotions/{promo_id}", headers=headers_rep)
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Listing Test Promo"

    # REP can list promotions
    list_res = await client.get("/promotions?limit=10", headers=headers_rep)
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert any(p["id"] == promo_id for p in items)


@pytest.mark.asyncio
async def test_update_promotion(client, workspace_setup, sample_store):
    headers_admin = {
        **workspace_setup["admin_headers"],
        "Idempotency-Key": "promo-update-create",
    }
    today = datetime.now(tz=UTC).date()
    payload = {
        "name": "Initial Name",
        "starts_on": str(today),
        "ends_on": str(today + timedelta(days=7)),
        "store_ids": [str(sample_store.id)],
        "agreement_media_id": None,
    }
    created = await client.post("/promotions", json=payload, headers=headers_admin)
    promo_id = created.json()["id"]
    version = created.json()["version"]

    # REP cannot update promotion
    update_payload = {
        "expected_version": version,
        "name": "Updated by REP",
    }
    rep_res = await client.patch(
        f"/promotions/{promo_id}",
        json=update_payload,
        headers=workspace_setup["rep_headers"],
    )
    assert rep_res.status_code == 403

    # ADMIN updates successfully
    admin_update_payload = {
        "expected_version": version,
        "name": "Updated Name by Admin",
    }
    admin_res = await client.patch(
        f"/promotions/{promo_id}",
        json=admin_update_payload,
        headers=workspace_setup["admin_headers"],
    )
    assert admin_res.status_code == 200
    assert admin_res.json()["name"] == "Updated Name by Admin"
    assert admin_res.json()["version"] == version + 1
    assert admin_res.json()["draft_revision"] == 2

    # Stale expected_version returns 409
    stale_res = await client.patch(
        f"/promotions/{promo_id}",
        json=admin_update_payload,
        headers=workspace_setup["admin_headers"],
    )
    assert stale_res.status_code == 409
