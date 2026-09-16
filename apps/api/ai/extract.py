"""Structured extraction workflows for shelf images, vendor agreement PDFs, and peer gap metrics."""

import logging
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from storeops_contracts.models import (
    Currency,
    FormulaVersion,
    Metrics,
    NullReason,
    SalesContext,
)

from apps.api.ai.prompts import (
    IMAGE_INSPECTION_PROMPT,
    IMAGE_INSPECTION_SYSTEM_INSTRUCTION,
    POLICY_EXTRACTION_PROMPT,
    POLICY_EXTRACTION_SYSTEM_INSTRUCTION,
)
from apps.api.ai.schemas import ImageObservation, PolicyExtraction
from apps.api.ports.model import ModelGateway

logger = logging.getLogger(__name__)


async def extract_image_observations(
    gateway: ModelGateway,
    image_bytes: bytes,
    media_id: UUID,
    zone_id: str,
    zone_kind: str = "SHELF",
    catalog_product_ids: list[UUID] | None = None,
) -> ImageObservation:
    """Extract structured ImageObservation from image bytes conforming to ai-output.schema.json."""
    prompt = (
        f"<system_instruction>\n{IMAGE_INSPECTION_SYSTEM_INSTRUCTION}\n</system_instruction>\n\n"
        + IMAGE_INSPECTION_PROMPT.format(
            media_id=media_id,
            zone_id=zone_id,
            zone_kind=zone_kind,
            catalog_products=[str(pid) for pid in (catalog_product_ids or [])],
        )
    )
    return await gateway.generate_structured(
        prompt=prompt,
        response_schema=ImageObservation,
        images=[image_bytes],
    )


async def extract_merchandising_policy(
    gateway: ModelGateway,
    pdf_bytes: bytes,
    media_id: UUID,
    catalog_product_ids: list[UUID],
    store_ids: list[UUID] | None = None,
) -> PolicyExtraction:
    """Extract structured PolicyExtraction from PDF bytes conforming to ai-output.schema.json."""
    prompt = (
        f"<system_instruction>\n{POLICY_EXTRACTION_SYSTEM_INSTRUCTION}\n</system_instruction>\n\n"
        + POLICY_EXTRACTION_PROMPT.format(
            media_id=media_id,
            catalog_products=[str(pid) for pid in catalog_product_ids],
            store_ids=[str(sid) for sid in (store_ids or [])],
        )
    )
    return await gateway.generate_structured(
        prompt=prompt,
        response_schema=PolicyExtraction,
        pdfs=[pdf_bytes],
    )


def calculate_metrics_from_sales_context(
    sales_ctx: SalesContext,
    currency: Currency = Currency.USD,
    as_of_date: date | None = None,
) -> Metrics:
    """Calculate deterministic peer_gap_v1 metrics from SalesContext per specs/05-ai.md:48-65."""
    ref_date = as_of_date or datetime.now(UTC).date()
    null_reasons: list[NullReason] = []
    peer_store_ids: list[UUID] = []

    # 1. Store growth
    sales_delta_str: str | None = None
    store_growth: Decimal | None = None
    if sales_ctx.prior_units and sales_ctx.prior_units > 0:
        curr_d = Decimal(str(sales_ctx.current_units))
        prior_d = Decimal(str(sales_ctx.prior_units))
        store_growth = (curr_d - prior_d) / prior_d
        sales_delta_str = format(store_growth, "f").rstrip("0").rstrip(".")
        if sales_delta_str == "-0":
            sales_delta_str = "0"
    else:
        null_reasons.append(NullReason(root="MISSING_PRIOR_WINDOW"))

    # 2. Peer growth
    # Peers must be complete and have positive prior units
    eligible = [
        p
        for p in (sales_ctx.eligible_peers or [])
        if p.complete and p.prior_units and p.prior_units > 0
    ]
    peer_store_ids = [p.store_id for p in eligible]

    peer_growth_str: str | None = None
    expected_units_str: str | None = None
    opportunity_proxy_str: str | None = None

    if len(eligible) < 3:
        null_reasons.append(NullReason(root="INSUFFICIENT_PEERS"))
    else:
        sum_curr = sum(Decimal(str(p.current_units)) for p in eligible)
        sum_prior = sum(Decimal(str(p.prior_units)) for p in eligible)
        if sum_prior > Decimal(0):
            peer_growth = (sum_curr / sum_prior) - Decimal(1)
            peer_growth_str = format(peer_growth, "f").rstrip("0").rstrip(".")
            if peer_growth_str == "-0":
                peer_growth_str = "0"

            # expected_units = prior_store_units * (1 + peer_growth)
            if sales_ctx.prior_units and sales_ctx.prior_units > 0:
                expected_units = Decimal(str(sales_ctx.prior_units)) * (
                    Decimal(1) + peer_growth
                )
                expected_units_str = format(expected_units, "f").rstrip("0").rstrip(".")
                if expected_units_str == "-0":
                    expected_units_str = "0"

                # opportunity_proxy = max(0, expected_units - current_store_units) * (prior_store_revenue / prior_store_units)
                # rounded once to 2 decimals with HALF_UP
                unit_gap = max(
                    Decimal(0),
                    expected_units - Decimal(str(sales_ctx.current_units)),
                )
                # If prior revenue available, compute opportunity proxy
                if (
                    hasattr(sales_ctx, "prior_revenue")
                    and sales_ctx.prior_revenue
                    and sales_ctx.prior_units > 0
                ):
                    avg_price = Decimal(str(sales_ctx.prior_revenue)) / Decimal(
                        str(sales_ctx.prior_units)
                    )
                    opp = (unit_gap * avg_price).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    opportunity_proxy_str = str(opp)
                else:
                    opp = unit_gap.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    opportunity_proxy_str = str(opp)

    return Metrics(
        sales_delta=sales_delta_str,
        peer_growth=peer_growth_str,
        expected_units=expected_units_str,
        opportunity_proxy=opportunity_proxy_str,
        currency=currency,
        prior_start=ref_date,
        prior_end=ref_date,
        current_start=ref_date,
        current_end=ref_date,
        peer_store_ids=peer_store_ids,
        null_reasons=null_reasons,
        formula_version=FormulaVersion.peer_gap_v1,
        evidence_ids=list(sales_ctx.evidence_ids),
    )
