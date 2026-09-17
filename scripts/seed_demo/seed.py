"""Autonomous demo seed script for StoreOps.

Seeds an independent demonstration workspace with standard catalog, distributor,
sales, inventory, promotional policies (manual rules), visit, and shelf audit
media using only standard HTTP client operations (AC30).

Note:
When running CLI against a live server, direct HTTP PUT to upload_url relies on
the underlying blob storage provider supporting PUT uploads (e.g., GCS signed
URLs or local media upload endpoint).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx

DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "demo"


async def upload_demo_media(
    client: httpx.AsyncClient,
    file_path: Path,
    kind: str,
    headers: dict[str, str],
    store_id: str | None = None,
    zone_id: str | None = None,
    zone_kind: str | None = None,
    captured_at: str | None = None,
    visit_id: str | None = None,
) -> str:
    """Upload a demo media artifact via standard upload-url and complete flow.

    Uses deterministic idempotency keys derived from content sha256 and media kind
    to ensure strict idempotence across multiple invocations.
    """
    file_bytes = file_path.read_bytes()
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()
    mime_type = "text/csv" if file_path.suffix == ".csv" else "image/jpeg"

    if kind in ("IMPORT", "AGREEMENT"):
        store_id = None
        visit_id = None
        zone_id = None
        zone_kind = None
        captured_at = None

    init_payload: dict[str, object] = {
        "kind": kind,
        "filename": file_path.name,
        "mime_type": mime_type,
        "byte_size": len(file_bytes),
        "sha256": sha256_hash,
        "store_id": store_id,
        "visit_id": visit_id,
        "product_id": None,
        "zone_id": zone_id,
        "zone_kind": zone_kind,
        "captured_at": captured_at,
    }

    req_headers = dict(headers)
    req_headers["Idempotency-Key"] = f"seed-media-init-{sha256_hash[:16]}-{kind}"

    init_res = await client.post("/media", json=init_payload, headers=req_headers)
    if init_res.status_code != 201:
        raise RuntimeError(
            f"Failed to initiate media upload for {file_path.name}: {init_res.status_code} {init_res.text}"
        )

    data = init_res.json()
    media_obj = data["media"]
    media_id = media_obj["id"]

    # If already completed via prior idempotent run, return existing media
    if media_obj.get("status") == "READY":
        return media_id

    upload_url = data["upload_url"]

    # For ASGI test client compatibility where upload_url host may differ from test transport host,
    # preserve relative path with full query string; otherwise preserve complete upload_url
    parsed = urlparse(upload_url)
    if client.base_url.host in ("testserver", "localhost", "127.0.0.1") and parsed.netloc != client.base_url.netloc:
        upload_target = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    else:
        upload_target = upload_url

    put_res = await client.put(upload_target, content=file_bytes)
    if put_res.status_code not in (200, 201):
        raise RuntimeError(
            f"Failed to PUT media bytes for {media_id}: {put_res.status_code} {put_res.text}"
        )

    complete_res = await client.post(
        f"/media/{media_id}/complete",
        headers={**req_headers, "Idempotency-Key": f"seed-media-complete-{sha256_hash[:16]}-{kind}"},
        json={"expected_version": 1},
    )
    if complete_res.status_code not in (200, 201):
        raise RuntimeError(
            f"Failed to complete media upload for {media_id}: {complete_res.status_code} {complete_res.text}"
        )

    return media_id


async def seed_workspace(
    client: httpx.AsyncClient,
    workspace_id: UUID,
    admin_headers: dict[str, str],
    fixtures_dir: Path | None = None,
) -> dict[str, object]:
    """Idempotently seed a workspace with complete demo data using standard HTTP APIs."""
    base_dir = fixtures_dir or DEFAULT_FIXTURES_DIR
    manifest_path = base_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Demo manifest not found at {manifest_path}")

    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    sales_path = base_dir / manifest["imports"]["sales_csv"]
    inv_path = base_dir / manifest["imports"]["inventory_csv"]
    before_path = base_dir / manifest["media"]["shelf_before"]
    after_path = base_dir / manifest["media"]["shelf_after"]

    for p in (sales_path, inv_path, before_path, after_path):
        if not p.exists():
            raise FileNotFoundError(f"Required demo fixture missing: {p}")

    headers = dict(admin_headers)
    headers["X-Workspace-Id"] = str(workspace_id)

    # 1. Distributor Location (create or reuse)
    dist_config = manifest["distributor"]
    dist_loc_id: str | None = None
    locs_res = await client.get("/locations", headers=headers)
    if locs_res.status_code == 200:
        for loc in locs_res.json().get("items", []):
            if loc.get("code") == dist_config["code"]:
                dist_loc_id = loc["id"]
                break

    if not dist_loc_id:
        loc_headers = dict(headers)
        loc_headers["Idempotency-Key"] = f"seed-loc-{dist_config['code']}"
        create_loc_res = await client.post(
            "/locations",
            json={
                "code": dist_config["code"],
                "name": dist_config["name"],
                "type": dist_config["type"],
            },
            headers=loc_headers,
        )
        if create_loc_res.status_code != 201:
            raise RuntimeError(
                f"Failed to create distributor location: {create_loc_res.status_code} {create_loc_res.text}"
            )
        dist_loc_id = create_loc_res.json()["id"]

    # 2. Store (create or reuse)
    store_config = manifest["store"]
    store_id: str | None = None
    stores_res = await client.get("/stores", headers=headers)
    if stores_res.status_code == 200:
        for st in stores_res.json().get("items", []):
            if st.get("code") == store_config["code"]:
                store_id = st["id"]
                break

    if not store_id:
        store_headers = dict(headers)
        store_headers["Idempotency-Key"] = f"seed-store-{store_config['code']}"
        create_store_res = await client.post(
            "/stores",
            json={
                "code": store_config["code"],
                "name": store_config["name"],
                "retailer": store_config["retailer"],
                "region": store_config["region"],
                "format": store_config["format"],
                "timezone": store_config["timezone"],
                "distributor_location_id": dist_loc_id,
            },
            headers=store_headers,
        )
        if create_store_res.status_code != 201:
            raise RuntimeError(
                f"Failed to create store: {create_store_res.status_code} {create_store_res.text}"
            )
        store_id = create_store_res.json()["id"]

    # 3. Product (create or reuse)
    prod_config = manifest["product"]
    product_id: str | None = None
    prods_res = await client.get("/products", headers=headers)
    if prods_res.status_code == 200:
        for p in prods_res.json().get("items", []):
            if p.get("sku") == prod_config["sku"]:
                product_id = p["id"]
                break

    if not product_id:
        prod_headers = dict(headers)
        prod_headers["Idempotency-Key"] = f"seed-prod-{prod_config['sku']}"
        create_prod_res = await client.post(
            "/products",
            json={
                "sku": prod_config["sku"],
                "name": prod_config["name"],
                "case_units": prod_config["case_units"],
            },
            headers=prod_headers,
        )
        if create_prod_res.status_code != 201:
            raise RuntimeError(
                f"Failed to create product: {create_prod_res.status_code} {create_prod_res.text}"
            )
        product_id = create_prod_res.json()["id"]

    # 4. Imports: Sales CSV (upload media, create import, commit)
    sales_bytes = sales_path.read_bytes()
    sales_sha256 = hashlib.sha256(sales_bytes).hexdigest()
    sales_import_id: str | None = None
    sales_committed_count = 0
    imports_res = await client.get("/imports", headers=headers)
    if imports_res.status_code == 200:
        for imp in imports_res.json().get("items", []):
            if imp.get("kind") == "SALES" and imp.get("status") == "COMMITTED":
                sales_import_id = imp["id"]
                sales_committed_count = imp.get("row_count", 1)
                break

    if not sales_import_id:
        sales_media_id = await upload_demo_media(
            client,
            sales_path,
            kind="IMPORT",
            headers=headers,
            store_id=store_id,
        )
        sales_create_res = await client.post(
            "/imports",
            headers={**headers, "Idempotency-Key": f"seed-import-sales-{sales_sha256[:16]}"},
            json={"kind": "SALES", "media_id": sales_media_id},
        )
        if sales_create_res.status_code != 202:
            raise RuntimeError(
                f"Failed to stage sales import: {sales_create_res.status_code} {sales_create_res.text}"
            )
        sales_import_id = sales_create_res.json()["resource_id"]

        sales_commit = await client.post(
            f"/imports/{sales_import_id}/commit",
            headers={**headers, "Idempotency-Key": f"seed-commit-sales-{sales_import_id}"},
            json={"expected_version": 1},
        )
        if sales_commit.status_code not in (200, 202):
            raise RuntimeError(
                f"Failed to commit sales import: {sales_commit.status_code} {sales_commit.text}"
            )

        verify_sales = await client.get(f"/imports/{sales_import_id}", headers=headers)
        if verify_sales.status_code != 200 or verify_sales.json().get("status") != "COMMITTED":
            raise RuntimeError(
                f"Sales import commit check failed: {verify_sales.status_code} {verify_sales.text}"
            )
        sales_committed_count = verify_sales.json().get("row_count", 1)

    # 5. Imports: Inventory CSV (upload media, create import, commit)
    inv_bytes = inv_path.read_bytes()
    inv_sha256 = hashlib.sha256(inv_bytes).hexdigest()
    inv_import_id: str | None = None
    inv_committed_count = 0
    if imports_res.status_code == 200:
        for imp in imports_res.json().get("items", []):
            if imp.get("kind") == "INVENTORY" and imp.get("status") == "COMMITTED":
                inv_import_id = imp["id"]
                inv_committed_count = imp.get("row_count", 1)
                break

    if not inv_import_id:
        inv_media_id = await upload_demo_media(
            client,
            inv_path,
            kind="IMPORT",
            headers=headers,
            store_id=store_id,
        )
        inv_create_res = await client.post(
            "/imports",
            headers={**headers, "Idempotency-Key": f"seed-import-inv-{inv_sha256[:16]}"},
            json={"kind": "INVENTORY", "media_id": inv_media_id},
        )
        if inv_create_res.status_code != 202:
            raise RuntimeError(
                f"Failed to stage inventory import: {inv_create_res.status_code} {inv_create_res.text}"
            )
        inv_import_id = inv_create_res.json()["resource_id"]

        inv_commit = await client.post(
            f"/imports/{inv_import_id}/commit",
            headers={**headers, "Idempotency-Key": f"seed-commit-inv-{inv_import_id}"},
            json={"expected_version": 1},
        )
        if inv_commit.status_code not in (200, 202):
            raise RuntimeError(
                f"Failed to commit inventory import: {inv_commit.status_code} {inv_commit.text}"
            )

        verify_inv = await client.get(f"/imports/{inv_import_id}", headers=headers)
        if verify_inv.status_code != 200 or verify_inv.json().get("status") != "COMMITTED":
            raise RuntimeError(
                f"Inventory import commit check failed: {verify_inv.status_code} {verify_inv.text}"
            )
        inv_committed_count = verify_inv.json().get("row_count", 1)

    # 6. Promotional Policy (create draft and approve)
    promo_config = manifest["policies"]
    promo_id: str | None = None
    promo_version = 1
    promos_res = await client.get("/promotions", headers=headers)
    if promos_res.status_code == 200:
        for p in promos_res.json().get("items", []):
            if p.get("name") == promo_config["promotion_title"]:
                promo_id = p["id"]
                promo_version = p.get("version", 1)
                break

    if not promo_id:
        promo_headers = dict(headers)
        promo_headers["Idempotency-Key"] = f"seed-promo-{manifest['dated']}"
        create_promo_res = await client.post(
            "/promotions",
            json={
                "name": promo_config["promotion_title"],
                "starts_on": "2026-09-01",
                "ends_on": "2026-09-30",
                "store_ids": [str(store_id)],
                "agreement_media_id": None,
            },
            headers=promo_headers,
        )
        if create_promo_res.status_code != 201:
            raise RuntimeError(
                f"Failed to create draft promotion: {create_promo_res.status_code} {create_promo_res.text}"
            )
        promo_data = create_promo_res.json()
        promo_id = promo_data["id"]
        promo_version = promo_data["version"]

        rule_cfg = promo_config.get("rule", {})
        merch_rule = {
            "rule_id": str(uuid4()),
            "kind": "MIN_FACINGS",
            "zone_id": store_config["zone_id"],
            "zone_kind": store_config["zone_kind"],
            "product_id": str(product_id),
            "min_facings": rule_cfg.get("min_facings", 2),
            "source": {
                "kind": "MANUAL",
                "media_id": None,
                "page": None,
                "quote": None,
                "reviewer_note": rule_cfg.get("reviewer_note", "Demo merchandising facing rule"),
            },
        }

        # Approve policy with required catalog_product_ids and expected_version
        approve_headers = dict(headers)
        approve_headers["Idempotency-Key"] = f"seed-approve-promo-{promo_id}"
        approve_res = await client.post(
            f"/promotions/{promo_id}/approve",
            json={
                "expected_version": promo_version,
                "rules": [merch_rule],
                "catalog_product_ids": [str(product_id)],
            },
            headers=approve_headers,
        )
        if approve_res.status_code not in (200, 201):
            raise RuntimeError(
                f"Failed to approve promotion: {approve_res.status_code} {approve_res.text}"
            )

        get_promo_res = await client.get(f"/promotions/{promo_id}", headers=headers)
        if get_promo_res.status_code == 200:
            promo_version = get_promo_res.json().get("version", promo_version + 1)
        else:
            promo_version += 1

    # 7. Store Visit (create or reuse)
    visit_id: str | None = None
    visits_res = await client.get(f"/visits?store_id={store_id}", headers=headers)
    if visits_res.status_code == 200:
        visits_items = visits_res.json().get("items", [])
        if visits_items:
            visit_id = visits_items[0]["id"]

    if not visit_id:
        visit_headers = dict(headers)
        visit_headers["Idempotency-Key"] = f"seed-visit-{store_id}-{manifest['dated']}"
        create_visit_res = await client.post(
            "/visits",
            json={
                "store_id": str(store_id),
                "notes": "Demo shelf audit visit",
            },
            headers=visit_headers,
        )
        if create_visit_res.status_code != 201:
            raise RuntimeError(
                f"Failed to create visit: {create_visit_res.status_code} {create_visit_res.text}"
            )
        visit_id = create_visit_res.json()["id"]

    # 8. Shelf Audit Media (before and after)
    before_media_id = await upload_demo_media(
        client,
        before_path,
        kind="VISIT_BEFORE",
        headers=headers,
        store_id=store_id,
        zone_id=store_config["zone_id"],
        zone_kind=store_config["zone_kind"],
        captured_at=f"{manifest['dated']}T09:00:00Z",
        visit_id=visit_id,
    )

    after_media_id = await upload_demo_media(
        client,
        after_path,
        kind="VISIT_AFTER",
        headers=headers,
        store_id=store_id,
        zone_id=store_config["zone_id"],
        zone_kind=store_config["zone_kind"],
        captured_at=f"{manifest['dated']}T10:00:00Z",
        visit_id=visit_id,
    )

    return {
        "status": "SUCCESS",
        "workspace_id": str(workspace_id),
        "distributor_location_id": str(dist_loc_id),
        "store_id": str(store_id),
        "product_id": str(product_id),
        "sales_import_id": str(sales_import_id),
        "sales_committed_count": sales_committed_count,
        "inventory_import_id": str(inv_import_id),
        "inventory_committed_count": inv_committed_count,
        "promotion_id": str(promo_id),
        "promotion_version": promo_version,
        "visit_id": str(visit_id),
        "shelf_before_media_id": str(before_media_id),
        "shelf_after_media_id": str(after_media_id),
    }


def build_cli_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser for standalone seed execution."""
    parser = argparse.ArgumentParser(
        description="Seed a StoreOps workspace with independent demo data.",
    )
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8000",
        help="Base URL of StoreOps API service",
    )
    parser.add_argument(
        "--workspace-id",
        required=True,
        help="Target workspace UUID to seed",
    )
    parser.add_argument(
        "--token",
        default="demo-admin",
        help="Bearer auth token (defaults to demo-admin)",
    )
    parser.add_argument(
        "--fixtures-dir",
        default=str(DEFAULT_FIXTURES_DIR),
        help="Custom fixtures directory containing manifest.json",
    )
    return parser


async def main() -> None:
    """CLI execution entrypoint."""
    parser = build_cli_parser()
    args = parser.parse_args()

    ws_id = UUID(args.workspace_id)
    admin_headers = {
        "Authorization": f"Bearer {args.token}",
        "X-Workspace-Id": str(ws_id),
    }

    async with httpx.AsyncClient(base_url=args.api_url, timeout=30.0) as client:
        result = await seed_workspace(
            client,
            ws_id,
            admin_headers,
            fixtures_dir=Path(args.fixtures_dir),
        )
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
