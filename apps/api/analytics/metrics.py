from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from storeops_contracts.models import (
    Currency,
    FormulaVersion,
    Metrics,
    NullReason,
    Store,
)


def compute_date_windows(as_of_date: date) -> tuple[date, date, date, date]:
    """Compute store commercial windows for reference date D.

    Current window: D-7 through D-1
    Prior window: D-14 through D-8
    """
    current_start = as_of_date - timedelta(days=7)
    current_end = as_of_date - timedelta(days=1)
    prior_start = as_of_date - timedelta(days=14)
    prior_end = as_of_date - timedelta(days=8)
    return prior_start, prior_end, current_start, current_end


def format_decimal(d: Decimal | None) -> str | None:
    if d is None:
        return None
    # Normalize trailing exponent or zero representation while maintaining decimal string
    s = format(d, "f")
    # If s has trailing decimal zeros, clean them up or leave exact representation
    # Pattern: ^-?\d+(\.\d+)?$
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


async def compute_peer_gap_metrics(
    store: Store,
    all_stores: list[Store],
    as_of_date: date,
    sales_fetcher: Any,  # async callable: (store_id: UUID, start: str, end: str) -> list[dict]
) -> Metrics:
    prior_start, prior_end, current_start, current_end = compute_date_windows(
        as_of_date
    )
    null_reasons: list[NullReason] = []

    # 1. Fetch focal store sales for both windows
    focal_prior_rows = await sales_fetcher(store.id, str(prior_start), str(prior_end))
    focal_current_rows = await sales_fetcher(
        store.id, str(current_start), str(current_end)
    )

    # Check complete 7-day coverage for focal store
    # Known limitation / deferral: specs/05-ai.md:50-51 specifies "complete product/date coverage".
    # For slice T03, coverage checks distinct calendar dates across all SKUs.
    # Per-product coverage matrix validation is deferred pending T04.
    prior_days = {row["business_date"] for row in focal_prior_rows}
    current_days = {row["business_date"] for row in focal_current_rows}

    focal_prior_complete = len(prior_days) >= 7
    focal_current_complete = len(current_days) >= 7

    prior_units = sum(int(row["units"]) for row in focal_prior_rows)
    current_units = sum(int(row["units"]) for row in focal_current_rows)
    prior_revenue = sum(Decimal(str(row["revenue"])) for row in focal_prior_rows)

    sales_delta: str | None = None
    if not focal_prior_complete or not focal_current_complete:
        null_reasons.append(
            NullReason(
                root=f"Focal store incomplete window coverage (prior {len(prior_days)}/7 days, current {len(current_days)}/7 days)"
            )
        )
    elif prior_units == 0:
        null_reasons.append(
            NullReason(root="Focal store has zero sales units in prior window")
        )
    else:
        # sales_delta = current_units / prior_units - 1
        delta_dec = (Decimal(current_units) / Decimal(prior_units)) - Decimal(1)
        sales_delta = format_decimal(delta_dec)

    # 2. Identify and filter peer cohort
    # Peers must share workspace, currency, retailer, region, format, and complete windows.
    # Known limitation / deferral: specs/05-ai.md:55-56 specifies peer cohorts sharing "promotion".
    # The Store contract model (contracts/openapi.json) does not define a promotion field.
    # Promotion matching is deferred pending T04 (vendor agreement policies).
    candidate_peers = [
        p
        for p in all_stores
        if p.id != store.id
        and p.active is True
        and p.workspace_id == store.workspace_id
        and p.currency == store.currency
        and p.retailer == store.retailer
        and p.region == store.region
        and p.format == store.format
    ]

    eligible_peers: list[tuple[Store, int, int]] = []
    peer_store_ids: list[UUID] = []

    for peer in candidate_peers:
        p_prior = await sales_fetcher(peer.id, str(prior_start), str(prior_end))
        p_curr = await sales_fetcher(peer.id, str(current_start), str(current_end))

        p_prior_days = {r["business_date"] for r in p_prior}
        p_curr_days = {r["business_date"] for r in p_curr}

        if len(p_prior_days) >= 7 and len(p_curr_days) >= 7:
            p_prior_u = sum(int(r["units"]) for r in p_prior)
            p_curr_u = sum(int(r["units"]) for r in p_curr)
            if p_prior_u > 0:
                eligible_peers.append((peer, p_prior_u, p_curr_u))
                peer_store_ids.append(peer.id)

    peer_growth: str | None = None
    expected_units: str | None = None
    opportunity_proxy: str | None = None

    if len(eligible_peers) < 3:
        null_reasons.append(
            NullReason(
                root=f"Insufficient eligible peers in cohort: found {len(eligible_peers)} (minimum 3 required)"
            )
        )
    elif not focal_prior_complete or not focal_current_complete or prior_units == 0:
        null_reasons.append(
            NullReason(
                root="Cannot compute peer metrics due to incomplete focal store prerequisites"
            )
        )
    else:
        # peer_growth = sum(current_peer_units) / sum(prior_peer_units) - 1
        sum_peer_curr = sum(p[2] for p in eligible_peers)
        sum_peer_prior = sum(p[1] for p in eligible_peers)

        if sum_peer_prior == 0:
            null_reasons.append(NullReason(root="Sum of prior peer units is zero"))
        else:
            pg_dec = (Decimal(sum_peer_curr) / Decimal(sum_peer_prior)) - Decimal(1)
            peer_growth = format_decimal(pg_dec)

            # expected_units = prior_store_units * (1 + peer_growth)
            exp_units_dec = Decimal(prior_units) * (Decimal(1) + pg_dec)
            expected_units = format_decimal(exp_units_dec)

            # opportunity_proxy = max(0, expected_units - current_store_units) * (prior_store_revenue / prior_store_units)
            # rounded once to 2 decimals with HALF_UP
            unit_gap = max(Decimal(0), exp_units_dec - Decimal(current_units))
            unit_price = prior_revenue / Decimal(prior_units)
            opp_dec = (unit_gap * unit_price).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            opportunity_proxy = format(opp_dec, ".2f")

    currency_enum = (
        Currency(store.currency.value)
        if hasattr(store.currency, "value")
        else Currency(str(store.currency))
    )

    return Metrics(
        sales_delta=sales_delta,
        peer_growth=peer_growth,
        expected_units=expected_units,
        opportunity_proxy=opportunity_proxy,
        currency=currency_enum,
        prior_start=prior_start,
        prior_end=prior_end,
        current_start=current_start,
        current_end=current_end,
        peer_store_ids=peer_store_ids,
        null_reasons=null_reasons,
        formula_version=FormulaVersion.peer_gap_v1,
        evidence_ids=[],
    )
