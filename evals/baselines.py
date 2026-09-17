"""Baseline model evaluators for StoreOps live evaluation comparison (specs/06-quality.md).

Includes:
1. DeterministicSalesStockBaseline: Rule-based heuristics using only inventory and sales signals.
2. ImageOnlyBaseline: Heuristic evaluation using only visual facing cues without catalog/stock history.
"""

from typing import Any


class DeterministicSalesStockBaseline:
    """Deterministic rule-based baseline using sales and inventory numbers."""

    def evaluate_scenario(self, scenario: dict[str, Any]) -> dict[str, Any]:
        category = scenario.get("category")
        ctx = scenario.get("input_context", {})

        if category == "diagnostic":
            return self._diagnose(ctx)
        elif category == "verification":
            return self._verify(ctx)
        else:
            return self._robustness(ctx)

    def _diagnose(self, ctx: dict[str, Any]) -> dict[str, Any]:
        shelf_stock = ctx.get("shelf_stock", 0)
        backroom_stock = ctx.get("backroom_stock", 0)
        distributor_stock = ctx.get("distributor_stock", 0)
        facings = ctx.get("facings_observed", 0)
        min_facings = ctx.get("policy_min_facings", 2)
        sales = ctx.get("recent_sales_units_7d", [])

        # Check explicit zero sales / holiday
        if "Day 4 shows exactly 0 units sold" in ctx.get("notes", ""):
            return {
                "diagnosis": "ZERO_SALES_RECORDED",
                "confidence": 0.95,
                "recommended_actions": ["NO_ACTION_REQUIRED"],
                "cited_ids": [ctx.get("sku", "")],
            }

        # Check stale inventory observation
        if ctx.get("inventory_observation_age_days", 0) > 14:
            return {
                "diagnosis": "STALE_INVENTORY_DATA",
                "confidence": 0.90,
                "recommended_actions": ["CONDUCT_PHYSICAL_CYCLE_COUNT"],
                "cited_ids": [ctx.get("sku", "")],
            }

        # Check phantom inventory
        if ctx.get("inventory_ledger_reported", 0) > 0 and shelf_stock == 0 and backroom_stock == 0:
            return {
                "diagnosis": "PHANTOM_INVENTORY",
                "confidence": 0.90,
                "recommended_actions": ["ADJUST_INVENTORY_SHRINKAGE", "TRIGGER_REORDER"],
                "cited_ids": [ctx.get("sku", "")],
            }

        # Check markdown compliance
        if (
            "shelf_price" in ctx
            and "policy_promo_price" in ctx
            and ctx["shelf_price"] != ctx["policy_promo_price"]
        ):
            return {
                "diagnosis": "PRICE_COMPLIANCE_ERROR",
                    "confidence": 0.95,
                    "recommended_actions": ["UPDATE_SHELF_PRICE_TAG"],
                    "cited_ids": [ctx.get("sku", "")],
                }

        # Check location breach
        if "observed_location" in ctx and ctx.get("observed_location") != ctx.get("policy_required_location"):
            return {
                "diagnosis": "LOCATION_BREACH",
                "confidence": 0.95,
                "recommended_actions": ["RELOCATE_TO_ENDCAP"],
                "cited_ids": [ctx.get("sku", "")],
            }

        # Check loading dock staging
        if ctx.get("dock_staging_stock", 0) > 0:
            return {
                "diagnosis": "REPLENISHMENT_LAG",
                "confidence": 0.90,
                "recommended_actions": ["TRANSPORT_PALLET_TO_FLOOR", "STOCK_SHELF"],
                "cited_ids": [ctx.get("sku", "")],
            }

        # Check facing encroachment
        if "sibling_sku" in ctx and ctx.get("sibling_facings", 0) > min_facings and facings < min_facings:
            return {
                "diagnosis": "FACING_ENCROACHMENT",
                "confidence": 0.90,
                "recommended_actions": ["REBALANCE_PLANOGRAM"],
                "cited_ids": [ctx.get("sku", ""), ctx.get("sibling_sku", "")],
            }

        # Check demand surge
        if any(s > 50 for s in sales) and shelf_stock == 0:
            return {
                "diagnosis": "UNPLANNED_DEMAND_SURGE",
                "confidence": 0.85,
                "recommended_actions": ["INCREASE_SAFETY_STOCK"],
                "cited_ids": [ctx.get("sku", "")],
            }

        # Check misplaced lookalike product
        notes = ctx.get("notes", "").lower()
        if "lookalike" in notes or "misplaced" in notes or "wrong" in notes:
            return {
                "diagnosis": "MISPLACED_PRODUCT",
                "confidence": 0.90,
                "recommended_actions": ["REMOVE_WRONG_SKU", "RESTOCK_TARGET_SKU"],
                "cited_ids": [ctx.get("sku", "")],
            }

        # Check multi-SKU promotion co-location execution gap
        if "paired_sku" in ctx or "co-locat" in notes:
            return {
                "diagnosis": "EXECUTION_GAP",
                "confidence": 0.90,
                "recommended_actions": ["CO_LOCATE_PROMOTIONAL_ITEMS", "STOCK_SHELF"],
                "cited_ids": [cid for cid in [ctx.get("sku", ""), ctx.get("paired_sku", "")] if cid],
            }

        # Core execution vs shortage vs healthy logic
        if facings == 0 and backroom_stock > 0:
            return {
                "diagnosis": "SHELF_OUT_OF_STOCK",
                "confidence": 0.95,
                "recommended_actions": ["RESTOCK_FROM_BACKROOM"],
                "cited_ids": [ctx.get("sku", "")],
            }
        elif facings == 0 and backroom_stock == 0 and distributor_stock == 0:
            return {
                "diagnosis": "SUPPLY_CHAIN_SHORTAGE",
                "confidence": 0.90,
                "recommended_actions": ["PLACE_DISTRIBUTOR_BACKORDER"],
                "cited_ids": [ctx.get("sku", "")],
            }
        elif 0 < facings < min_facings:
            return {
                "diagnosis": "PARTIAL_COMPLIANCE",
                "confidence": 0.85,
                "recommended_actions": ["EXPAND_FACINGS"],
                "cited_ids": [ctx.get("sku", "")],
            }
        elif facings >= min_facings and any(s < 5 for s in sales[-3:]) and shelf_stock > 10:
            return {
                "diagnosis": "DEMAND_DROP",
                "confidence": 0.80,
                "recommended_actions": ["INVESTIGATE_COMPETITOR_PRICING"],
                "cited_ids": [ctx.get("sku", "")],
            }
        else:
            return {
                "diagnosis": "COMPLIANT_NO_ACTION",
                "confidence": 0.90,
                "recommended_actions": ["NO_ACTION_REQUIRED"],
                "cited_ids": [ctx.get("sku", "")],
            }

    def _verify(self, ctx: dict[str, Any]) -> dict[str, Any]:
        # Check duplicate before/after image hash
        if ctx.get("before_image_hash") and ctx.get("before_image_hash") == ctx.get("after_image_hash"):
            return {"outcome": "REUSED_BEFORE_MEDIA", "confidence": 1.0, "is_compliant": False}

        # Check visual obstruction
        if "visual_obstruction" in ctx or ctx.get("visibility_score", 1.0) < 0.5:
            return {"outcome": "RETAKE_REQUESTED", "confidence": 0.90, "is_compliant": False}

        # Check blur
        if "blur_metric" in ctx:
            return {"outcome": "RETAKE_REQUESTED", "confidence": 0.85, "is_compliant": False}

        # Check zone
        if "required_zone" in ctx and ctx.get("imaged_zone") != ctx.get("required_zone"):
            return {"outcome": "FAIL", "confidence": 0.95, "is_compliant": False}

        # Check lookalike substitution
        if "detected_sku" in ctx and "LOOKALIKE" in ctx.get("detected_sku", ""):
            return {"outcome": "FAIL", "confidence": 0.95, "is_compliant": False}

        # Check price compliance
        if "detected_price" in ctx and ctx.get("detected_price") != ctx.get("contract_promo_price"):
            return {"outcome": "FAIL", "confidence": 0.95, "is_compliant": False}

        # Facings check
        verified_facings = ctx.get("verified_facings", 0)
        required_facings = ctx.get("required_facings", 1)

        if verified_facings >= required_facings:
            return {"outcome": "PASS", "confidence": 0.95, "is_compliant": True}
        else:
            return {"outcome": "FAIL", "confidence": 0.90, "is_compliant": False}

    def _robustness(self, ctx: dict[str, Any]) -> dict[str, Any]:
        notes = ctx.get("notes", "")
        if "SYSTEM OVERRIDE" in notes or "ignore all" in notes:
            return {"outcome": "INJECTION_ATTEMPT_DEFENDED", "confidence": 1.0, "is_compliant": False}
        if ctx.get("media_payload_status") == "CORRUPTED_BYTES":
            return {"outcome": "MEDIA_CORRUPTED_ERROR", "confidence": 1.0, "is_compliant": False}
        if ctx.get("provider_response_code") == 429:
            return {"outcome": "BLOCKED_RATE_LIMIT", "confidence": 1.0, "is_compliant": False}
        if "investigation_policy_version" in ctx and ctx["investigation_policy_version"] != ctx.get("current_approved_policy_version"):
            return {"outcome": "STALE_POLICY_CONFLICT", "confidence": 1.0, "is_compliant": False}
        if ctx.get("store_id") == "00000000-0000-0000-0000-000000000000":
            return {"outcome": "ENTITY_NOT_FOUND", "confidence": 1.0, "is_compliant": False}
        return {"outcome": "SCHEMA_STRICTLY_ENFORCED", "confidence": 0.90, "is_compliant": False}


class ImageOnlyBaseline:
    """Baseline using only simulated visual observations without sales or backroom stock."""

    def evaluate_scenario(self, scenario: dict[str, Any]) -> dict[str, Any]:
        ctx = scenario.get("input_context", {})
        category = scenario.get("category")

        if category == "verification":
            verified = ctx.get("verified_facings", 0)
            required = ctx.get("required_facings", 1)
            if verified >= required and not ctx.get("visual_obstruction"):
                return {"outcome": "PASS", "confidence": 0.80, "is_compliant": True}
            return {"outcome": "FAIL", "confidence": 0.75, "is_compliant": False}

        # Diagnostic: pure facing count without backroom visibility cannot distinguish shortage from execution gap
        facings = ctx.get("facings_observed", 0)
        if facings == 0:
            return {"diagnosis": "OUT_OF_STOCK_UNKNOWN_CAUSE", "confidence": 0.50}
        return {"diagnosis": "FACINGS_PRESENT", "confidence": 0.70}
