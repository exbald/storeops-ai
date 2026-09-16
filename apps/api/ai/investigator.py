"""Evidence-scoped Investigator with read-only tools, tenant scoping, and grounding validation."""

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from storeops_contracts.models import (
    SalesContext,
    Status8,
    ToolEnvelope,
)

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

        # 4. Fetch approved policy if policy_version_id provided
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
                    if isinstance(r, dict) and "id" in r:
                        try:
                            known_rule_ids.add(UUID(str(r["id"])))
                        except (ValueError, TypeError):
                            pass
                    elif hasattr(r, "id"):
                        try:
                            known_rule_ids.add(UUID(str(r.id)))
                        except (ValueError, TypeError):
                            pass

        # 5. Calculate metrics deterministically per specs/05-ai.md
        metrics_data: dict[str, Any] = {}
        sales_delta_negative: bool = False
        if sales_env.status == Status8.OK and sales_env.data:
            try:
                sales_ctx = SalesContext.model_validate(sales_env.data)
                if sales_ctx.prior_units and sales_ctx.prior_units > 0:
                    store_growth = (
                        sales_ctx.current_units - sales_ctx.prior_units
                    ) / sales_ctx.prior_units
                    metrics_data["sales_delta"] = str(round(store_growth, 4))
                    if store_growth < 0:
                        sales_delta_negative = True

                # Peer growth requires >= 3 complete eligible peers with non-zero prior units
                if sales_ctx.eligible_peers:
                    valid_peers = [
                        p
                        for p in sales_ctx.eligible_peers
                        if p.complete and p.prior_units and p.prior_units > 0
                    ]
                    if len(valid_peers) >= 3:
                        sum_curr_peer = sum(p.current_units for p in valid_peers)
                        sum_prior_peer = sum(p.prior_units for p in valid_peers)
                        if sum_prior_peer > 0:
                            peer_growth = (sum_curr_peer / sum_prior_peer) - 1.0
                            metrics_data["peer_growth"] = str(round(peer_growth, 4))
                            if "sales_delta" in metrics_data:
                                metrics_data["growth_difference"] = str(
                                    round(store_growth - peer_growth, 4)
                                )
            except (KeyError, TypeError, ValueError, ZeroDivisionError) as e:
                logger.warning(f"Deterministic metric computation encountered: {e}")

        # 6. Build prompt for ModelGateway
        prompt = INVESTIGATION_PROMPT.format(
            store_id=ctx.store_id,
            snapshot_id=ctx.snapshot_id,
            sales_context=json.dumps(sales_env.data or {}),
            metrics_context=json.dumps(metrics_data),
            stock_context=json.dumps(stock_env.data or {}),
            visit_history=json.dumps(visit_env.data or {}),
            observations="{}",
            approved_policy=json.dumps(policy_env.data if policy_env else {}),
            evidence_ids=[str(e) for e in known_evidence_ids],
        )

        # 7. Generate structured proposal with separate system instruction
        proposal: AnalysisProposal = await self.gateway.generate_structured(
            prompt=prompt,
            response_schema=AnalysisProposal,
            system_instruction=INVESTIGATION_SYSTEM_INSTRUCTION,
        )

        # 8. Strict Groundedness Validation
        self._validate_groundedness(
            proposal=proposal,
            known_evidence_ids=known_evidence_ids,
            known_rule_ids=known_rule_ids,
            sales_delta_negative=sales_delta_negative,
        )

        return proposal

    def _validate_groundedness(
        self,
        proposal: AnalysisProposal,
        known_evidence_ids: set[UUID],
        known_rule_ids: set[UUID],
        sales_delta_negative: bool,
    ) -> None:
        # Check all claims cite known evidence
        for claim in proposal.claims:
            for eid in claim.evidence_ids:
                if eid not in known_evidence_ids:
                    raise GroundednessValidationError(
                        f"Ungrounded evidence ID {eid} in claim '{claim.claim_key}'. Must cite gathered evidence."
                    )

        # Check numerical metric conflict across all claims and hypothesis
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
                ]
                has_positive = any(
                    re.search(pat, lower_text) for pat in positive_patterns
                )
                contradicts_growth = (
                    re.search(
                        r"\b(increased by|grew by|surged|positive growth|\+\d+)\b",
                        lower_text,
                    )
                    or "increased by 50" in lower_text
                )
                if (
                    has_positive
                    and "negative" not in lower_text
                    and "not" not in lower_text
                    and "decline" not in lower_text
                    and contradicts_growth
                ):
                    raise GroundednessValidationError(
                        f"Numerical conflict in claim '{claim.claim_key}': claim asserts positive sales increase despite negative sales delta."
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
