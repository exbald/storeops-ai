"""Acceptance tests for AC30: Optional independent demo seed and replay suite.

Verifies:
1. Complete isolation: Application modules under apps/ never import fixtures/demo or scripts/seed_demo.
2. Seed script independence: scripts/seed_demo/seed.py has zero imports from apps.api.
3. Demonstration fixtures exist, are dated, and conform to contracts.
4. Idempotency: Double-run of seed against a workspace produces identical, non-duplicated entities (including media).
5. Verification of all resources: Store, distributor location, product, committed imports, active promotion, visit, and media.
6. Multi-tenant isolation: Demo data in one workspace does not leak into other workspaces.
7. Integration gate: The application and services run cleanly when fixtures/demo is physically moved aside.
"""

from __future__ import annotations

import ast
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image

from tests.demo.conftest import provision_demo_workspace


def test_ac30_no_app_imports_demo_fixtures_or_evals():
    """AC30 / AGENTS.md invariant: Application modules must not import fixtures, demo seeds or evaluation labels."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    apps_dir = repo_root / "apps"

    forbidden_roots = {"fixtures", "evals", "scripts.seed_demo"}

    for py_file in apps_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_pkg = alias.name.split(".")[0]
                    assert root_pkg not in forbidden_roots, (
                        f"Forbidden import '{alias.name}' found in {py_file}"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                root_pkg = node.module.split(".")[0]
                assert root_pkg not in forbidden_roots, (
                    f"Forbidden import 'from {node.module}' found in {py_file}"
                )


def test_ac30_seed_script_no_server_internal_imports():
    """AC30 invariant: scripts/seed_demo must use normal services and avoid importing server internals."""
    seed_file = Path(__file__).resolve().parent.parent.parent / "scripts" / "seed_demo" / "seed.py"
    assert seed_file.exists(), f"Seed file not found at {seed_file}"

    content = seed_file.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(seed_file))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("apps"), (
                    f"Forbidden internal import '{alias.name}' in seed.py"
                )
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("apps"), (
                f"Forbidden internal import 'from {node.module}' in seed.py"
            )


def test_ac30_demo_fixtures_existence_and_structure():
    """AC30: Demo files, sales CSV, inventory CSV, and media exist and conform to schemas."""
    fixtures_dir = Path(__file__).resolve().parent.parent.parent / "fixtures" / "demo"
    manifest_path = fixtures_dir / "manifest.json"
    assert manifest_path.exists(), "manifest.json missing in fixtures/demo"

    sales_path = fixtures_dir / "sales.csv"
    assert sales_path.exists(), "sales.csv missing in fixtures/demo"
    sales_header = sales_path.read_text(encoding="utf-8").splitlines()[0]
    assert sales_header == "store_code,sku,business_date,units,revenue,currency"

    inv_path = fixtures_dir / "inventory.csv"
    assert inv_path.exists(), "inventory.csv missing in fixtures/demo"
    inv_header = inv_path.read_text(encoding="utf-8").splitlines()[0]
    assert inv_header == "location_code,sku,observed_at,quantity,unit"

    shelf_before = fixtures_dir / "media" / "shelf_before.jpg"
    assert shelf_before.exists(), "shelf_before.jpg missing"

    shelf_after = fixtures_dir / "media" / "shelf_after.jpg"
    assert shelf_after.exists(), "shelf_after.jpg missing"


def test_ac30_demo_images_are_valid_jpeg():
    """Verify demo shelf images are valid non-corrupted JPEGs."""
    fixtures_dir = Path(__file__).resolve().parent.parent.parent / "fixtures" / "demo"
    for img_name in ("shelf_before.jpg", "shelf_after.jpg"):
        img_path = fixtures_dir / "media" / img_name
        with Image.open(img_path) as img:
            assert img.format == "JPEG"
            assert img.width > 0 and img.height > 0


@pytest.mark.asyncio
async def test_ac30_seed_demo_idempotence(demo_client: AsyncClient):
    """AC30: Running seed_demo twice against a target workspace is strictly idempotent and creates all entities."""
    from scripts.seed_demo.seed import seed_workspace

    workspace_id = uuid4()
    await provision_demo_workspace(workspace_id)

    admin_headers = {
        "Authorization": "Bearer demo-admin",
        "X-Workspace-Id": str(workspace_id),
    }

    # Run 1: First seed execution
    result_run1 = await seed_workspace(demo_client, workspace_id, admin_headers)
    assert result_run1["status"] == "SUCCESS"
    assert result_run1["store_id"] is not None
    assert result_run1["distributor_location_id"] is not None
    assert result_run1["product_id"] is not None
    assert result_run1["promotion_id"] is not None
    assert result_run1["promotion_version"] == 2  # draft (1) + approved (2)
    assert result_run1["visit_id"] is not None
    assert result_run1["sales_import_id"] is not None
    assert result_run1["inventory_import_id"] is not None
    assert result_run1["shelf_before_media_id"] is not None
    assert result_run1["shelf_after_media_id"] is not None

    # Run 2: Second seed execution (must be idempotent)
    result_run2 = await seed_workspace(demo_client, workspace_id, admin_headers)
    assert result_run2["status"] == "SUCCESS"
    assert result_run2["store_id"] == result_run1["store_id"]
    assert result_run2["distributor_location_id"] == result_run1["distributor_location_id"]
    assert result_run2["product_id"] == result_run1["product_id"]
    assert result_run2["promotion_id"] == result_run1["promotion_id"]
    assert result_run2["promotion_version"] == result_run1["promotion_version"]
    assert result_run2["visit_id"] == result_run1["visit_id"]
    assert result_run2["sales_import_id"] == result_run1["sales_import_id"]
    assert result_run2["inventory_import_id"] == result_run1["inventory_import_id"]
    assert result_run2["shelf_before_media_id"] == result_run1["shelf_before_media_id"]
    assert result_run2["shelf_after_media_id"] == result_run1["shelf_after_media_id"]

    # Verify entity counts across API: No duplicate records created
    stores_res = await demo_client.get("/stores", headers=admin_headers)
    assert stores_res.status_code == 200
    assert len(stores_res.json()["items"]) == 1
    assert stores_res.json()["items"][0]["code"] == "STORE-101"

    locs_res = await demo_client.get("/locations", headers=admin_headers)
    assert locs_res.status_code == 200
    # Store backroom + distributor location
    loc_codes = [loc["code"] for loc in locs_res.json()["items"]]
    assert "LOC-DIST-01" in loc_codes
    assert "STORE-101-BACKROOM" in loc_codes

    prods_res = await demo_client.get("/products", headers=admin_headers)
    assert prods_res.status_code == 200
    assert len(prods_res.json()["items"]) == 1
    assert prods_res.json()["items"][0]["sku"] == "BEV-WAT-001"

    imports_res = await demo_client.get("/imports", headers=admin_headers)
    assert imports_res.status_code == 200
    items = imports_res.json()["items"]
    assert len(items) == 2
    for imp in items:
        assert imp["status"] == "COMMITTED"

    promos_res = await demo_client.get("/promotions", headers=admin_headers)
    assert promos_res.status_code == 200
    promos = promos_res.json()["items"]
    assert len(promos) == 1
    assert promos[0]["approved_policy"] is not None
    assert promos[0]["version"] == 2

    visits_res = await demo_client.get(f"/visits?store_id={result_run1['store_id']}", headers=admin_headers)
    assert visits_res.status_code == 200
    assert len(visits_res.json()["items"]) == 1

    # Verify media stability and valid states
    media_before = await demo_client.get(f"/media/{result_run1['shelf_before_media_id']}", headers=admin_headers)
    assert media_before.status_code == 200
    assert media_before.json()["status"] == "READY"
    assert media_before.json()["kind"] == "VISIT_BEFORE"

    media_after = await demo_client.get(f"/media/{result_run1['shelf_after_media_id']}", headers=admin_headers)
    assert media_after.status_code == 200
    assert media_after.json()["status"] == "READY"
    assert media_after.json()["kind"] == "VISIT_AFTER"


@pytest.mark.asyncio
async def test_ac30_seed_demo_different_data_isolation(demo_client: AsyncClient):
    """AC30: Demo seed operates with strict multi-tenant isolation and does not cross workspace boundaries."""
    from scripts.seed_demo.seed import seed_workspace

    ws_demo = uuid4()
    ws_custom = uuid4()

    await provision_demo_workspace(ws_demo)
    await provision_demo_workspace(ws_custom)

    demo_headers = {
        "Authorization": "Bearer demo-admin",
        "X-Workspace-Id": str(ws_demo),
    }
    custom_headers = {
        "Authorization": "Bearer demo-admin",
        "X-Workspace-Id": str(ws_custom),
    }

    # Seed demo workspace
    await seed_workspace(demo_client, ws_demo, demo_headers)

    # In custom workspace, create different entities
    custom_store_res = await demo_client.post(
        "/stores",
        json={
            "code": "CUSTOM-999",
            "name": "Custom Retail Outlet",
            "retailer": "Custom Retailer LLC",
            "region": "West",
            "format": "Convenience",
            "timezone": "America/Los_Angeles",
            "distributor_location_id": None,
        },
        headers={**custom_headers, "Idempotency-Key": f"custom-store-{uuid4()}"},
    )
    assert custom_store_res.status_code == 201

    custom_prod_res = await demo_client.post(
        "/products",
        json={
            "sku": "CUSTOM-SKU-999",
            "name": "Custom Snack Bar",
            "case_units": 12,
        },
        headers={**custom_headers, "Idempotency-Key": f"custom-prod-{uuid4()}"},
    )
    assert custom_prod_res.status_code == 201

    # Verify demo workspace does NOT see custom data
    demo_stores = await demo_client.get("/stores", headers=demo_headers)
    assert [s["code"] for s in demo_stores.json()["items"]] == ["STORE-101"]

    demo_prods = await demo_client.get("/products", headers=demo_headers)
    assert [p["sku"] for p in demo_prods.json()["items"]] == ["BEV-WAT-001"]

    # Verify custom workspace does NOT see demo data
    custom_stores = await demo_client.get("/stores", headers=custom_headers)
    assert [s["code"] for s in custom_stores.json()["items"]] == ["CUSTOM-999"]

    custom_prods = await demo_client.get("/products", headers=custom_headers)
    assert [p["sku"] for p in custom_prods.json()["items"]] == ["CUSTOM-SKU-999"]


@pytest.mark.asyncio
async def test_ac30_missing_manifest_raises_error(demo_client: AsyncClient, tmp_path: Path):
    """AC30: Missing manifest in target fixtures directory raises FileNotFoundError."""
    from scripts.seed_demo.seed import seed_workspace

    empty_dir = tmp_path / "empty_fixtures"
    empty_dir.mkdir()

    with pytest.raises(FileNotFoundError, match="Demo manifest not found"):
        await seed_workspace(
            demo_client,
            uuid4(),
            {"Authorization": "Bearer demo-admin"},
            fixtures_dir=empty_dir,
        )


def test_ac30_cli_parser():
    """Verify build_cli_parser constructs valid CLI flags."""
    from scripts.seed_demo.seed import build_cli_parser

    parser = build_cli_parser()
    args = parser.parse_args(["--workspace-id", "00000000-0000-0000-0000-000000000001"])
    assert args.workspace_id == "00000000-0000-0000-0000-000000000001"
    assert args.api_url == "http://127.0.0.1:8000"
    assert args.token == "demo-admin"


def test_ac30_integration_gate_app_runs_without_demo_fixtures():
    """T13 Integration Gate: The application and ordinary services run cleanly with fixtures/demo absent."""
    import shutil
    import tempfile

    fixtures_dir = Path(__file__).resolve().parent.parent.parent / "fixtures" / "demo"
    assert fixtures_dir.exists(), "fixtures/demo should exist prior to test"

    temp_backup = Path(tempfile.mkdtemp(prefix="demo_fixtures_bak_"))
    backup_target = temp_backup / "demo"

    # Move fixtures/demo physically aside
    shutil.move(str(fixtures_dir), str(backup_target))
    try:
        assert not fixtures_dir.exists(), "fixtures/demo must be absent during check"

        # Verify application main and services import and initialize cleanly
        import apps.api.main
        import apps.api.modules.catalog.service
        import apps.api.modules.imports.service
        import apps.api.modules.policies.service
        import apps.api.modules.verification.service
        import apps.api.modules.visits.service

        assert apps.api.main.app is not None
    finally:
        # Guarantee physical restoration of fixtures/demo
        shutil.move(str(backup_target), str(fixtures_dir))
        shutil.rmtree(temp_backup, ignore_errors=True)
        assert fixtures_dir.exists(), "fixtures/demo must be restored after check"
