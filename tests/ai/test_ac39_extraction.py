"""AC39 tests for multimodal extraction workflows and peer_gap_v1 metrics."""

from datetime import date
from uuid import uuid4

import pytest
from storeops_contracts.models import (
    Currency,
    FormulaVersion,
    PeerSales,
    SalesContext,
)

from apps.api.ai.extract import (
    calculate_metrics_from_sales_context,
    extract_image_observations,
    extract_merchandising_policy,
)
from apps.api.ai.gateway import DeterministicModelGateway
from apps.api.ai.schemas import (
    Detection,
    ExtractedRule,
    ImageObservation,
    PolicyExtraction,
)


@pytest.mark.asyncio
async def test_extract_image_observations():
    gateway = DeterministicModelGateway()
    media_id = uuid4()
    p_id = uuid4()

    mock_obs = ImageObservation(
        media_id=media_id,
        zone_id="shelf-main",
        zone_kind="SHELF",
        quality="CLEAR",
        coverage="FULL",
        occluded=False,
        detections=[
            Detection(
                product_id=p_id,
                view="FRONT",
                box=[100, 100, 400, 400],
                identity="CLEAR",
                label="Product 1",
            )
        ],
        display="UNKNOWN",
        limitations=[],
    )
    gateway.register_response(ImageObservation, mock_obs)

    result = await extract_image_observations(
        gateway=gateway,
        image_bytes=b"fake-image-bytes",
        media_id=media_id,
        zone_id="shelf-main",
        zone_kind="SHELF",
        catalog_product_ids=[p_id],
    )
    assert result.media_id == media_id
    assert len(result.detections) == 1
    assert result.detections[0].view == "FRONT"
    assert gateway.call_history[0]["images_count"] == 1


@pytest.mark.asyncio
async def test_extract_merchandising_policy():
    gateway = DeterministicModelGateway()
    p_id = uuid4()
    s_id = uuid4()
    agreement_media_id = uuid4()

    mock_extraction = PolicyExtraction(
        media_id=agreement_media_id,
        rules=[
            ExtractedRule(
                kind="MIN_FACINGS",
                product_id=p_id,
                zone_kind="SHELF",
                min_facings=4,
                source_page=1,
                source_quote="Minimum of 4 facings required at all times.",
            )
        ],
        gaps=[],
    )
    gateway.register_response(PolicyExtraction, mock_extraction)

    result = await extract_merchandising_policy(
        gateway=gateway,
        pdf_bytes=b"fake-pdf-bytes",
        media_id=agreement_media_id,
        catalog_product_ids=[p_id],
        store_ids=[s_id],
    )
    assert len(result.rules) == 1
    assert result.rules[0].min_facings == 4
    assert result.rules[0].source_page == 1
    assert gateway.call_history[0]["pdfs_count"] == 1


def test_calculate_metrics_peer_gap_v1_deterministic_math():
    """Verify Decimal peer_gap_v1 math and HALF_UP rounding per specs/05-ai.md:48-65."""
    ev_id = uuid4()
    # 3 complete eligible peers
    peers = [
        PeerSales(
            store_id=uuid4(),
            current_units=120,
            prior_units=100,
            complete=True,
            retailer="RetailCo",
            region="West",
            format="Supercenter",
            currency=Currency.USD,
            promotion_id=uuid4(),
            evidence_ids=[uuid4()],
        ),
        PeerSales(
            store_id=uuid4(),
            current_units=110,
            prior_units=100,
            complete=True,
            retailer="RetailCo",
            region="West",
            format="Supercenter",
            currency=Currency.USD,
            promotion_id=uuid4(),
            evidence_ids=[uuid4()],
        ),
        PeerSales(
            store_id=uuid4(),
            current_units=130,
            prior_units=100,
            complete=True,
            retailer="RetailCo",
            region="West",
            format="Supercenter",
            currency=Currency.USD,
            promotion_id=uuid4(),
            evidence_ids=[uuid4()],
        ),
    ]
    # Peer sum: current = 360, prior = 300 -> peer_growth = 360/300 - 1 = 0.2
    # Store: prior = 100, current = 80 -> store_growth = 80/100 - 1 = -0.2
    # expected_units = 100 * (1 + 0.2) = 120
    # unit_gap = 120 - 80 = 40
    # prior_revenue = 500, avg_price = 500 / 100 = 5.0
    # opportunity_proxy = 40 * 5.0 = 200.00
    sales_ctx = SalesContext(
        store_id=uuid4(),
        snapshot_id=uuid4(),
        catalog_product_ids=[uuid4()],
        prior_start=date(2026, 8, 1),
        prior_end=date(2026, 8, 7),
        current_start=date(2026, 8, 8),
        current_end=date(2026, 8, 14),
        complete=True,
        current_units=80,
        prior_units=100,
        prior_revenue="500.00",
        current_revenue="400.00",
        currency=Currency.USD,
        eligible_peers=peers,
        gaps=[],
        evidence_ids=[ev_id],
    )

    metrics = calculate_metrics_from_sales_context(
        sales_ctx=sales_ctx,
        currency=Currency.USD,
        as_of_date=date(2026, 9, 15),
    )

    assert metrics.formula_version == FormulaVersion.peer_gap_v1
    assert metrics.sales_delta == "-0.2"
    assert metrics.peer_growth == "0.2"
    assert metrics.expected_units == "120"
    assert metrics.opportunity_proxy == "200.00"
    assert len(metrics.null_reasons) == 0
    assert len(metrics.peer_store_ids) == 3


def test_calculate_metrics_insufficient_peers_returns_null_reasons():
    """When fewer than 3 peers are eligible, return INSUFFICIENT_PEERS null reason."""
    ev_id = uuid4()
    peers = [
        PeerSales(
            store_id=uuid4(),
            current_units=120,
            prior_units=100,
            complete=True,
            retailer="RetailCo",
            region="West",
            format="Supercenter",
            currency=Currency.USD,
            promotion_id=uuid4(),
            evidence_ids=[uuid4()],
        )
    ]
    sales_ctx = SalesContext(
        store_id=uuid4(),
        snapshot_id=uuid4(),
        catalog_product_ids=[uuid4()],
        prior_start=date(2026, 8, 1),
        prior_end=date(2026, 8, 7),
        current_start=date(2026, 8, 8),
        current_end=date(2026, 8, 14),
        complete=True,
        current_units=80,
        prior_units=100,
        prior_revenue="500.00",
        current_revenue="400.00",
        currency=Currency.USD,
        eligible_peers=peers,
        gaps=[],
        evidence_ids=[ev_id],
    )

    metrics = calculate_metrics_from_sales_context(sales_ctx=sales_ctx)
    assert any(nr.root == "INSUFFICIENT_PEERS" for nr in metrics.null_reasons)
    assert metrics.peer_growth is None
    assert metrics.expected_units is None
    assert metrics.opportunity_proxy is None
    assert metrics.sales_delta == "-0.2"
