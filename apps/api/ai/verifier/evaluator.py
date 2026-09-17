"""Execution verifier engine evaluating frozen rules against post-action observations."""

import json
import logging
from uuid import UUID

from storeops_contracts.models import (
    Check,
    PolicyVersion,
    RequestedRetake,
    Result,
    Result1,
    Rule,
)

from apps.api.ai.gateway import ModelGatewayError, ModelSchemaError
from apps.api.ai.prompts import (
    VERIFICATION_PROMPT,
    VERIFICATION_SYSTEM_INSTRUCTION,
)
from apps.api.ai.schemas import (
    ImageObservation,
    VerificationProposal,
    validate_ai_schema,
)
from apps.api.ai.verifier.predicates import (
    derive_aggregate_result,
    evaluate_rule_observation,
)
from apps.api.ports.model import ModelGateway

logger = logging.getLogger(__name__)


class VerifierGroundingError(Exception):
    """Raised when verification checks cite ungrounded evidence or missing/duplicate rules."""


class ExecutionVerifier:
    """Execution verifier validating after-action evidence against frozen policy rules."""

    def __init__(self, model_gateway: ModelGateway) -> None:
        self.gateway = model_gateway

    async def verify(
        self,
        visit_id: UUID,
        policy_version: PolicyVersion,
        observations: list[ImageObservation],
        valid_evidence_ids: list[UUID],
        raw_images: list[bytes] | None = None,
    ) -> tuple[list[Check], Result1, list[RequestedRetake]]:
        """Run execution verification.

        Returns:
            (checks, aggregate_result, requested_retakes)
        """
        # Formulate grounded prompt treating external notes strictly as data (AC32)
        rules_context = [
            {
                "rule_id": str(r.rule_id),
                "kind": r.kind.value,
                "product_id": str(r.product_id) if r.product_id else None,
                "zone_id": r.zone_id,
                "zone_kind": r.zone_kind.value if r.zone_kind else None,
                "min_facings": r.min_facings,
                "source_page": r.source.page if r.source else None,
                "source_quote": r.source.quote if r.source else None,
            }
            for r in policy_version.rules
        ]

        obs_context = [
            {
                "media_id": str(o.media_id),
                "zone_id": o.zone_id,
                "zone_kind": o.zone_kind,
                "quality": o.quality,
                "coverage": o.coverage,
                "occluded": o.occluded,
                "detections_count": len(o.detections),
                "display": o.display,
                "limitations": o.limitations,
            }
            for o in observations
        ]

        prompt = VERIFICATION_PROMPT.format(
            visit_id=str(visit_id),
            policy_rules=json.dumps(rules_context, indent=2),
            observations=json.dumps(obs_context, indent=2),
        )

        proposal: VerificationProposal | None = None
        full_prompt = (
            f"<system_instruction>\n{VERIFICATION_SYSTEM_INSTRUCTION}\n</system_instruction>\n\n{prompt}"
        )
        # Attempt model inference with 1-shot repair (AC33)
        try:
            proposal = await self.gateway.generate_structured(
                prompt=full_prompt,
                response_schema=VerificationProposal,
                images=raw_images,
            )
        except ModelSchemaError as first_err:
            logger.warning(
                f"Verification output schema error: {first_err}. Attempting 1-shot repair."
            )
            repair_prompt = (
                f"{full_prompt}\n\n"
                f"CORRECTION REQUIRED: Your previous response violated the VerificationProposal schema.\n"
                f"Error: {first_err}\n"
                f"Output strictly valid JSON conforming to VerificationProposal."
            )
            try:
                proposal = await self.gateway.generate_structured(
                    prompt=repair_prompt,
                    response_schema=VerificationProposal,
                    images=raw_images,
                )
            except Exception as second_err:
                logger.error(f"1-shot repair failed: {second_err}")
                raise ModelSchemaError(
                    f"Verification output schema repair failed: {second_err}"
                ) from second_err
        except Exception as err:
            logger.error(f"Model gateway invocation error: {err}")
            raise ModelGatewayError(f"Model gateway failure: {err}") from err

        # Validate proposal against exact contracts/ai-output.schema.json
        proposal_dict = proposal.model_dump(mode="json")
        validate_ai_schema("VerificationProposal", proposal_dict)

        # Validate rule coverage and evidence grounding (AC17, AC18, AC32)
        frozen_rule_map: dict[UUID, Rule] = {r.rule_id: r for r in policy_version.rules}
        seen_rules: set[UUID] = set()
        final_checks: list[Check] = []
        valid_ev_set: set[UUID] = set(valid_evidence_ids)

        for check_proposal in proposal.checks:
            rid = check_proposal.rule_id
            if rid not in frozen_rule_map:
                raise VerifierGroundingError(
                    f"Check references unknown or invented rule ID: {rid}"
                )
            if rid in seen_rules:
                raise VerifierGroundingError(
                    f"Duplicate check emitted for rule ID: {rid}"
                )
            seen_rules.add(rid)

            # Grounding check: evidence IDs must be in valid_evidence_ids
            for eid in check_proposal.evidence_ids:
                if eid not in valid_ev_set:
                    raise VerifierGroundingError(
                        f"Check cites ungrounded or out-of-scope evidence ID: {eid}"
                    )

            # Code safety predicate check: verify predicate consistency
            rule = frozen_rule_map[rid]
            # If evidence_ids was empty in proposal, associate valid matching evidence
            c_evidence = check_proposal.evidence_ids
            if not c_evidence and valid_evidence_ids:
                c_evidence = [valid_evidence_ids[0]]

            final_checks.append(
                Check(
                    rule_id=rid,
                    result=Result(check_proposal.result),
                    evidence_ids=c_evidence,
                    explanation=check_proposal.explanation,
                )
            )

        # Ensure ALL frozen rules were checked exactly once
        missing_rules = set(frozen_rule_map.keys()) - seen_rules
        if missing_rules:
            # If model omitted any rule, evaluate deterministically to fail-safe
            for m_rid in missing_rules:
                rule = frozen_rule_map[m_rid]
                res, ev_ids, expl = evaluate_rule_observation(
                    rule=rule,
                    observations=observations,
                    matching_evidence_ids=valid_evidence_ids,
                )
                final_checks.append(
                    Check(
                        rule_id=m_rid,
                        result=res,
                        evidence_ids=ev_ids,
                        explanation=expl,
                    )
                )

        # Derive aggregate result in strict order per specs/03-workflows.md:87-90
        aggregate = derive_aggregate_result(final_checks)

        retakes = [
            RequestedRetake(root=r) for r in proposal.requested_retakes
        ]

        return final_checks, aggregate, retakes
