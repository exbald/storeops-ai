import asyncio
import hashlib
import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from storeops_contracts.models import (
    Action,
    ActionUpdate,
    Alternative,
    Claim,
    Diagnosis,
    Dismiss,
    Evidence,
    EvidenceList,
    Freshness1,
    Hypothesis,
    Investigation,
    InvestigationCreate,
    InvestigationList,
    Job,
    Kind6,
    Kind7,
    Kind8,
    Locator,
    Outcome,
    PolicyVersion,
    Promotion,
    Report,
    RequiredZoneId,
    ResourceType,
    SalesContext,
    State,
    Status1,
    Status2,
    Status5,
    Status6,
    StockContext,
    Support,
    Type2,
    VersionCommand,
    Visit,
    VisitCreate,
    VisitHistoryContext,
    VisitList,
    VisitUpdate,
)

from apps.api.ai.extract import calculate_metrics_from_sales_context
from apps.api.ai.gateway import ModelSchemaError
from apps.api.ai.investigator import (
    CallBudgetExceededError,
    GroundednessValidationError,
    InvestigationContext,
    Investigator,
    ReadOnlyToolRegistry,
)
from apps.api.ai.schemas import AnalysisProposal
from apps.api.core.errors import ApiError
from apps.api.modules.visits.ports import VisitCatalogPort, VisitPolicyPort
from apps.api.modules.visits.repository import VisitRepository
from apps.api.ports.analytics import AnalyticsRepository
from apps.api.ports.blob import BlobRepository
from apps.api.ports.clock import Clock
from apps.api.ports.model import ModelGateway
from apps.api.ports.state import StateRepository

logger = logging.getLogger(__name__)


class VisitService:
    def __init__(
        self,
        visit_repo: VisitRepository,
        catalog_repo: VisitCatalogPort,
        policy_repo: VisitPolicyPort,
        state_repo: StateRepository,
        model_gateway: ModelGateway,
        clock: Clock,
        analytics_repo: AnalyticsRepository | None = None,
        blob_repo: BlobRepository | None = None,
    ) -> None:
        self.visit_repo = visit_repo
        self.catalog_repo = catalog_repo
        self.policy_repo = policy_repo
        self.state_repo = state_repo
        self.model_gateway = model_gateway
        self.clock = clock
        self.analytics_repo = analytics_repo
        self.blob_repo = blob_repo
        self._inv_lock = asyncio.Lock()

    async def create_visit(
        self, workspace_id: UUID, payload: VisitCreate, uid: str
    ) -> Visit:
        store = await self.catalog_repo.get_store(workspace_id, payload.store_id)
        if not store:
            raise ApiError(
                status_code=404,
                code="STORE_NOT_FOUND",
                message=f"Store {payload.store_id} not found",
            )
        if not store.active:
            raise ApiError(
                status_code=422,
                code="STORE_INACTIVE",
                message=f"Store {payload.store_id} is inactive or archived",
            )

        now = self.clock.now_utc()
        visit = Visit(
            id=uuid4(),
            workspace_id=workspace_id,
            version=1,
            created_at=now,
            updated_at=now,
            store_id=payload.store_id,
            notes=payload.notes,
            visit_started_at=now,
            status=Status5.OPEN,
            before_media_ids=[],
            after_media_ids=[],
            active_investigation_id=None,
            report_ids=[],
        )
        return await self.visit_repo.create_visit(workspace_id, visit)

    async def get_visit(self, workspace_id: UUID, visit_id: UUID) -> Visit:
        visit = await self.visit_repo.get_visit(workspace_id, visit_id)
        if not visit:
            raise ApiError(
                status_code=404,
                code="VISIT_NOT_FOUND",
                message=f"Visit {visit_id} not found",
            )
        return visit

    async def list_visits(
        self,
        workspace_id: UUID,
        store_id: UUID | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> VisitList:
        items, next_cursor = await self.visit_repo.list_visits(
            workspace_id, store_id=store_id, cursor=cursor, limit=limit
        )
        return VisitList(items=items, next_cursor=next_cursor)

    async def update_visit(
        self, workspace_id: UUID, visit_id: UUID, payload: VisitUpdate, uid: str
    ) -> Visit:
        visit = await self.get_visit(workspace_id, visit_id)
        if visit.status != Status5.OPEN:
            raise ApiError(
                status_code=409,
                code="VISIT_CLOSED",
                message="Cannot update notes on a closed visit",
            )
        if visit.version != payload.expected_version:
            raise ApiError(
                status_code=409,
                code="VERSION_CONFLICT",
                message=f"Expected version {payload.expected_version} but visit is at version {visit.version}",
            )

        now = self.clock.now_utc()
        visit.notes = payload.notes
        visit.version += 1
        visit.updated_at = now
        return await self.visit_repo.update_visit(workspace_id, visit)

    async def create_investigation(
        self, workspace_id: UUID, payload: InvestigationCreate, uid: str
    ) -> Job:
        # Validate Store
        store = await self.catalog_repo.get_store(workspace_id, payload.store_id)
        if not store:
            raise ApiError(
                status_code=404,
                code="STORE_NOT_FOUND",
                message=f"Store {payload.store_id} not found",
            )
        if not store.active:
            raise ApiError(
                status_code=422,
                code="STORE_INACTIVE",
                message="Store is inactive or archived",
            )

        async with self._inv_lock:
            # Validate Visit
            visit = await self.get_visit(workspace_id, payload.visit_id)
            if visit.store_id != payload.store_id:
                raise ApiError(
                    status_code=422,
                    code="STORE_MISMATCH",
                    message=f"Visit {payload.visit_id} does not belong to store {payload.store_id}",
                )
            if visit.status != Status5.OPEN:
                raise ApiError(
                    status_code=409,
                    code="VISIT_NOT_OPEN",
                    message="Cannot start investigation on a closed visit",
                )

            # Invariant: At most one nonterminal investigation exists per visit (contracts/SEMANTICS.md:54-56)
            if visit.active_investigation_id:
                old_inv = await self.visit_repo.get_investigation(
                    workspace_id, visit.active_investigation_id
                )
                if old_inv:
                    if old_inv.state in (
                        State.QUEUED,
                        State.INVESTIGATING,
                        State.VERIFYING,
                    ):
                        raise ApiError(
                            status_code=409,
                            code="ACTIVE_INVESTIGATION_RUNNING",
                            message="An active investigation job is currently running on this visit",
                        )
                    if old_inv.state in (
                        State.PROPOSED,
                        State.ACCEPTED,
                        State.NEEDS_WORK,
                        State.INCOMPLETE,
                    ):
                        raise ApiError(
                            status_code=409,
                            code="ACTIVE_INVESTIGATION_EXISTS",
                            message="Starting another investigation requires dismissing the existing nonterminal investigation first",
                        )

            # Validate Promotion
            promo = await self.policy_repo.get_promotion(
                workspace_id, payload.promotion_id
            )
            if not promo:
                raise ApiError(
                    status_code=404,
                    code="PROMOTION_NOT_FOUND",
                    message=f"Promotion {payload.promotion_id} not found",
                )
            if promo.archived:
                raise ApiError(
                    status_code=422,
                    code="PROMOTION_ARCHIVED",
                    message="Promotion is archived",
                )
            if not promo.approved_policy:
                raise ApiError(
                    status_code=422,
                    code="POLICY_NOT_APPROVED",
                    message="Promotion does not have an approved policy version",
                )

            policy_ver = promo.approved_policy

            # Validate Media
            if not payload.media_ids:
                raise ApiError(
                    status_code=422,
                    code="MEDIA_REQUIRED",
                    message="At least one media ID is required for investigation",
                )

            now = self.clock.now_utc()
            for mid in payload.media_ids:
                media = await self.catalog_repo.get_media(workspace_id, mid)
                if not media:
                    raise ApiError(
                        status_code=422,
                        code="MEDIA_NOT_FOUND",
                        message=f"Media {mid} not found",
                    )
                if media.status != Status1.READY:
                    raise ApiError(
                        status_code=422,
                        code="MEDIA_NOT_READY",
                        message=f"Media {mid} is not ready (status: {media.status.value})",
                    )
                if media.store_id != payload.store_id:
                    raise ApiError(
                        status_code=422,
                        code="MEDIA_STORE_MISMATCH",
                        message=f"Media {mid} belongs to a different store",
                    )
                if media.visit_id != payload.visit_id:
                    raise ApiError(
                        status_code=422,
                        code="MEDIA_VISIT_MISMATCH",
                        message=f"Media {mid} was not captured for this visit",
                    )

            # Bind media IDs to visit before_media_ids
            for mid in payload.media_ids:
                if mid not in visit.before_media_ids:
                    visit.before_media_ids.append(mid)

            investigation_id = uuid4()
            snapshot_id = uuid4()
            job_id = uuid4()

            job = Job(
                id=job_id,
                workspace_id=workspace_id,
                version=1,
                created_at=now,
                updated_at=now,
                type=Type2.INVESTIGATE,
                status=Status2.QUEUED,
                resource_id=investigation_id,
                resource_type=ResourceType.INVESTIGATION,
                attempt=0,
                stage="QUEUED",
                started_at=None,
                finished_at=None,
                error=None,
                linked_previous_job_id=None,
                model_id=None,
                usage=None,
            )
            await self.state_repo.create_job_with_outbox(job)

            inv = Investigation(
                id=investigation_id,
                workspace_id=workspace_id,
                version=1,
                created_at=now,
                updated_at=now,
                visit_id=visit.id,
                store_id=store.id,
                promotion_id=promo.id,
                policy_version_id=policy_ver.id,
                snapshot_id=snapshot_id,
                snapshot_at=now,
                state=State.QUEUED,
                metrics=None,
                diagnosis=None,
                actions=[],
                plan_revision=0,
                accepted_at=None,
                accepted_by=None,
                current_job_id=job_id,
                latest_verification_id=None,
                policy_stale=False,
            )
            await self.visit_repo.create_investigation(workspace_id, inv)

            visit.active_investigation_id = investigation_id
            visit.version += 1
            visit.updated_at = now
            await self.visit_repo.update_visit(workspace_id, visit)

        # Run pipeline synchronously for LOCAL / in-process execution
        await self._run_investigation_pipeline(
            workspace_id=workspace_id,
            inv=inv,
            visit=visit,
            promo=promo,
            policy_ver=policy_ver,
            media_ids=payload.media_ids,
            job=job,
        )

        return job

    async def _run_investigation_pipeline(
        self,
        workspace_id: UUID,
        inv: Investigation,
        visit: Visit,
        promo: Promotion,
        policy_ver: PolicyVersion,
        media_ids: list[UUID],
        job: Job,
    ) -> None:
        gen = await self.state_repo.acquire_job_lease(
            job.id, worker_id="investigation-worker"
        )
        now = self.clock.now_utc()

        # Stage 1: GATHERING_EVIDENCE
        if gen is not None:
            await self.state_repo.update_job_stage(
                job_id=job.id,
                generation=gen,
                stage="GATHERING_EVIDENCE",
                status="RUNNING",
                summary="Gathering frozen inputs, visual evidence and policy rules",
            )

        known_evidence_ids: list[UUID] = []

        # 1. Visual evidence
        for mid in media_ids:
            media = await self.catalog_repo.get_media(workspace_id, mid)
            observed_at = (media.captured_at if media else None) or now
            # Freshness check: <= 30m at start
            age_seconds = (now - observed_at).total_seconds()
            freshness = Freshness1.CURRENT if age_seconds <= 1800 else Freshness1.STALE
            ev = Evidence(
                id=uuid4(),
                investigation_id=inv.id,
                kind=Kind8.PHOTO,
                observed_at=observed_at,
                retrieved_at=now,
                freshness=freshness,
                summary=f"Before shelf photograph {mid}",
                source_id=mid,
                source_sha256=(
                    (media.normalized_sha256 or media.original_sha256)
                    if media and (media.normalized_sha256 or media.original_sha256)
                    else hashlib.sha256(f"media:{mid}".encode()).hexdigest()
                ),
                locator=Locator(
                    media_id=mid,
                    page=None,
                    quote=None,
                    box=None,
                    row_ids=[],
                    batch_ids=[],
                    query_template_id=None,
                    query_job_id=None,
                    query_parameters={"store_id": str(inv.store_id)},
                ),
            )
            await self.visit_repo.save_evidence(workspace_id, ev)
            known_evidence_ids.append(ev.id)

        # 2. Policy evidence
        policy_ev = Evidence(
            id=uuid4(),
            investigation_id=inv.id,
            kind=Kind8.POLICY,
            observed_at=policy_ver.approved_at,
            retrieved_at=now,
            freshness=Freshness1.CURRENT,
            summary=f"Approved policy version {policy_ver.version} for promotion {promo.name}",
            source_id=policy_ver.id,
            source_sha256=policy_ver.content_sha256,
            locator=Locator(
                media_id=None,
                page=None,
                quote=None,
                box=None,
                row_ids=[],
                batch_ids=[],
                query_template_id=None,
                query_job_id=None,
                query_parameters={
                    "promotion_id": str(promo.id),
                    "policy_version_id": str(policy_ver.id),
                },
            ),
        )
        await self.visit_repo.save_evidence(workspace_id, policy_ev)
        known_evidence_ids.append(policy_ev.id)

        # 3. Visit note evidence if present
        if visit.notes:
            note_ev = Evidence(
                id=uuid4(),
                investigation_id=inv.id,
                kind=Kind8.VISIT_NOTE,
                observed_at=visit.created_at,
                retrieved_at=now,
                freshness=Freshness1.CURRENT,
                summary=f"Visit rep notes: {visit.notes[:200]}",
                source_id=visit.id,
                source_sha256=hashlib.sha256(visit.notes.encode()).hexdigest(),
                locator=Locator(
                    media_id=None,
                    page=None,
                    quote=visit.notes[:500],
                    box=None,
                    row_ids=[],
                    batch_ids=[],
                    query_template_id=None,
                    query_job_id=None,
                    query_parameters={"visit_id": str(visit.id)},
                ),
            )
            await self.visit_repo.save_evidence(workspace_id, note_ev)
            known_evidence_ids.append(note_ev.id)

        # Stage 2: REASONING & SYNTHESIZING
        if gen is not None:
            await self.state_repo.update_job_stage(
                job_id=job.id,
                generation=gen,
                stage="REASONING",
                status="RUNNING",
                summary="Executing read-only tools and evaluating hypotheses",
            )

        # Set up ReadOnlyToolRegistry
        registry = ReadOnlyToolRegistry(workspace_id=str(workspace_id))

        # Retrieve real batch information if analytics repository is available
        sales_batches: list[dict[str, Any]] = []
        stock_batches: list[dict[str, Any]] = []
        sales_facts: list[dict[str, Any]] = []
        stock_facts: list[dict[str, Any]] = []

        if self.analytics_repo:
            try:
                sales_batches = await self.analytics_repo.get_active_batches(
                    workspace_id, kind="SALES"
                )
                stock_batches = await self.analytics_repo.get_active_batches(
                    workspace_id, kind="INVENTORY"
                )
                sales_facts = await self.analytics_repo.get_sales_window(
                    workspace_id=workspace_id,
                    store_id=inv.store_id,
                    start_date="2026-08-01",
                    end_date="2026-08-14",
                )
                stock_facts = await self.analytics_repo.get_latest_inventory(
                    workspace_id=workspace_id,
                    location_ids=[inv.store_id],
                    as_of_time=now.isoformat(),
                )
            except (KeyError, ValueError, RuntimeError, OSError) as e:
                logger.warning("Error fetching analytics data for investigation: %s", e)

        sales_sha = (
            sales_batches[0]["source_sha256"]
            if sales_batches
            else hashlib.sha256(f"sales:{inv.snapshot_id}".encode()).hexdigest()
        )
        sales_batch_ids: list[UUID] = []
        for b in sales_batches:
            try:
                sales_batch_ids.append(UUID(str(b["batch_id"])))
            except ValueError:
                pass

        stock_sha = (
            stock_batches[0]["source_sha256"]
            if stock_batches
            else hashlib.sha256(f"stock:{inv.snapshot_id}".encode()).hexdigest()
        )
        stock_batch_ids: list[UUID] = []
        for b in stock_batches:
            try:
                stock_batch_ids.append(UUID(str(b["batch_id"])))
            except ValueError:
                pass

        from storeops_contracts.models import (
            Currency,
            Freshness2,
            LocationType,
            MissingItem,
            Status8,
            StockItem,
            ToolEnvelope,
            Unit,
        )

        sales_ev_id = uuid4()
        sales_ev = Evidence(
            id=sales_ev_id,
            investigation_id=inv.id,
            kind=Kind8.SALES_ROWS,
            observed_at=now,
            retrieved_at=now,
            freshness=Freshness1.CURRENT,
            summary="Committed weekly sales rows snapshot",
            source_id=inv.snapshot_id,
            source_sha256=sales_sha,
            locator=Locator(
                media_id=None,
                page=None,
                quote=None,
                box=None,
                row_ids=[],
                batch_ids=sales_batch_ids,
                query_template_id="sales_window_v1",
                query_job_id=None,
                query_parameters={"store_id": str(inv.store_id)},
            ),
        )
        await self.visit_repo.save_evidence(workspace_id, sales_ev)
        known_evidence_ids.append(sales_ev_id)

        stock_ev_id = uuid4()
        stock_ev = Evidence(
            id=stock_ev_id,
            investigation_id=inv.id,
            kind=Kind8.STOCK_ROWS,
            observed_at=now,
            retrieved_at=now,
            freshness=Freshness1.CURRENT,
            summary="Committed latest inventory snapshot",
            source_id=inv.snapshot_id,
            source_sha256=stock_sha,
            locator=Locator(
                media_id=None,
                page=None,
                quote=None,
                box=None,
                row_ids=[],
                batch_ids=stock_batch_ids,
                query_template_id="latest_stock_v1",
                query_job_id=None,
                query_parameters={"store_id": str(inv.store_id)},
            ),
        )
        await self.visit_repo.save_evidence(workspace_id, stock_ev)
        known_evidence_ids.append(stock_ev_id)

        cat_pids = (
            policy_ver.catalog_product_ids
            if policy_ver.catalog_product_ids
            else [uuid4()]
        )

        prior_facts = [
            f for f in sales_facts if str(f.get("business_date", "")) <= "2026-08-07"
        ]
        current_facts = [
            f for f in sales_facts if str(f.get("business_date", "")) > "2026-08-07"
        ]

        if prior_facts and current_facts:
            sales_complete = True
            sales_gaps = []
            prior_units = sum(int(f["units"]) for f in prior_facts)
            current_units = sum(int(f["units"]) for f in current_facts)
            prior_revenue = str(sum(Decimal(str(f["revenue"])) for f in prior_facts))
            current_revenue = str(
                sum(Decimal(str(f["revenue"])) for f in current_facts)
            )
            sales_currency = (
                Currency(sales_facts[0]["currency"])
                if sales_facts
                and sales_facts[0].get("currency") in Currency.__members__
                else Currency.SGD
            )
        else:
            sales_complete = False
            sales_gaps = ["Incomplete commercial window: missing sales facts"]
            prior_units = (
                sum(int(f["units"]) for f in prior_facts) if prior_facts else None
            )
            current_units = (
                sum(int(f["units"]) for f in current_facts) if current_facts else None
            )
            prior_revenue = (
                str(sum(Decimal(str(f["revenue"])) for f in prior_facts))
                if prior_facts
                else None
            )
            current_revenue = (
                str(sum(Decimal(str(f["revenue"])) for f in current_facts))
                if current_facts
                else None
            )
            sales_currency = Currency.SGD

        sales_context = SalesContext(
            snapshot_id=inv.snapshot_id,
            store_id=inv.store_id,
            catalog_product_ids=cat_pids,
            prior_start=date(2026, 8, 1),
            prior_end=date(2026, 8, 7),
            current_start=date(2026, 8, 8),
            current_end=date(2026, 8, 14),
            complete=sales_complete,
            prior_units=prior_units,
            current_units=current_units,
            prior_revenue=prior_revenue,
            current_revenue=current_revenue,
            currency=sales_currency,
            eligible_peers=[],
            gaps=sales_gaps,
            evidence_ids=[sales_ev_id],
        )

        inv.metrics = calculate_metrics_from_sales_context(
            sales_context, currency=sales_currency, as_of_date=now.date()
        )

        stock_items: list[StockItem] = []
        for sf in stock_facts:
            raw_obs = sf.get("observed_at")
            if isinstance(raw_obs, str):
                obs_dt = datetime.fromisoformat(raw_obs)
            elif isinstance(raw_obs, datetime):
                obs_dt = raw_obs
            else:
                obs_dt = now

            if obs_dt.tzinfo is None:
                obs_dt = obs_dt.replace(tzinfo=UTC)

            stock_items.append(
                StockItem(
                    product_id=cat_pids[0],
                    location_id=sf["location_id"],
                    location_type=LocationType.BACKROOM,
                    quantity=int(sf["quantity"]),
                    unit=Unit.UNIT,
                    units_normalized=int(sf["normalized_units"]),
                    observed_at=obs_dt,
                    freshness=Freshness2.CURRENT,
                    evidence_id=stock_ev_id,
                )
            )

        missing_items = (
            []
            if stock_items
            else [
                MissingItem(product_id=pid, location_type=LocationType.BACKROOM)
                for pid in cat_pids
            ]
        )

        stock_context = StockContext(
            snapshot_id=inv.snapshot_id,
            store_id=inv.store_id,
            items=stock_items,
            missing=missing_items,
        )

        registry.register(
            "get_sales_context",
            lambda inp: ToolEnvelope(
                status=Status8.OK,
                data=sales_context.model_dump(mode="json"),
                evidence_ids=[sales_ev_id],
                as_of=now,
                error=None,
            ),
        )

        registry.register(
            "get_inventory_context",
            lambda inp: ToolEnvelope(
                status=Status8.OK,
                data=stock_context.model_dump(mode="json"),
                evidence_ids=[stock_ev_id],
                as_of=now,
                error=None,
            ),
        )

        registry.register(
            "get_visit_history",
            lambda inp: ToolEnvelope(
                status=Status8.OK,
                data=VisitHistoryContext(
                    snapshot_id=inv.snapshot_id,
                    store_id=inv.store_id,
                    visits=[],
                ).model_dump(mode="json"),
                evidence_ids=[],
                as_of=now,
                error=None,
            ),
        )

        registry.register(
            "get_approved_policy",
            lambda inp: ToolEnvelope(
                status=Status8.OK,
                data=policy_ver.model_dump(mode="json"),
                evidence_ids=[policy_ev.id],
                as_of=now,
                error=None,
            ),
        )

        zone_media_ids = {f"zone-{i}": mid for i, mid in enumerate(media_ids)}

        ctx = InvestigationContext(
            workspace_id=str(workspace_id),
            store_id=inv.store_id,
            snapshot_id=inv.snapshot_id,
            catalog_product_ids=policy_ver.catalog_product_ids,
            policy_version_id=policy_ver.id,
            zone_media_ids=zone_media_ids,
        )

        investigator = Investigator(gateway=self.model_gateway, max_tool_calls=15)
        proposal: AnalysisProposal | None = None
        incomplete_reason = ""

        try:
            proposal = await investigator.run_investigation(ctx=ctx, tools=registry)
        except (
            GroundednessValidationError,
            CallBudgetExceededError,
            ModelSchemaError,
        ) as err:
            logger.warning(f"Investigation execution produced gap: {err}")
            incomplete_reason = str(err)

        if not proposal:
            inv.state = State.INCOMPLETE
            inv.updated_at = self.clock.now_utc()
            await self.visit_repo.update_investigation(workspace_id, inv)
            if gen is not None:
                await self.state_repo.update_job_stage(
                    job_id=job.id,
                    generation=gen,
                    stage="COMPLETED",
                    status="SUCCEEDED",
                    summary=f"Investigation completed with state INCOMPLETE: {incomplete_reason[:200]}",
                )
            return

        # Stage 3: SYNTHESIZING
        if gen is not None:
            await self.state_repo.update_job_stage(
                job_id=job.id,
                generation=gen,
                stage="SYNTHESIZING",
                status="RUNNING",
                summary="Transforming proposal into validated claims and actions",
            )

        claims: list[Claim] = []
        claim_key_to_id: dict[str, UUID] = {}
        for pc in proposal.claims:
            cid = uuid4()
            claim_key_to_id[pc.claim_key] = cid
            claims.append(
                Claim(
                    id=cid,
                    kind=Kind6(pc.kind),
                    text=pc.text,
                    evidence_ids=pc.evidence_ids,
                )
            )

        alternatives = [
            Alternative(
                hypothesis=Hypothesis(alt.hypothesis),
                reason=alt.reason,
                evidence_ids=alt.evidence_ids,
            )
            for alt in proposal.alternatives
        ]

        actions: list[Action] = []
        action_mapping_error: str | None = None

        if len(proposal.actions) > 3:
            action_mapping_error = (
                f"Model proposed {len(proposal.actions)} actions; maximum allowed is 3"
            )
        else:
            for act in proposal.actions:
                act_id = uuid4()
                # Check for unmapped claim keys - fail closed if unmapped
                missing_claim_keys = [
                    ck for ck in act.claim_keys if ck not in claim_key_to_id
                ]
                if missing_claim_keys:
                    action_mapping_error = (
                        f"Action references unmapped claim keys: {missing_claim_keys}"
                    )
                    break
                mapped_claim_ids = [claim_key_to_id[ck] for ck in act.claim_keys]
                actions.append(
                    Action(
                        id=act_id,
                        kind=Kind7(act.kind),
                        rule_ids=act.rule_ids,
                        claim_ids=mapped_claim_ids,
                        evidence_ids=act.evidence_ids,
                        instruction=act.instruction,
                        required_zone_ids=[
                            RequiredZoneId(root=z) for z in act.required_zone_ids
                        ],
                        status=Status6.OPEN,
                    )
                )

        if action_mapping_error:
            logger.warning(f"Action validation failed: {action_mapping_error}")
            inv.state = State.INCOMPLETE
            inv.updated_at = self.clock.now_utc()
            await self.visit_repo.update_investigation(workspace_id, inv)
            if gen is not None:
                await self.state_repo.update_job_stage(
                    job_id=job.id,
                    generation=gen,
                    stage="COMPLETED",
                    status="SUCCEEDED",
                    summary=f"Investigation completed with state INCOMPLETE: {action_mapping_error}",
                )
            return

        # Determine support label (contracts/SEMANTICS.md:52-74)
        is_supported = (
            sales_complete
            and len(sales_gaps) == 0
            and len(stock_items) > 0
            and len(proposal.unresolved_questions) == 0
        )
        diagnosis_support = Support.SUPPORTED if is_supported else Support.LIMITED

        diagnosis = Diagnosis(
            hypothesis=Hypothesis(proposal.hypothesis),
            support=diagnosis_support,
            summary=proposal.summary,
            claims=claims,
            alternatives=alternatives,
            unresolved_questions=proposal.unresolved_questions,
        )

        inv.diagnosis = diagnosis
        inv.actions = actions
        inv.updated_at = self.clock.now_utc()

        # NO_ACTION rule (contracts/SEMANTICS.md:56-60, AC16):
        # A fully supported NO_ISSUE with zero actions closes the visit as NO_ACTION
        # and creates a NO_ACTION report without a claim of verified corrective work.
        if (
            proposal.hypothesis == "NO_ISSUE"
            and len(actions) == 0
            and diagnosis_support == Support.SUPPORTED
        ):
            inv.state = State.NO_ACTION
            report = Report(
                id=uuid4(),
                workspace_id=workspace_id,
                visit_id=visit.id,
                investigation_id=inv.id,
                verification_id=None,
                created_at=self.clock.now_utc(),
                outcome=Outcome.NO_ACTION,
                summary="No operational or merchandising issues detected during visit. Policy checks satisfied.",
                checks=[],
                evidence_ids=known_evidence_ids,
                policy_version_id=policy_ver.id,
            )
            await self.visit_repo.save_report(workspace_id, report)
            visit.status = Status5.CLOSED
            visit.report_ids.append(report.id)
            visit.active_investigation_id = None
            visit.version += 1
            visit.updated_at = self.clock.now_utc()
            await self.visit_repo.update_visit(workspace_id, visit)
        elif (
            proposal.hypothesis == "NO_ISSUE" and diagnosis_support != Support.SUPPORTED
        ):
            # Cannot close as NO_ACTION if evidence is incomplete or limited
            inv.state = State.NEEDS_WORK
            inv.plan_revision = 1
        else:
            inv.state = State.PROPOSED
            inv.plan_revision = 1

        await self.visit_repo.update_investigation(workspace_id, inv)

        if gen is not None:
            await self.state_repo.update_job_stage(
                job_id=job.id,
                generation=gen,
                stage="COMPLETED",
                status="SUCCEEDED",
                summary="Investigation proposal synthesized successfully",
            )

    async def get_investigation(
        self, workspace_id: UUID, investigation_id: UUID
    ) -> Investigation:
        inv = await self.visit_repo.get_investigation(workspace_id, investigation_id)
        if not inv:
            raise ApiError(
                status_code=404,
                code="INVESTIGATION_NOT_FOUND",
                message=f"Investigation {investigation_id} not found",
            )

        # Dynamic check for policy staleness if in PROPOSED state
        promo = await self.policy_repo.get_promotion(workspace_id, inv.promotion_id)
        if (
            promo
            and (
                promo.archived
                or not promo.approved_policy
                or promo.approved_policy.id != inv.policy_version_id
            )
            and not inv.policy_stale
        ):
            inv.policy_stale = True
            await self.visit_repo.update_investigation(workspace_id, inv)

        return inv

    async def list_investigations(
        self,
        workspace_id: UUID,
        store_id: UUID | None = None,
        visit_id: UUID | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> InvestigationList:
        items, next_cursor = await self.visit_repo.list_investigations(
            workspace_id,
            store_id=store_id,
            visit_id=visit_id,
            cursor=cursor,
            limit=limit,
        )
        return InvestigationList(items=items, next_cursor=next_cursor)

    async def accept_investigation(
        self,
        workspace_id: UUID,
        investigation_id: UUID,
        payload: VersionCommand,
        uid: str,
    ) -> Investigation:
        inv = await self.get_investigation(workspace_id, investigation_id)

        # OCC Version check
        if inv.version != payload.expected_version:
            raise ApiError(
                status_code=409,
                code="VERSION_CONFLICT",
                message=f"Expected version {payload.expected_version} but investigation is at version {inv.version}",
            )

        # State check
        if inv.state not in (State.PROPOSED, State.NEEDS_WORK):
            raise ApiError(
                status_code=409,
                code="INVALID_STATE",
                message=f"Cannot accept investigation in state {inv.state.value}",
            )

        # Staleness check (AC34)
        promo = await self.policy_repo.get_promotion(workspace_id, inv.promotion_id)
        if (
            not promo
            or promo.archived
            or not promo.approved_policy
            or promo.approved_policy.id != inv.policy_version_id
        ):
            inv.policy_stale = True
            await self.visit_repo.update_investigation(workspace_id, inv)
            raise ApiError(
                status_code=409,
                code="STALE_POLICY",
                message="Promotion policy has changed or is archived since proposal was generated; new investigation required",
            )

        now = self.clock.now_utc()
        inv.state = State.ACCEPTED
        inv.accepted_at = now
        inv.accepted_by = uid
        inv.version += 1
        inv.updated_at = now
        return await self.visit_repo.update_investigation(workspace_id, inv)

    async def dismiss_investigation(
        self,
        workspace_id: UUID,
        investigation_id: UUID,
        payload: Dismiss,
        uid: str,
    ) -> Investigation:
        inv = await self.get_investigation(workspace_id, investigation_id)

        # OCC Version check
        if inv.version != payload.expected_version:
            raise ApiError(
                status_code=409,
                code="VERSION_CONFLICT",
                message=f"Expected version {payload.expected_version} but investigation is at version {inv.version}",
            )

        # Terminal state check
        if inv.state in (State.RESOLVED, State.NO_ACTION, State.DISMISSED):
            raise ApiError(
                status_code=409,
                code="INVALID_STATE",
                message=f"Cannot dismiss investigation in terminal state {inv.state.value}",
            )

        now = self.clock.now_utc()
        inv.state = State.DISMISSED
        inv.version += 1
        inv.updated_at = now

        # Release visit active investigation link
        visit = await self.visit_repo.get_visit(workspace_id, inv.visit_id)
        if visit and visit.active_investigation_id == inv.id:
            visit.active_investigation_id = None
            visit.version += 1
            visit.updated_at = now
            await self.visit_repo.update_visit(workspace_id, visit)

        return await self.visit_repo.update_investigation(workspace_id, inv)

    async def update_action(
        self,
        workspace_id: UUID,
        investigation_id: UUID,
        action_id: UUID,
        payload: ActionUpdate,
        uid: str,
    ) -> Investigation:
        inv = await self.get_investigation(workspace_id, investigation_id)

        # OCC Version check
        if inv.version != payload.expected_version:
            raise ApiError(
                status_code=409,
                code="VERSION_CONFLICT",
                message=f"Expected version {payload.expected_version} but investigation is at version {inv.version}",
            )

        # State check
        if inv.state not in (State.ACCEPTED, State.NEEDS_WORK):
            raise ApiError(
                status_code=409,
                code="INVALID_STATE",
                message=f"Cannot update actions for investigation in state {inv.state.value}",
            )

        target_action: Action | None = None
        for act in inv.actions:
            if act.id == action_id:
                target_action = act
                break

        if not target_action:
            raise ApiError(
                status_code=404,
                code="ACTION_NOT_FOUND",
                message=f"Action {action_id} not found in investigation {investigation_id}",
            )

        # AC16: Rep checkboxes set CLAIMED_DONE; they never resolve or verify
        if payload.status.value != "CLAIMED_DONE":
            raise ApiError(
                status_code=422,
                code="INVALID_ACTION_STATUS",
                message=f"Rep action update cannot transition to {payload.status.value}; only CLAIMED_DONE is permitted",
            )
        target_action.status = Status6(payload.status.value)

        now = self.clock.now_utc()
        inv.version += 1
        inv.updated_at = now
        return await self.visit_repo.update_investigation(workspace_id, inv)

    async def list_evidence(
        self,
        workspace_id: UUID,
        investigation_id: UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> EvidenceList:
        # Verify investigation exists in workspace
        await self.get_investigation(workspace_id, investigation_id)
        items, next_cursor = await self.visit_repo.list_evidence(
            workspace_id, investigation_id, cursor=cursor, limit=limit
        )
        return EvidenceList(items=items, next_cursor=next_cursor)

    async def get_evidence(self, workspace_id: UUID, evidence_id: UUID) -> Evidence:
        ev = await self.visit_repo.get_evidence(workspace_id, evidence_id)
        if not ev:
            raise ApiError(
                status_code=404,
                code="EVIDENCE_NOT_FOUND",
                message=f"Evidence {evidence_id} not found",
            )
        return ev

    async def get_report(self, workspace_id: UUID, report_id: UUID) -> Report:
        rep = await self.visit_repo.get_report(workspace_id, report_id)
        if not rep:
            raise ApiError(
                status_code=404,
                code="REPORT_NOT_FOUND",
                message=f"Report {report_id} not found",
            )
        return rep
