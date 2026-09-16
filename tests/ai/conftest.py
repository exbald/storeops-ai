"""Test fixtures and mock factories for AI investigation and model gateway tests."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from storeops_contracts.models import (
    Currency,
    LocationType,
    PeerSales,
    SalesContext,
    StockContext,
    StockItem,
    Unit,
    Visit1,
    VisitHistoryContext,
)


@pytest.fixture
def workspace_id() -> str:
    return str(uuid4())


@pytest.fixture
def other_workspace_id() -> str:
    return str(uuid4())


@pytest.fixture
def store_id() -> UUID:
    return uuid4()


@pytest.fixture
def snapshot_id() -> UUID:
    return uuid4()


@pytest.fixture
def product_ids() -> list[UUID]:
    return [uuid4(), uuid4(), uuid4()]


@pytest.fixture
def media_id() -> UUID:
    return uuid4()


@pytest.fixture
def rule_id() -> UUID:
    return uuid4()


@pytest.fixture
def sample_sales_context(
    store_id: UUID, snapshot_id: UUID, product_ids: list[UUID]
) -> SalesContext:
    from datetime import date

    peer_id = uuid4()
    return SalesContext(
        snapshot_id=snapshot_id,
        store_id=store_id,
        catalog_product_ids=product_ids,
        prior_start=date(2026, 8, 1),
        prior_end=date(2026, 8, 7),
        current_start=date(2026, 8, 8),
        current_end=date(2026, 8, 14),
        complete=True,
        prior_units=100,
        current_units=80,
        prior_revenue="1000.00",
        current_revenue="800.00",
        currency=Currency.USD,
        eligible_peers=[
            PeerSales(
                store_id=peer_id,
                complete=True,
                prior_units=50,
                current_units=60,
                retailer="RetailCo",
                region="West",
                format="Supercenter",
                currency=Currency.USD,
                promotion_id=uuid4(),
                evidence_ids=[uuid4()],
            )
        ],
        gaps=[],
        evidence_ids=[uuid4(), uuid4()],
    )


@pytest.fixture
def sample_stock_context(
    store_id: UUID, snapshot_id: UUID, product_ids: list[UUID]
) -> StockContext:
    from storeops_contracts.models import Freshness2

    evidence_id = uuid4()
    return StockContext(
        snapshot_id=snapshot_id,
        store_id=store_id,
        items=[
            StockItem(
                product_id=product_ids[0],
                location_id=uuid4(),
                location_type=LocationType.BACKROOM,
                quantity=20,
                unit=Unit.UNIT,
                units_normalized=20,
                observed_at=datetime.now(UTC),
                freshness=Freshness2.CURRENT,
                evidence_id=evidence_id,
            )
        ],
        missing=[],
    )


@pytest.fixture
def sample_visit_history(store_id: UUID, snapshot_id: UUID) -> VisitHistoryContext:
    return VisitHistoryContext(
        snapshot_id=snapshot_id,
        store_id=store_id,
        visits=[
            Visit1(
                visit_id=uuid4(),
                visited_at=datetime.now(UTC),
                notes="Previous visit showed partial display setup.",
                evidence_ids=[uuid4()],
            )
        ],
    )
