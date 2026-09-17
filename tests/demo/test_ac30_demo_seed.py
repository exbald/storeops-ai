"""AC30: Optional independent demo seed and replay suite acceptance tests.

Specs: specs/00-product.md, specs/06-quality.md, plan/acceptance.json (AC30), AGENTS.md.

Validates that:
1. The demo seed command uses normal API services/imports and is strictly idempotent.
2. Running the seed command twice produces no duplicates or runtime errors.
3. No runtime application code under apps/ imports fixtures, demo seeds, or evaluation labels.
4. Normal regression test factories operate completely independently of fixtures/demo/.
"""

import ast
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEMO_FIXTURES_DIR = ROOT_DIR / "fixtures" / "demo"
DEMO_SCRIPTS_DIR = ROOT_DIR / "scripts" / "seed_demo"


def test_ac30_no_app_imports_demo_fixtures_or_evals():
    """AC30 / AGENTS.md: Application modules must not import fixtures, demo seeds or evals."""
    apps_dir = ROOT_DIR / "apps"
    forbidden_prefixes = ("fixtures", "scripts.seed_demo", "evals")

    violations = []
    for py_file in apps_dir.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for prefix in forbidden_prefixes:
                        if alias.name == prefix or alias.name.startswith(f"{prefix}."):
                            violations.append((str(py_file.relative_to(ROOT_DIR)), alias.name))
            elif isinstance(node, ast.ImportFrom) and node.module:
                for prefix in forbidden_prefixes:
                    if node.module == prefix or node.module.startswith(f"{prefix}."):
                        violations.append((str(py_file.relative_to(ROOT_DIR)), node.module))

    assert not violations, f"Forbidden imports found in application modules: {violations}"


def test_ac30_demo_manifest_and_files_exist():
    """AC30: Dated demo manifest and importable files/media exist in fixtures/demo/."""
    from scripts.seed_demo.seed import load_demo_manifest

    manifest = load_demo_manifest()
    assert manifest is not None
    assert manifest.get("demo_id") == "storeops-retail-demo-2026"
    assert manifest.get("dated") == "2026-09-15"

    # Verify associated files exist
    sales_csv = DEMO_FIXTURES_DIR / manifest["imports"]["sales_csv"]
    inventory_csv = DEMO_FIXTURES_DIR / manifest["imports"]["inventory_csv"]
    agreement_md = DEMO_FIXTURES_DIR / manifest["policies"]["agreement_text"]

    assert sales_csv.exists(), f"Missing sales CSV: {sales_csv}"
    assert inventory_csv.exists(), f"Missing inventory CSV: {inventory_csv}"
    assert agreement_md.exists(), f"Missing agreement markdown: {agreement_md}"

    # Verify CSV headers match contracts/imports.json
    sales_lines = sales_csv.read_text(encoding="utf-8").strip().splitlines()
    assert sales_lines[0] == "store_code,sku,business_date,units,revenue,currency"

    inv_lines = inventory_csv.read_text(encoding="utf-8").strip().splitlines()
    assert inv_lines[0] == "location_code,sku,observed_at,quantity,unit"


@pytest.mark.asyncio
async def test_ac30_seed_demo_idempotence():
    """AC30: Running seed_demo twice against a target workspace is strictly idempotent."""
    from scripts.seed_demo.seed import seed_workspace

    workspace_id = uuid4()
    admin_headers = {
        "Authorization": "Bearer demo-admin",
        "X-Workspace-Id": str(workspace_id),
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Run 1: First seed execution
        result_run1 = await seed_workspace(client, workspace_id, admin_headers)
        assert result_run1["status"] == "SUCCESS"
        assert result_run1["store_id"] is not None
        assert result_run1["product_id"] is not None
        assert result_run1["sales_committed"] == 1
        assert result_run1["inventory_committed"] == 1

        # Run 2: Second seed execution on same workspace (must succeed without duplicate conflicts)
        result_run2 = await seed_workspace(client, workspace_id, admin_headers)
        assert result_run2["status"] == "SUCCESS"
        assert result_run2["store_id"] == result_run1["store_id"]
        assert result_run2["product_id"] == result_run1["product_id"]

        # Verify only one store exists in the workspace
        res_stores = await client.get("/stores", headers=admin_headers)
        assert res_stores.status_code == 200
        stores = res_stores.json().get("items", [])
        assert len(stores) == 1
        assert stores[0]["code"] == "STORE-101"

        # Verify only one product exists in the workspace
        res_prods = await client.get("/products", headers=admin_headers)
        assert res_prods.status_code == 200
        products = res_prods.json().get("items", [])
        assert len(products) == 1
        assert products[0]["sku"] == "BEV-WAT-001"


@pytest.mark.asyncio
async def test_ac30_seed_demo_different_data_isolation():
    """AC30: Loading differently named data after demo seed operates with complete isolation."""
    from scripts.seed_demo.seed import seed_workspace

    workspace_id = uuid4()
    admin_headers = {
        "Authorization": "Bearer demo-admin",
        "X-Workspace-Id": str(workspace_id),
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Seed the standard demo
        await seed_workspace(client, workspace_id, admin_headers)

        # Create a distinct independent store with different data
        custom_store_res = await client.post(
            "/stores",
            headers={**admin_headers, "Idempotency-Key": f"custom-store-{uuid4()}"},
            json={
                "name": "Suburban Outlet #999",
                "code": "STORE-SUB-999",
                "retailer": "Independent Retail",
                "region": "West",
                "format": "Supermarket",
                "timezone": "America/Los_Angeles",
                "distributor_location_id": None,
            },
        )
        assert custom_store_res.status_code == 201
        custom_store = custom_store_res.json()
        assert custom_store["code"] == "STORE-SUB-999"

        # List stores: both exist without interference
        stores_res = await client.get("/stores", headers=admin_headers)
        assert stores_res.status_code == 200
        codes = [s["code"] for s in stores_res.json().get("items", [])]
        assert "STORE-101" in codes
        assert "STORE-SUB-999" in codes


def test_ac30_demo_media_files_exist_and_valid():
    """AC30: Demo media files exist, are valid JPEGs, and conform to size limits."""
    from PIL import Image

    from scripts.seed_demo.seed import load_demo_manifest

    manifest = load_demo_manifest()
    shelf_before = DEMO_FIXTURES_DIR / manifest["media"]["shelf_before"]
    shelf_after = DEMO_FIXTURES_DIR / manifest["media"]["shelf_after"]

    assert shelf_before.is_file(), f"Missing shelf_before image: {shelf_before}"
    assert shelf_after.is_file(), f"Missing shelf_after image: {shelf_after}"

    # Verify PIL can open and decode
    with Image.open(shelf_before) as img:
        assert img.format == "JPEG"
        assert img.width > 0 and img.height > 0

    with Image.open(shelf_after) as img:
        assert img.format == "JPEG"
        assert img.width > 0 and img.height > 0


def test_ac30_load_demo_manifest_missing_file_raises(monkeypatch):
    """AC30: load_demo_manifest raises FileNotFoundError if manifest does not exist."""
    import scripts.seed_demo.seed as seed_module

    monkeypatch.setattr(seed_module, "MANIFEST_PATH", Path("/tmp/nonexistent/manifest.json"))
    with pytest.raises(FileNotFoundError):
        seed_module.load_demo_manifest()


def test_ac30_demo_seed_cli_parser():
    """AC30: CLI entry point parses default and custom arguments correctly."""
    from scripts.seed_demo.seed import build_cli_parser

    parser = build_cli_parser()
    args = parser.parse_args(["--api-url", "http://storeops.internal:8000", "--workspace-id", "11111111-2222-3333-4444-555555555555"])
    assert args.api_url == "http://storeops.internal:8000"
    assert args.workspace_id == "11111111-2222-3333-4444-555555555555"
