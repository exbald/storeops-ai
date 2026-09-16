from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from storeops_contracts.models import Currency, Store

from apps.api.analytics.metrics import compute_peer_gap_metrics


def _make_store(
    ws_id, code, retailer="FairPrice", region="Central", fmt="Hypermarket", active=True
):
    return Store(
        id=uuid4(),
        workspace_id=ws_id,
        version=1,
        created_at="2026-09-01T00:00:00Z",
        updated_at="2026-09-01T00:00:00Z",
        code=code,
        name=f"Store {code}",
        retailer=retailer,
        region=region,
        format=fmt,
        currency=Currency.SGD,
        timezone="Asia/Singapore",
        active=active,
        distributor_location_id=None,
        backroom_location_id=uuid4(),
    )


def _generate_window_data(store_id, units_per_day, rev_per_day):
    """Generate 7 days of prior (2026-09-01 to 2026-09-07) and 7 days of current (2026-09-08 to 2026-09-14)."""
    rows = []
    # Prior window
    for day in range(1, 8):
        rows.append(
            {
                "store_id": store_id,
                "sku": "SKU-COKE-330",
                "business_date": f"2026-09-{day:02d}",
                "units": units_per_day[0],
                "revenue": Decimal(str(rev_per_day[0])),
                "currency": "SGD",
            }
        )
    # Current window
    for day in range(8, 15):
        rows.append(
            {
                "store_id": store_id,
                "sku": "SKU-COKE-330",
                "business_date": f"2026-09-{day:02d}",
                "units": units_per_day[1],
                "revenue": Decimal(str(rev_per_day[1])),
                "currency": "SGD",
            }
        )
    return rows


@pytest.mark.asyncio
async def test_ac14_deterministic_peer_gap_math():
    ws_id = uuid4()
    as_of = date(2026, 9, 15)

    focal = _make_store(ws_id, "FOCAL")
    peer1 = _make_store(ws_id, "PEER1")
    peer2 = _make_store(ws_id, "PEER2")
    peer3 = _make_store(ws_id, "PEER3")
    # Ineligible peer due to mismatched region
    peer_ineligible = _make_store(ws_id, "PEER_EAST", region="East")

    all_stores = [focal, peer1, peer2, peer3, peer_ineligible]

    # Focal store: prior 10/day ($30/day), current 8/day ($24/day)
    # Prior units = 70, rev = 210.00. Current units = 56, rev = 168.00.
    focal_data = _generate_window_data(focal.id, (10, 8), (30.00, 24.00))

    # Peer 1: prior 10/day (70), current 12/day (84)
    peer1_data = _generate_window_data(peer1.id, (10, 12), (30.00, 36.00))

    # Peer 2: prior 20/day (140), current 22/day (154)
    peer2_data = _generate_window_data(peer2.id, (20, 22), (60.00, 66.00))

    # Peer 3: prior 30/day (210), current 36/day (252)
    peer3_data = _generate_window_data(peer3.id, (30, 36), (90.00, 108.00))

    # Ineligible peer
    peer_ineligible_data = _generate_window_data(
        peer_ineligible.id, (100, 200), (300.00, 600.00)
    )

    data_by_store = {
        focal.id: focal_data,
        peer1.id: peer1_data,
        peer2.id: peer2_data,
        peer3.id: peer3_data,
        peer_ineligible.id: peer_ineligible_data,
    }

    async def sales_fetcher(store_id, start, end):
        store_rows = data_by_store.get(store_id, [])
        return [r for r in store_rows if start <= r["business_date"] <= end]

    metrics = await compute_peer_gap_metrics(
        store=focal,
        all_stores=all_stores,
        as_of_date=as_of,
        sales_fetcher=sales_fetcher,
    )

    # 1. Verification of focal store sales_delta:
    # 56 / 70 - 1 = -0.2
    assert metrics.sales_delta == "-0.2"

    # 2. Peer cohort check: peer_ineligible must NOT be included
    assert set(metrics.peer_store_ids) == {peer1.id, peer2.id, peer3.id}
    assert peer_ineligible.id not in metrics.peer_store_ids
    assert focal.id not in metrics.peer_store_ids

    # 3. peer_growth check:
    # sum_curr = 84 + 154 + 252 = 490
    # sum_prior = 70 + 140 + 210 = 420
    # peer_growth = 490 / 420 - 1 = 1/6 ~= 0.1666666...
    assert metrics.peer_growth is not None
    assert metrics.peer_growth.startswith("0.16666")

    # 4. expected_units check:
    # 70 * (1 + 1/6) = 490 / 6 = 81.66666...
    assert metrics.expected_units is not None
    assert metrics.expected_units.startswith("81.6666")

    # 5. opportunity_proxy check:
    # (81.6666... - 56) * (210 / 70) = 25.6666... * 3 = 77.00
    assert metrics.opportunity_proxy == "77.00"
    assert len(metrics.null_reasons) == 0


@pytest.mark.asyncio
async def test_ac13_insufficient_peers_and_missing_window():
    ws_id = uuid4()
    as_of = date(2026, 9, 15)

    focal = _make_store(ws_id, "FOCAL")
    peer1 = _make_store(ws_id, "PEER1")
    peer2 = _make_store(ws_id, "PEER2")
    # Only 2 peers -> less than required 3

    all_stores = [focal, peer1, peer2]
    focal_data = _generate_window_data(focal.id, (10, 8), (30.00, 24.00))
    peer1_data = _generate_window_data(peer1.id, (10, 12), (30.00, 36.00))
    peer2_data = _generate_window_data(peer2.id, (20, 22), (60.00, 66.00))

    data_by_store = {
        focal.id: focal_data,
        peer1.id: peer1_data,
        peer2.id: peer2_data,
    }

    async def sales_fetcher(store_id, start, end):
        store_rows = data_by_store.get(store_id, [])
        return [r for r in store_rows if start <= r["business_date"] <= end]

    metrics = await compute_peer_gap_metrics(
        store=focal,
        all_stores=all_stores,
        as_of_date=as_of,
        sales_fetcher=sales_fetcher,
    )

    # Focal metrics available
    assert metrics.sales_delta == "-0.2"

    # Peer metrics null due to fewer than 3 peers
    assert metrics.peer_growth is None
    assert metrics.expected_units is None
    assert metrics.opportunity_proxy is None
    assert any("Insufficient eligible peers" in r.root for r in metrics.null_reasons)


@pytest.mark.asyncio
async def test_ac13_store_health_freshness(client, data_setup):
    rep_headers = data_setup["rep_headers"]
    store_1 = data_setup["store_1"]

    # 1. Initial health before any data imported -> Freshness is MISSING
    res = await client.get(f"/stores/{store_1.id}/health", headers=rep_headers)
    assert res.status_code == 200
    health = res.json()
    assert health["freshness"] == "MISSING"
    assert any("Missing sales history" in r for r in health["readiness"])
    assert health["metrics"]["sales_delta"] is None
