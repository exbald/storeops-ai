"""Deterministic predicates for rule evaluation against image observations."""

from typing import Any
from uuid import UUID

from storeops_contracts.models import (
    Kind5,
    Result,
    Result1,
    Rule,
)

from apps.api.ai.schemas import ImageObservation


def evaluate_rule_observation(
    rule: Rule,
    observations: list[ImageObservation],
    matching_evidence_ids: list[UUID],
) -> tuple[Result, list[UUID], str]:
    """Evaluate a single frozen policy rule against post-action image observations.

    Returns:
        (result, evidence_ids, explanation)
    """
    # Find observations matching rule zone
    relevant_obs = [
        obs
        for obs in observations
        if (rule.zone_id is None or obs.zone_id == rule.zone_id)
        and (rule.zone_kind is None or obs.zone_kind == rule.zone_kind.value)
    ]

    if not relevant_obs:
        return (
            Result.UNKNOWN,
            matching_evidence_ids,
            f"No post-action image observation available for zone '{rule.zone_id or rule.zone_kind}'.",
        )

    # If any matching observation is unusable or occluded, yield UNKNOWN
    for obs in relevant_obs:
        if obs.quality == "UNUSABLE":
            return (
                Result.UNKNOWN,
                matching_evidence_ids,
                f"Image observation for zone '{obs.zone_id}' is UNUSABLE ({', '.join(obs.limitations) or 'quality degraded'}).",
            )
        if obs.occluded:
            return (
                Result.UNKNOWN,
                matching_evidence_ids,
                f"Zone '{obs.zone_id}' is occluded; cannot verify compliance.",
            )

    if rule.kind == Kind5.MIN_FACINGS:
        required_facings = rule.min_facings or 1
        total_compliant_facings = 0
        has_ambiguous = False
        has_partial = False

        for obs in relevant_obs:
            if obs.coverage in ("PARTIAL", "UNKNOWN"):
                has_partial = True

            for det in obs.detections:
                if det.product_id == rule.product_id:
                    if det.identity == "AMBIGUOUS":
                        has_ambiguous = True
                    elif det.view == "FRONT":
                        total_compliant_facings += 1

        if total_compliant_facings >= required_facings:
            return (
                Result.PASS,
                matching_evidence_ids,
                f"Observed {total_compliant_facings} compliant front facings (required: {required_facings}).",
            )

        if has_ambiguous or has_partial:
            return (
                Result.UNKNOWN,
                matching_evidence_ids,
                f"Found {total_compliant_facings}/{required_facings} facings, but partial coverage or ambiguous detections exist.",
            )

        return (
            Result.FAIL,
            matching_evidence_ids,
            f"Observed only {total_compliant_facings} compliant front facings (required: {required_facings}).",
        )

    if rule.kind == Kind5.REQUIRED_PRODUCT:
        total_present = 0
        has_ambiguous = False
        has_partial = False

        for obs in relevant_obs:
            if obs.coverage in ("PARTIAL", "UNKNOWN"):
                has_partial = True

            for det in obs.detections:
                if det.product_id == rule.product_id:
                    if det.identity == "AMBIGUOUS":
                        has_ambiguous = True
                    else:
                        total_present += 1

        if total_present >= 1:
            return (
                Result.PASS,
                matching_evidence_ids,
                f"Required product {rule.product_id} is present ({total_present} detections).",
            )

        if has_ambiguous or has_partial:
            return (
                Result.UNKNOWN,
                matching_evidence_ids,
                f"Product {rule.product_id} not confirmed due to partial coverage or ambiguous detection.",
            )

        return (
            Result.FAIL,
            matching_evidence_ids,
            f"Required product {rule.product_id} was not detected on shelf.",
        )

    if rule.kind == Kind5.REQUIRED_DISPLAY:
        for obs in relevant_obs:
            if obs.display == "PRESENT":
                return (
                    Result.PASS,
                    matching_evidence_ids,
                    f"Promotional feature display observed in zone '{obs.zone_id}'.",
                )
            if obs.display == "ABSENT":
                if obs.coverage == "FULL" and not obs.occluded:
                    return (
                        Result.FAIL,
                        matching_evidence_ids,
                        f"Display confirmed ABSENT with full unobstructed coverage in zone '{obs.zone_id}'.",
                    )
                return (
                    Result.UNKNOWN,
                    matching_evidence_ids,
                    f"Display absent but coverage is {obs.coverage}; cannot establish non-compliance.",
                )
            if obs.display == "UNKNOWN":
                return (
                    Result.UNKNOWN,
                    matching_evidence_ids,
                    f"Display status in zone '{obs.zone_id}' is UNKNOWN.",
                )

        return (
            Result.UNKNOWN,
            matching_evidence_ids,
            "Display zone status could not be established.",
        )

    return (
        Result.UNKNOWN,
        matching_evidence_ids,
        f"Unrecognized rule kind {rule.kind}.",
    )


def derive_aggregate_result(checks: list[Any]) -> Result1:
    """Strict aggregate result derivation order per specs/03-workflows.md:87-90.

    1. Any UNKNOWN -> INCONCLUSIVE.
    2. All PASS -> PASS.
    3. All FAIL -> FAIL.
    4. Otherwise -> PARTIAL.
    """
    if not checks:
        return Result1.INCONCLUSIVE

    # Extract result string or enum value
    results = [
        c.result.value if hasattr(c.result, "value") else str(c.result) for c in checks
    ]

    # 1. Any UNKNOWN -> INCONCLUSIVE
    if any(r == "UNKNOWN" for r in results):
        return Result1.INCONCLUSIVE

    # 2. All PASS -> PASS
    if all(r == "PASS" for r in results):
        return Result1.PASS

    # 3. All FAIL -> FAIL
    if all(r == "FAIL" for r in results):
        return Result1.FAIL

    # 4. Otherwise -> PARTIAL
    return Result1.PARTIAL
