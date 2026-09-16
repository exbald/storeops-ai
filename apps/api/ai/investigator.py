"""Evidence-scoped Investigator with read-only tools, tenant scoping, and grounding validation."""

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from storeops_contracts.models import (
    SalesContext,
    Status8,
    ToolEnvelope,
)

from apps.api.ai.extract import calculate_metrics_from_sales_context
from apps.api.ai.prompts import (
    INVESTIGATION_PROMPT,
    INVESTIGATION_SYSTEM_INSTRUCTION,
)
from apps.api.ai.schemas import AnalysisProposal
from apps.api.ports.model import ModelGateway

logger = logging.getLogger(__name__)


class TenantIsolationError(Exception):
    """Raised when an operation attempts to access data outside its workspace boundary."""


class CallBudgetExceededError(Exception):
    """Raised when an investigation exceeds allowed tool call limit."""


class GroundednessValidationError(Exception):
    """Raised when a proposal cites ungrounded evidence or contradicts metrics."""


# Supported read-only tools per contracts/tools.json
ALLOWED_READ_ONLY_TOOLS = {
    "get_sales_context",
    "get_inventory_context",
    "get_approved_policy",
    "get_visit_history",
    "inspect_image",
    "extract_policy",
    "calculate_metrics",
}


@dataclass
class InvestigationContext:
    workspace_id: str
    store_id: UUID
    snapshot_id: UUID
    catalog_product_ids: list[UUID]
    policy_version_id: UUID | None = None
    zone_media_ids: dict[str, UUID] | None = None
    agreement_media_id: UUID | None = None


class ReadOnlyToolRegistry:
    """Workspace-scoped registry of read-only tools enforcing tenant isolation and envelope validation."""

    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id
        self._tools: dict[str, Callable[[dict[str, Any]], ToolEnvelope]] = {}

    def register(
        self, tool_name: str, handler: Callable[[dict[str, Any]], ToolEnvelope]
    ) -> None:
        if tool_name not in ALLOWED_READ_ONLY_TOOLS:
            raise ValueError(
                f"Tool '{tool_name}' is not in allowed read-only tools: {ALLOWED_READ_ONLY_TOOLS}"
            )
        self._tools[tool_name] = handler

    def execute(
        self, tool_name: str, caller_workspace_id: str, input_data: dict[str, Any]
    ) -> ToolEnvelope:
        if caller_workspace_id != self.workspace_id:
            raise TenantIsolationError(
                f"Workspace isolation violation: caller workspace '{caller_workspace_id}' cannot access registry for '{self.workspace_id}'."
            )

        if tool_name not in self._tools:
            return ToolEnvelope(
                status=Status8.ERROR,
                data=None,
                evidence_ids=[],
                as_of=datetime.now(UTC),
                error={
                    "code": "TOOL_NOT_FOUND",
                    "message": f"Tool '{tool_name}' not registered",
                    "retryable": False,
                },
            )

        envelope = self._tools[tool_name](input_data)
        if not isinstance(envelope, ToolEnvelope):
            raise TypeError(
                f"Tool '{tool_name}' must return a ToolEnvelope, got {type(envelope)}"
            )
        return envelope


class Investigator:
    """Evidence-scoped Investigator synthesizing grounded AnalysisProposal from read-only tools."""

    def __init__(self, gateway: ModelGateway, max_tool_calls: int = 15) -> None:
        self.gateway = gateway
        self.max_tool_calls = max_tool_calls

    async def run_investigation(
        self,
        ctx: InvestigationContext,
        tools: ReadOnlyToolRegistry,
    ) -> AnalysisProposal:
        tool_call_count = 0
        known_evidence_ids: set[UUID] = set()

        def call_tool(name: str, inp: dict[str, Any]) -> ToolEnvelope:
            nonlocal tool_call_count
            if tool_call_count >= self.max_tool_calls:
                raise CallBudgetExceededError(
                    f"Investigation call budget of {self.max_tool_calls} tool calls exceeded."
                )
            tool_call_count += 1
            env = tools.execute(
                tool_name=name, caller_workspace_id=ctx.workspace_id, input_data=inp
            )
            for eid in env.evidence_ids:
                known_evidence_ids.add(eid)
            return env

        # 1. Fetch sales context
        sales_env = call_tool(
            "get_sales_context",
            {"store_id": str(ctx.store_id), "snapshot_id": str(ctx.snapshot_id)},
        )

        # 2. Fetch inventory context
        stock_env = call_tool(
            "get_inventory_context",
            {"store_id": str(ctx.store_id), "snapshot_id": str(ctx.snapshot_id)},
        )

        # 3. Fetch visit history
        visit_env = call_tool(
            "get_visit_history",
            {
                "store_id": str(ctx.store_id),
                "snapshot_id": str(ctx.snapshot_id),
                "limit": 3,
            },
        )

        # 4. Inspect visual zones if media provided and inspect_image registered
        observations_data: list[dict[str, Any]] = []
        if "inspect_image" in tools._tools and ctx.zone_media_ids:
            for zone_id, media_id in ctx.zone_media_ids.items():
                img_env = call_tool(
                    "inspect_image",
                    {
                        "media_id": str(media_id),
                        "reference_media_ids": [
                            str(pid) for pid in ctx.catalog_product_ids[:10]
                        ],
                        "zone_id": zone_id,
                    },
                )
                if img_env.status == Status8.OK and img_env.data:
                    observations_data.append(img_env.data)

        # 5. Fetch approved policy if policy_version_id provided
        policy_env = None
        known_rule_ids: set[UUID] = set()
        if ctx.policy_version_id:
            policy_env = call_tool(
                "get_approved_policy",
                {"policy_version_id": str(ctx.policy_version_id)},
            )
            if policy_env.status == Status8.OK and policy_env.data:
                rules_list = policy_env.data.get("rules", [])
                for r in rules_list:
                    if isinstance(r, dict):
                        rid = r.get("rule_id") or r.get("id")
                        if rid:
                            try:
                                known_rule_ids.add(UUID(str(rid)))
                            except (ValueError, TypeError):
                                pass
                    elif hasattr(r, "rule_id"):
                        try:
                            known_rule_ids.add(UUID(str(r.rule_id)))
                        except (ValueError, TypeError):
                            pass
                    elif hasattr(r, "id"):
                        try:
                            known_rule_ids.add(UUID(str(r.id)))
                        except (ValueError, TypeError):
                            pass

        # 6. Calculate metrics deterministically using peer_gap_v1 or calculate_metrics tool
        metrics_data: dict[str, Any] = {}
        sales_delta_negative: bool = False
        if sales_env.status == Status8.OK and sales_env.data:
            if "calculate_metrics" in tools._tools:
                metrics_env = call_tool("calculate_metrics", sales_env.data)
                if metrics_env.status == Status8.OK and metrics_env.data:
                    metrics_data = (
                        metrics_env.data
                        if isinstance(metrics_env.data, dict)
                        else metrics_env.data.model_dump(mode="json")
                    )
            else:
                try:
                    sales_ctx = SalesContext.model_validate(sales_env.data)
                    metrics_obj = calculate_metrics_from_sales_context(
                        sales_ctx, currency=sales_ctx.currency
                    )
                    metrics_data = metrics_obj.model_dump(mode="json")
                except (KeyError, TypeError, ValueError, ZeroDivisionError) as err:
                    logger.warning(
                        f"Deterministic metric computation encountered: {err}"
                    )

            if metrics_data and metrics_data.get("sales_delta") is not None:
                try:
                    delta_dec = Decimal(str(metrics_data["sales_delta"]))
                    if delta_dec < Decimal(0):
                        sales_delta_negative = True
                except (ValueError, TypeError):
                    pass

        # 7. Build prompt with system instruction enclosure for ModelGateway
        prompt = (
            f"<system_instruction>\n{INVESTIGATION_SYSTEM_INSTRUCTION}\n</system_instruction>\n\n"
            + INVESTIGATION_PROMPT.format(
                store_id=ctx.store_id,
                snapshot_id=ctx.snapshot_id,
                sales_context=json.dumps(sales_env.data or {}),
                metrics_context=json.dumps(metrics_data),
                stock_context=json.dumps(stock_env.data or {}),
                visit_history=json.dumps(visit_env.data or {}),
                observations=json.dumps(observations_data),
                approved_policy=json.dumps(policy_env.data if policy_env else {}),
                evidence_ids=[str(e) for e in known_evidence_ids],
            )
        )

        # 8. Generate structured proposal via port-compliant method
        proposal: AnalysisProposal = await self.gateway.generate_structured(
            prompt=prompt,
            response_schema=AnalysisProposal,
        )

        # 9. Strict Groundedness Validation
        self._validate_groundedness(
            proposal=proposal,
            known_evidence_ids=known_evidence_ids,
            known_rule_ids=known_rule_ids,
            sales_delta_negative=sales_delta_negative,
            metrics_data=metrics_data,
        )

        return proposal

    def _validate_groundedness(
        self,
        proposal: AnalysisProposal,
        known_evidence_ids: set[UUID],
        known_rule_ids: set[UUID],
        sales_delta_negative: bool,
        metrics_data: dict[str, Any],
    ) -> None:
        # Check all claims cite known evidence
        for claim in proposal.claims:
            for eid in claim.evidence_ids:
                if eid not in known_evidence_ids:
                    raise GroundednessValidationError(
                        f"Ungrounded evidence ID {eid} in claim '{claim.claim_key}'. Must cite gathered evidence."
                    )

        # Check numerical metric conflict against computed Metrics DTO
        if sales_delta_negative:
            # If sales delta is negative, hypothesis cannot be NO_ISSUE
            if proposal.hypothesis == "NO_ISSUE":
                raise GroundednessValidationError(
                    "Contradiction: Hypothesis 'NO_ISSUE' conflicts with negative sales delta."
                )
            for claim in proposal.claims:
                lower_text = claim.text.lower()
                positive_patterns = [
                    r"\bincreased\b",
                    r"\bsales grew\b",
                    r"\bgrowth\b",
                    r"\bsurged\b",
                    r"\boutperformed\b",
                    r"\bpositive\b",
                    r"\+\d+",
                ]
                has_positive = any(
                    re.search(pat, lower_text) for pat in positive_patterns
                )
                negation_words = ["negative", "decline", "not", "decrease", "down"]
                has_negation = any(neg in lower_text for neg in negation_words)
                if has_positive and not has_negation:
                    raise GroundednessValidationError(
                        f"Numerical conflict in claim '{claim.claim_key}': claim asserts positive sales increase despite negative sales delta ({metrics_data.get('sales_delta')})."
                    )

        # Check all alternatives cite known evidence
        for alt in proposal.alternatives:
            for eid in alt.evidence_ids:
                if eid not in known_evidence_ids:
                    raise GroundednessValidationError(
                        f"Ungrounded evidence ID {eid} in alternative for hypothesis '{alt.hypothesis}'."
                    )

        # Check all actions cite known evidence, valid claim_keys, and known rule_ids
        claim_keys = {c.claim_key for c in proposal.claims}
        for action in proposal.actions:
            for eid in action.evidence_ids:
                if eid not in known_evidence_ids:
                    raise GroundednessValidationError(
                        f"Ungrounded evidence ID {eid} in proposed action '{action.kind}'."
                    )
            for ck in action.claim_keys:
                if ck not in claim_keys:
                    raise GroundednessValidationError(
                        f"Proposed action '{action.kind}' cites non-existent claim_key '{ck}'."
                    )
            for rid in action.rule_ids:
                if rid not in known_rule_ids:
                    raise GroundednessValidationError(
                        f"Ungrounded rule ID {rid} in proposed action '{action.kind}'. Rule does not exist in approved policy."
                    )
