"""AC39 AI Schema conformance and validation tests against contracts/ai-output.schema.json."""

import json
from pathlib import Path
from uuid import uuid4

import jsonschema
import pytest
from pydantic import ValidationError

from apps.api.ai.schemas import (
    Alternative,
    AnalysisProposal,
    Detection,
    ExtractedRule,
    ImageObservation,
    PolicyExtraction,
    ProposedAction,
    ProposedCheck,
    ProposedClaim,
    VerificationProposal,
    validate_ai_schema,
)


def get_json_schema(def_name: str) -> dict:
    schema_path = Path("contracts/ai-output.schema.json")
    with open(schema_path, "r", encoding="utf-8") as f:
        root = json.load(f)
    return {"$ref": f"#/$defs/{def_name}", "$defs": root["$defs"]}


def test_image_observation_valid_schema():
    obs = ImageObservation(
        media_id=uuid4(),
        zone_id="shelf-a-01",
        zone_kind="SHELF",
        quality="CLEAR",
        coverage="FULL",
        occluded=False,
        detections=[
            Detection(
                product_id=uuid4(),
                view="FRONT",
                box=[100, 150, 400, 450],
                identity="CLEAR",
                label="Product Brand X 500ml",
            )
        ],
        display="UNKNOWN",
        limitations=[],
    )
    # Pydantic dump
    data = json.loads(obs.model_dump_json())
    schema = get_json_schema("ImageObservation")
    jsonschema.validate(instance=data, schema=schema)
    assert validate_ai_schema("ImageObservation", data) is True


def test_image_observation_invalid_box_and_pattern():
    with pytest.raises(ValidationError):
        # Box requires 4 integers
        Detection(
            product_id=uuid4(),
            view="FRONT",
            box=[100, 200, 300],  # only 3 coords
            identity="CLEAR",
            label="Product",
        )

    with pytest.raises(ValidationError):
        # Box coordinate out of 0-1000 range
        Detection(
            product_id=uuid4(),
            view="FRONT",
            box=[100, 200, 300, 1001],
            identity="CLEAR",
            label="Product",
        )

    with pytest.raises(ValidationError):
        # Invalid zone_id pattern (starts with symbol)
        ImageObservation(
            media_id=uuid4(),
            zone_id="_invalid_zone",
            zone_kind="SHELF",
            quality="CLEAR",
            coverage="FULL",
            occluded=False,
            detections=[],
            display="UNKNOWN",
            limitations=[],
        )


def test_policy_extraction_valid_schema():
    rule = ExtractedRule(
        kind="MIN_FACINGS",
        zone_id="main-aisle",
        zone_kind="SHELF",
        product_id=uuid4(),
        min_facings=3,
        source_page=1,
        source_quote="Supplier requires minimum of 3 facings on center shelf.",
    )
    policy = PolicyExtraction(
        media_id=uuid4(),
        rules=[rule],
        gaps=["Endcap display specification missing from agreement."],
    )
    data = json.loads(policy.model_dump_json())
    schema = get_json_schema("PolicyExtraction")
    jsonschema.validate(instance=data, schema=schema)
    assert validate_ai_schema("PolicyExtraction", data) is True


def test_policy_extraction_invalid_rules():
    with pytest.raises(ValidationError):
        # min_facings out of bounds (1..100)
        ExtractedRule(
            kind="MIN_FACINGS",
            zone_id="zone-1",
            zone_kind="SHELF",
            product_id=uuid4(),
            min_facings=0,
            source_page=1,
            source_quote="Quote",
        )

    with pytest.raises(ValidationError):
        # source_page out of bounds (1..10)
        ExtractedRule(
            kind="MIN_FACINGS",
            zone_id="zone-1",
            zone_kind="SHELF",
            product_id=uuid4(),
            min_facings=2,
            source_page=11,
            source_quote="Quote",
        )


def test_analysis_proposal_valid_schema():
    ev1 = uuid4()
    ev2 = uuid4()
    claim1 = ProposedClaim(
        claim_key="c1",
        kind="OBSERVATION",
        text="Shelf inspection shows 1 visible facing of Brand X against required 3.",
        evidence_ids=[ev1],
    )
    claim2 = ProposedClaim(
        claim_key="c2",
        kind="METRIC",
        text="Sales dropped 20% compared to peer growth of 16.67%.",
        evidence_ids=[ev2],
    )
    action = ProposedAction(
        kind="RESTORE_FACINGS",
        rule_ids=[uuid4()],
        claim_keys=["c1"],
        evidence_ids=[ev1],
        instruction="Replenish Brand X from backroom and restore 3 front-facing positions.",
        required_zone_ids=["shelf-1"],
    )
    proposal = AnalysisProposal(
        hypothesis="EXECUTION",
        summary="Store displays execution gap: inventory is available in backroom but facing compliance is below requirement.",
        claims=[claim1, claim2],
        alternatives=[
            Alternative(
                hypothesis="SUPPLY_CONSTRAINT",
                reason="Distributor delivery may be delayed if backroom stock is exhausted.",
                evidence_ids=[ev1],
            )
        ],
        actions=[action],
        unresolved_questions=["Was distributor delivery on schedule this morning?"],
    )

    data = json.loads(proposal.model_dump_json())
    schema = get_json_schema("AnalysisProposal")
    jsonschema.validate(instance=data, schema=schema)
    assert validate_ai_schema("AnalysisProposal", data) is True


def test_analysis_proposal_constraints():
    ev_id = uuid4()

    # Invalid claim key pattern (must match ^c[1-9][0-9]*$)
    with pytest.raises(ValidationError):
        ProposedClaim(
            claim_key="c0",
            kind="OBSERVATION",
            text="Invalid key",
            evidence_ids=[ev_id],
        )

    with pytest.raises(ValidationError):
        ProposedClaim(
            claim_key="claim1",
            kind="OBSERVATION",
            text="Invalid key",
            evidence_ids=[ev_id],
        )

    # Empty evidence_ids in claim (minItems 1)
    with pytest.raises(ValidationError):
        ProposedClaim(
            claim_key="c1",
            kind="OBSERVATION",
            text="Missing evidence",
            evidence_ids=[],
        )

    # Actions limit: max 3 actions allowed by contract
    claims = [
        ProposedClaim(
            claim_key="c1", kind="OBSERVATION", text="Text", evidence_ids=[ev_id]
        )
    ]
    actions = [
        ProposedAction(
            kind="REPLENISH",
            rule_ids=[],
            claim_keys=["c1"],
            evidence_ids=[ev_id],
            instruction=f"Action {i}",
            required_zone_ids=[],
        )
        for i in range(4)
    ]
    with pytest.raises(ValidationError):
        AnalysisProposal(
            hypothesis="EXECUTION",
            summary="Too many actions",
            claims=claims,
            alternatives=[],
            actions=actions,
            unresolved_questions=[],
        )

    # Empty string in limitations (minLength 1)
    with pytest.raises(ValidationError):
        ImageObservation(
            media_id=uuid4(),
            zone_id="shelf-1",
            zone_kind="SHELF",
            quality="CLEAR",
            coverage="FULL",
            occluded=False,
            detections=[],
            display="UNKNOWN",
            limitations=[""],
        )

    # Oversized string > 500 in unresolved_questions (maxLength 500)
    with pytest.raises(ValidationError):
        AnalysisProposal(
            hypothesis="EXECUTION",
            summary="Valid summary",
            claims=claims,
            alternatives=[],
            actions=[],
            unresolved_questions=["x" * 501],
        )


def test_verification_proposal_valid_schema():
    prop = VerificationProposal(
        checks=[
            ProposedCheck(
                rule_id=uuid4(),
                result="PASS",
                evidence_ids=[uuid4()],
                explanation="Photo shows 3 clear front facings meeting minimum requirement.",
            )
        ],
        requested_retakes=[],
    )
    data = json.loads(prop.model_dump_json())
    schema = get_json_schema("VerificationProposal")
    jsonschema.validate(instance=data, schema=schema)
    assert validate_ai_schema("VerificationProposal", data) is True
