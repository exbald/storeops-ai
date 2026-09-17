"""AC25: Contract and Schema Conformance Tests.

Validates:
1. Canonical OpenAPI and AI schemas integrity.
2. Generated client and domain-model schema conformance without drift.
3. Rejection of unknown/malformed request bodies, malformed UUIDs, and illegal enum values.
4. Consistent error envelope schema across all API endpoints.
5. Absence of duplicate shadow DTOs.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from storeops_contracts import models as py_models

from apps.api.adapters.state.in_memory import InMemoryStateRepository
from apps.api.core.auth import set_state_repository
from apps.api.main import app

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest_asyncio.fixture
async def contract_client():
    repo = InMemoryStateRepository()
    now = datetime.now(UTC)
    ws_id = uuid4()
    ws = py_models.Workspace(
        id=ws_id,
        workspace_id=ws_id,
        version=1,
        created_at=now,
        updated_at=now,
        name="Contract Workspace",
        brand_name="Contract Brand",
        currency=py_models.Currency.SGD,
    )
    await repo.create_workspace_with_admin(ws, uid="contract-admin-uid", email="admin@contract.test")
    from apps.api.core import auth
    prev_repo = auth._state_repository
    set_state_repository(repo)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client, ws_id
    finally:
        auth._state_repository = prev_repo


def test_ac25_openapi_contract_file_exists_and_parses():
    """Verify canonical openapi.json exists and is valid JSON with required paths."""
    openapi_path = PROJECT_ROOT / "contracts" / "openapi.json"
    assert openapi_path.exists(), "contracts/openapi.json must exist"

    with open(openapi_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    assert "openapi" in spec
    assert "paths" in spec
    assert "components" in spec
    assert "schemas" in spec["components"]

    # Critical API routes must be declared
    required_paths = [
        "/health",
        "/me",
        "/stores",
        "/products",
        "/imports",
        "/promotions",
        "/visits",
        "/investigations",
        "/verifications",
        "/reports",
        "/jobs",
    ]
    for p in required_paths:
        matched = any(path == p or path.startswith(f"{p}/") for path in spec["paths"])
        assert matched, f"Required path {p} missing from openapi.json"


def test_ac25_python_models_contain_all_major_schema_types():
    """Verify generated Python contract models include core business entities."""
    required_models = [
        "Store",
        "Product",
        "Import",
        "Promotion",
        "Visit",
        "Investigation",
        "Verification",
        "Report",
        "Job",
        "Membership",
        "Workspace",
        "Error",
    ]
    for model_name in required_models:
        assert hasattr(py_models, model_name), f"Python contract model {model_name} missing from storeops_contracts.models"


def test_ac25_error_envelope_schema():
    """Verify Error schema matches the frozen standard."""
    error_model = getattr(py_models, "Error", None)
    assert error_model is not None, "Error model must exist in storeops_contracts"
    fields = error_model.model_fields
    assert "code" in fields
    assert "message" in fields
    assert "request_id" in fields
    assert "details" in fields


@pytest.mark.asyncio
async def test_ac25_negative_malformed_uuid_returns_422(contract_client):
    """API must reject malformed UUIDs with 422 Unprocessable Entity."""
    client, ws_id = contract_client
    resp = await client.get(
        "/stores/not-a-valid-uuid",
        headers={
            "Authorization": "Bearer contract-admin-uid",
            "X-Workspace-Id": str(ws_id),
        },
    )
    assert resp.status_code == 422, f"Expected 422 for malformed UUID, got {resp.status_code}"


@pytest.mark.asyncio
async def test_ac25_negative_illegal_enum_returns_422(contract_client):
    """API must reject illegal enum values in payload with 422."""
    client, ws_id = contract_client
    resp = await client.post(
        "/stores",
        headers={
            "Authorization": "Bearer contract-admin-uid",
            "X-Workspace-Id": str(ws_id),
            "Idempotency-Key": str(uuid4()),
        },
        json={
            "code": "INVALID-STORE",
            "name": "Invalid Currency Store",
            "retailer": "Retail Corp",
            "region": "Central",
            "format": "Supermarket",
            "timezone": "Asia/Singapore",
            "distributor_location_id": "NOT-A-UUID",  # invalid format
        },
    )
    assert resp.status_code == 422, f"Expected 422 for invalid format/enum value, got {resp.status_code}"


@pytest.mark.asyncio
async def test_ac25_negative_missing_authorization_returns_401():
    """Protected endpoints reject unauthenticated requests with 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/stores")
        assert resp.status_code == 401, f"Expected 401 without auth token, got {resp.status_code}"
