"""StoreOps AI module: Gemini gateway, structured observations, and evidence-scoped investigation."""

from apps.api.ai.gateway import (
    DeterministicModelGateway,
    GeminiGateway,
    ModelGatewayError,
    ModelQuotaError,
    ModelSchemaError,
    ModelTimeoutError,
    ModelTransientError,
)
from apps.api.ai.investigator import (
    CallBudgetExceededError,
    GroundednessValidationError,
    InvestigationContext,
    Investigator,
    ReadOnlyToolRegistry,
    TenantIsolationError,
)
from apps.api.ai.probe import probe_live_gemini
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

__all__ = [
    "Alternative",
    "AnalysisProposal",
    "CallBudgetExceededError",
    "Detection",
    "DeterministicModelGateway",
    "ExtractedRule",
    "GeminiGateway",
    "GroundednessValidationError",
    "ImageObservation",
    "InvestigationContext",
    "Investigator",
    "ModelGatewayError",
    "ModelQuotaError",
    "ModelSchemaError",
    "ModelTimeoutError",
    "ModelTransientError",
    "PolicyExtraction",
    "ProposedAction",
    "ProposedCheck",
    "ProposedClaim",
    "ReadOnlyToolRegistry",
    "TenantIsolationError",
    "VerificationProposal",
    "probe_live_gemini",
    "validate_ai_schema",
]
