"""Pytest fixtures for Web Management (T05 / AC-38)."""

import pytest


@pytest.fixture
def mock_api_double_evidence():
    """Returns sample contract-shaped responses for management screen doubles."""
    return {
        "workspace_id": "11111111-1111-1111-1111-111111111111",
        "store": {
            "id": "22222222-2222-2222-2222-222222222222",
            "workspace_id": "11111111-1111-1111-1111-111111111111",
            "code": "STR-001",
            "name": "Downtown Central",
            "retailer": "FairPrice",
            "format": "SUPERMARKET",
            "region": "Central",
            "timezone": "Asia/Singapore",
            "distributor_location_id": None,
            "active": True,
            "version": 1,
            "created_at": "2026-09-16T12:00:00Z",
            "updated_at": "2026-09-16T12:00:00Z",
        },
        "product": {
            "id": "33333333-3333-3333-3333-333333333333",
            "workspace_id": "11111111-1111-1111-1111-111111111111",
            "sku": "COKE-500",
            "name": "Coca-Cola 500ml",
            "case_units": 24,
            "reference_media_ids": [],
            "active": True,
            "version": 1,
            "created_at": "2026-09-16T12:00:00Z",
            "updated_at": "2026-09-16T12:00:00Z",
        },
        "import_record": {
            "id": "44444444-4444-4444-4444-444444444444",
            "workspace_id": "11111111-1111-1111-1111-111111111111",
            "kind": "SALES_DAILY",
            "media_id": "55555555-5555-5555-5555-555555555555",
            "status": "STAGED",
            "row_count": 150,
            "error_count": 1,
            "errors": [
                {
                    "row_number": 42,
                    "code": "UNKNOWN_SKU",
                    "message": "SKU UNKNOWN-999 is not in catalog",
                    "raw_line": "2026-09-15,STR-001,UNKNOWN-999,10,15.00,SGD",
                }
            ],
            "batch_id": None,
            "committed_at": None,
            "source_sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "version": 1,
            "created_at": "2026-09-16T12:00:00Z",
            "updated_at": "2026-09-16T12:00:00Z",
        },
    }
