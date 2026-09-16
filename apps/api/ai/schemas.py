"""Pydantic V2 schemas and JSON Schema validation matching contracts/ai-output.schema.json."""

import json
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

import jsonschema
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, conint

# Reusable constraints
ZoneId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
ClaimKey = Annotated[str, StringConstraints(pattern=r"^c[1-9][0-9]*$")]
BoxCoord = Annotated[int, Field(ge=0, le=1000)]
Box = Annotated[list[BoxCoord], Field(min_length=4, max_length=4)]
String500 = Annotated[str, Field(min_length=1, max_length=500)]


class Detection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID | None
    view: Literal["FRONT", "OTHER"]
    box: Box
    identity: Literal["CLEAR", "AMBIGUOUS"]
    label: str = Field(..., min_length=1, max_length=200)


class ImageObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_id: UUID
    zone_id: ZoneId
    zone_kind: Literal["SHELF", "DISPLAY"]
    quality: Literal["CLEAR", "UNUSABLE"]
    coverage: Literal["FULL", "PARTIAL", "UNKNOWN"]
    occluded: bool
    detections: list[Detection] = Field(..., min_length=0, max_length=100)
    display: Literal["PRESENT", "ABSENT", "UNKNOWN"]
    limitations: list[String500] = Field(..., min_length=0, max_length=20)


class ExtractedRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["MIN_FACINGS", "REQUIRED_PRODUCT", "REQUIRED_DISPLAY"]
    zone_id: ZoneId | None = None
    zone_kind: Literal["SHELF", "DISPLAY"] | None = None
    product_id: UUID | None = None
    min_facings: conint(ge=1, le=100) | None = None
    source_page: conint(ge=1, le=10)
    source_quote: str = Field(..., min_length=1, max_length=2000)


class PolicyExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_id: UUID
    rules: list[ExtractedRule] = Field(..., min_length=0, max_length=30)
    gaps: list[String500] = Field(..., min_length=0, max_length=20)


class ProposedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_key: ClaimKey
    kind: Literal["OBSERVATION", "POLICY", "METRIC", "HYPOTHESIS"]
    text: str = Field(..., min_length=1, max_length=800)
    evidence_ids: list[UUID] = Field(..., min_length=1, max_length=30)


class ProposedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "REPLENISH",
        "RESTORE_FACINGS",
        "INSTALL_DISPLAY",
        "CHECK_STOCK",
        "REQUEST_SUPPLY",
        "RETAKE",
    ]
    rule_ids: list[UUID] = Field(..., min_length=0, max_length=30)
    claim_keys: list[ClaimKey] = Field(..., min_length=1, max_length=20)
    evidence_ids: list[UUID] = Field(..., min_length=1, max_length=30)
    instruction: str = Field(..., min_length=1, max_length=1000)
    required_zone_ids: list[ZoneId] = Field(..., min_length=0, max_length=10)


class Alternative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis: Literal[
        "EXECUTION",
        "SUPPLY_CONSTRAINT",
        "UNEXPLAINED_DECLINE",
        "NO_ISSUE",
        "INSUFFICIENT_EVIDENCE",
    ]
    reason: str = Field(..., min_length=1, max_length=800)
    evidence_ids: list[UUID] = Field(..., min_length=0, max_length=30)


class AnalysisProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis: Literal[
        "EXECUTION",
        "SUPPLY_CONSTRAINT",
        "UNEXPLAINED_DECLINE",
        "NO_ISSUE",
        "INSUFFICIENT_EVIDENCE",
    ]
    summary: str = Field(..., min_length=1, max_length=1000)
    claims: list[ProposedClaim] = Field(..., min_length=1, max_length=20)
    alternatives: list[Alternative] = Field(..., min_length=0, max_length=3)
    actions: list[ProposedAction] = Field(..., min_length=0, max_length=3)
    unresolved_questions: list[String500] = Field(..., min_length=0, max_length=20)


class ProposedCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: UUID
    result: Literal["PASS", "FAIL", "UNKNOWN"]
    evidence_ids: list[UUID] = Field(..., min_length=0, max_length=30)
    explanation: str = Field(..., min_length=1, max_length=1000)


class VerificationProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checks: list[ProposedCheck] = Field(..., min_length=1, max_length=30)
    requested_retakes: list[String500] = Field(..., min_length=0, max_length=20)


def validate_ai_schema(def_name: str, instance: dict[str, Any]) -> bool:
    """Validate raw python dict against the exact $defs entry in contracts/ai-output.schema.json."""
    schema_path = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "contracts"
        / "ai-output.schema.json"
    )
    if not schema_path.exists():
        schema_path = Path("contracts/ai-output.schema.json")
    with open(schema_path, "r", encoding="utf-8") as f:
        root = json.load(f)

    subschema = {"$ref": f"#/$defs/{def_name}", "$defs": root["$defs"]}
    validator = jsonschema.Draft202012Validator(subschema)
    validator.validate(instance=instance)
    return True
