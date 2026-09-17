import hashlib
import json
from datetime import date
from uuid import UUID, uuid4

from storeops_contracts.models import (
    ApprovePolicy,
    ExtractionGap,
    Job,
    Kind4,
    Kind5,
    PolicySource,
    PolicyVersion,
    PolicyVersionList,
    Promotion,
    PromotionCreate,
    PromotionList,
    PromotionUpdate,
    ResourceType,
    Rule,
    Status1,
    Status2,
    Type2,
    ZoneKind,
)

from apps.api.ai.extract import extract_merchandising_policy
from apps.api.modules.catalog.repository import CatalogRepository
from apps.api.modules.policies.repository import PolicyRepository
from apps.api.ports.blob import BlobRepository
from apps.api.ports.clock import Clock
from apps.api.ports.model import ModelGateway
from apps.api.ports.state import StateRepository, VersionConflictError


class PolicyServiceError(Exception):
    def __init__(
        self, message: str, status_code: int = 400, code: str = "BAD_REQUEST"
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class NotFoundError(PolicyServiceError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=404, code="NOT_FOUND")


class ValidationError(PolicyServiceError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422, code="VALIDATION_FAILED")


class ConflictError(PolicyServiceError):
    def __init__(self, message: str, code: str = "PROMOTION_ARCHIVED") -> None:
        super().__init__(message, status_code=409, code=code)


def compute_policy_content_sha256(
    promotion_id: UUID,
    version: int,
    starts_on: date,
    ends_on: date,
    store_ids: list[UUID],
    catalog_product_ids: list[UUID],
    rules: list[Rule],
) -> str:
    """Compute deterministic SHA-256 hex digest for immutable policy content."""
    canonical_dict = {
        "promotion_id": str(promotion_id),
        "version": version,
        "starts_on": str(starts_on),
        "ends_on": str(ends_on),
        "store_ids": sorted(str(s) for s in store_ids),
        "catalog_product_ids": sorted(str(p) for p in catalog_product_ids),
        "rules": sorted(
            [
                {
                    "rule_id": str(r.rule_id),
                    "kind": r.kind.value,
                    "zone_id": r.zone_id,
                    "zone_kind": r.zone_kind.value,
                    "product_id": str(r.product_id) if r.product_id else None,
                    "min_facings": r.min_facings,
                    "source": {
                        "kind": r.source.kind.value,
                        "media_id": str(r.source.media_id)
                        if r.source.media_id
                        else None,
                        "page": r.source.page,
                        "quote": r.source.quote,
                        "reviewer_note": r.source.reviewer_note,
                    },
                }
                for r in rules
            ],
            key=lambda item: str(item["rule_id"]),
        ),
    }
    encoded = json.dumps(canonical_dict, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class PolicyService:
    def __init__(
        self,
        repo: PolicyRepository,
        catalog_repo: CatalogRepository,
        state_repo: StateRepository,
        blob_repo: BlobRepository,
        model_gateway: ModelGateway,
        clock: Clock,
    ) -> None:
        self.repo = repo
        self.catalog_repo = catalog_repo
        self.state_repo = state_repo
        self.blob_repo = blob_repo
        self.model_gateway = model_gateway
        self.clock = clock

    async def list_promotions(
        self,
        workspace_id: UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> PromotionList:
        items, next_cursor = await self.repo.list_promotions(
            workspace_id, cursor=cursor, limit=limit
        )
        return PromotionList(items=items, next_cursor=next_cursor)

    async def get_promotion(self, workspace_id: UUID, promotion_id: UUID) -> Promotion:
        promo = await self.repo.get_promotion(workspace_id, promotion_id)
        if not promo:
            raise NotFoundError(f"Promotion {promotion_id} not found")
        return promo

    async def create_promotion(
        self, workspace_id: UUID, payload: PromotionCreate
    ) -> Promotion:
        # 1. Validate dates
        if payload.starts_on > payload.ends_on:
            raise ValidationError("starts_on cannot be after ends_on")

        # 2. Validate stores
        for store_id in payload.store_ids:
            store = await self.catalog_repo.get_store(workspace_id, store_id)
            if not store or not store.active:
                raise ValidationError(
                    f"Store {store_id} not found or inactive in workspace"
                )

        # 3. Validate agreement media if provided
        if payload.agreement_media_id is not None:
            media = await self.catalog_repo.get_media(
                workspace_id, payload.agreement_media_id
            )
            if not media:
                raise ValidationError(
                    f"Agreement media {payload.agreement_media_id} not found"
                )
            if media.status != Status1.READY:
                raise ValidationError(
                    f"Agreement media {payload.agreement_media_id} is not READY (status: {media.status})"
                )

        now = self.clock.now_utc()
        promo = Promotion(
            id=uuid4(),
            workspace_id=workspace_id,
            version=1,
            created_at=now,
            updated_at=now,
            name=payload.name,
            starts_on=payload.starts_on,
            ends_on=payload.ends_on,
            store_ids=payload.store_ids,
            agreement_media_id=payload.agreement_media_id,
            archived=False,
            draft_revision=1,
            extracted_rules=[],
            extraction_gaps=[],
            approved_policy=None,
        )
        return await self.repo.create_promotion(workspace_id, promo)

    async def update_promotion(
        self, workspace_id: UUID, promotion_id: UUID, payload: PromotionUpdate
    ) -> Promotion:
        promo = await self.get_promotion(workspace_id, promotion_id)

        # Concurrency check
        if promo.version != payload.expected_version:
            raise VersionConflictError(
                message=f"Expected version {payload.expected_version} but promotion is at version {promo.version}",
                code="VERSION_CONFLICT",
            )

        # Dates validation
        new_starts = (
            payload.starts_on if payload.starts_on is not None else promo.starts_on
        )
        new_ends = payload.ends_on if payload.ends_on is not None else promo.ends_on
        if new_starts > new_ends:
            raise ValidationError("starts_on cannot be after ends_on")
        promo.starts_on = new_starts
        promo.ends_on = new_ends

        if payload.name is not None:
            promo.name = payload.name

        if payload.store_ids is not None:
            for store_id in payload.store_ids:
                store = await self.catalog_repo.get_store(workspace_id, store_id)
                if not store or not store.active:
                    raise ValidationError(
                        f"Store {store_id} not found or inactive in workspace"
                    )
            promo.store_ids = payload.store_ids

        if "agreement_media_id" in payload.model_fields_set:
            if payload.agreement_media_id is not None:
                media = await self.catalog_repo.get_media(
                    workspace_id, payload.agreement_media_id
                )
                if not media:
                    raise ValidationError(
                        f"Agreement media {payload.agreement_media_id} not found"
                    )
                if media.status != Status1.READY:
                    raise ValidationError(
                        f"Agreement media {payload.agreement_media_id} is not READY (status: {media.status})"
                    )
                promo.agreement_media_id = payload.agreement_media_id
            else:
                promo.agreement_media_id = None

        if payload.archived is not None:
            promo.archived = payload.archived

        promo.version += 1
        promo.draft_revision += 1
        promo.updated_at = self.clock.now_utc()
        return await self.repo.update_promotion(workspace_id, promo)

    async def extract_policy(
        self,
        workspace_id: UUID,
        promotion_id: UUID,
        expected_version: int,
        uid: str,
    ) -> Job:
        """Trigger policy rule extraction from agreement media.

        Execution profile note:
        In the default LOCAL in-memory profile, the job record is created in StateRepository with
        stage="QUEUED", processed inline, and returned with terminal stage/status.
        In the CLOUD / worker deployment profile, this endpoint returns 202 with QUEUED job and
        delegates processing to worker outbox handlers.
        """
        promo = await self.get_promotion(workspace_id, promotion_id)

        if promo.archived:
            raise ConflictError("Cannot extract policy on an archived promotion")

        if promo.version != expected_version:
            raise VersionConflictError(
                message=f"Expected version {expected_version} but promotion is at version {promo.version}",
                code="VERSION_CONFLICT",
            )

        if not promo.agreement_media_id:
            raise ValidationError(
                "Promotion does not have an attached agreement media file"
            )

        media = await self.catalog_repo.get_media(
            workspace_id, promo.agreement_media_id
        )
        if not media:
            raise ValidationError("Agreement media not found")
        if media.status != Status1.READY:
            raise ValidationError("Agreement media is not in READY status")

        # Read PDF bytes from blob repository
        try:
            pdf_bytes = await self.blob_repo.read_bytes(media.id)
        except (FileNotFoundError, OSError):
            raise ValidationError("Agreement PDF content not found in storage")

        # Read active catalog products with pagination
        active_product_ids: list[UUID] = []
        prod_cursor = None
        while True:
            products, prod_cursor = await self.catalog_repo.list_products(
                workspace_id, cursor=prod_cursor, limit=100
            )
            active_product_ids.extend([p.id for p in products if p.active])
            if not prod_cursor:
                break

        now = self.clock.now_utc()
        job_id = uuid4()
        job = Job(
            id=job_id,
            workspace_id=workspace_id,
            version=1,
            created_at=now,
            updated_at=now,
            type=Type2.POLICY_EXTRACT,
            status=Status2.QUEUED,
            resource_id=promo.id,
            resource_type=ResourceType.PROMOTION,
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

        # Call extraction gateway
        try:
            extraction = await extract_merchandising_policy(
                gateway=self.model_gateway,
                pdf_bytes=pdf_bytes,
                media_id=media.id,
                catalog_product_ids=active_product_ids,
                store_ids=promo.store_ids,
            )
        except Exception as exc:
            gen = await self.state_repo.acquire_job_lease(
                job.id, worker_id="policy-extractor"
            )
            if gen is not None:
                await self.state_repo.update_job_stage(
                    job_id=job.id,
                    generation=gen,
                    stage="FAILED",
                    status="FAILED",
                    summary=f"Extraction failed: {exc}",
                )
            raise

        # Map rules per contracts/SEMANTICS.md:46-47:
        # Incomplete proposals with unresolved fields remain extraction gaps, not invalid Rule DTOs.
        extracted_rules: list[Rule] = []
        proposal_gaps: list[ExtractionGap] = []
        for er in extraction.rules:
            rule_kind = Kind5(er.kind)
            zk = ZoneKind(er.zone_kind) if er.zone_kind is not None else None

            is_valid = True
            gap_reason = ""

            if not er.zone_id:
                is_valid = False
                gap_reason = "Missing zone_id"
            elif (
                not er.source_quote
                or not er.source_quote.strip()
                or not (1 <= er.source_page <= 10)
            ):
                is_valid = False
                gap_reason = "Invalid source citation bounds"
            elif rule_kind == Kind5.MIN_FACINGS:
                if zk != ZoneKind.SHELF:
                    is_valid = False
                    gap_reason = "MIN_FACINGS must be in SHELF zone"
                elif er.min_facings is None or er.min_facings <= 0:
                    is_valid = False
                    gap_reason = "MIN_FACINGS min_facings must be > 0"
                elif (
                    er.product_id is not None
                    and er.product_id not in active_product_ids
                ):
                    is_valid = False
                    gap_reason = (
                        f"MIN_FACINGS references unknown product {er.product_id}"
                    )
            elif rule_kind == Kind5.REQUIRED_PRODUCT:
                if zk != ZoneKind.SHELF:
                    is_valid = False
                    gap_reason = "REQUIRED_PRODUCT must be in SHELF zone"
                elif er.product_id is None:
                    is_valid = False
                    gap_reason = "REQUIRED_PRODUCT requires product_id"
                elif er.product_id not in active_product_ids:
                    is_valid = False
                    gap_reason = (
                        f"REQUIRED_PRODUCT references unknown product {er.product_id}"
                    )
                elif er.min_facings is not None:
                    is_valid = False
                    gap_reason = "REQUIRED_PRODUCT must not specify min_facings"
            elif rule_kind == Kind5.REQUIRED_DISPLAY:
                if zk != ZoneKind.DISPLAY:
                    is_valid = False
                    gap_reason = "REQUIRED_DISPLAY must be in DISPLAY zone"
                elif er.product_id is not None:
                    is_valid = False
                    gap_reason = "REQUIRED_DISPLAY must not specify product_id"
                elif er.min_facings is not None:
                    is_valid = False
                    gap_reason = "REQUIRED_DISPLAY must not specify min_facings"

            if not is_valid:
                proposal_gaps.append(
                    ExtractionGap(
                        root=f"Rule proposal gap ({gap_reason}): {er.source_quote[:200]}"
                    )
                )
            else:
                rule = Rule(
                    rule_id=uuid4(),
                    kind=rule_kind,
                    zone_id=er.zone_id,
                    zone_kind=zk,
                    product_id=er.product_id,
                    min_facings=er.min_facings,
                    source=PolicySource(
                        kind=Kind4.DOCUMENT,
                        media_id=media.id,
                        page=er.source_page,
                        quote=er.source_quote,
                        reviewer_note=None,
                    ),
                )
                extracted_rules.append(rule)

        # Map gaps
        gaps: list[ExtractionGap] = [ExtractionGap(root=gap) for gap in extraction.gaps]
        gaps.extend(proposal_gaps)

        # Update promotion draft (NO policy becomes approved automatically!)
        promo.extracted_rules = extracted_rules
        promo.extraction_gaps = gaps
        promo.draft_revision += 1
        promo.version += 1
        promo.updated_at = self.clock.now_utc()
        await self.repo.update_promotion(workspace_id, promo)

        # Update Job to SUCCEEDED
        gen = await self.state_repo.acquire_job_lease(
            job.id, worker_id="policy-extractor"
        )
        if gen is not None:
            await self.state_repo.update_job_stage(
                job_id=job.id,
                generation=gen,
                stage="EXTRACTED",
                status="SUCCEEDED",
                summary=f"Extracted {len(extracted_rules)} rules and {len(gaps)} gaps",
            )
            updated_job = await self.state_repo.get_job(workspace_id, job.id)
            if updated_job:
                job = updated_job

        return job

    async def approve_policy(
        self,
        workspace_id: UUID,
        promotion_id: UUID,
        payload: ApprovePolicy,
        user_uid: str,
    ) -> PolicyVersion:
        promo = await self.get_promotion(workspace_id, promotion_id)

        if promo.archived:
            raise ConflictError("Cannot approve policy on an archived promotion")

        if promo.version != payload.expected_version:
            raise VersionConflictError(
                message=f"Expected version {payload.expected_version} but promotion is at version {promo.version}",
                code="VERSION_CONFLICT",
            )

        # 1. Validate catalog_product_ids
        for pid in payload.catalog_product_ids:
            product = await self.catalog_repo.get_product(workspace_id, pid)
            if not product:
                raise ValidationError(f"Catalog product {pid} not found in workspace")
            if not product.active:
                raise ValidationError(
                    f"Catalog product {pid} ({product.name}) is archived and cannot be used in policy"
                )

        catalog_product_ids_set = set(payload.catalog_product_ids)

        # 2. Validate rules
        rule_ids = [r.rule_id for r in payload.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValidationError("Duplicate rule IDs found in policy rules")

        for r in payload.rules:
            # Rule kind predicates per SEMANTICS.md
            if r.kind == Kind5.MIN_FACINGS:
                if r.zone_kind != ZoneKind.SHELF:
                    raise ValidationError(
                        f"Rule {r.rule_id}: MIN_FACINGS requires zone_kind=SHELF, got {r.zone_kind}"
                    )
                if r.min_facings is None or r.min_facings <= 0:
                    raise ValidationError(
                        f"Rule {r.rule_id}: MIN_FACINGS requires min_facings > 0"
                    )
                if r.product_id is not None:
                    if r.product_id not in catalog_product_ids_set:
                        raise ValidationError(
                            f"Rule {r.rule_id} references product {r.product_id} not present in catalog_product_ids"
                        )
                    prod = await self.catalog_repo.get_product(
                        workspace_id, r.product_id
                    )
                    if not prod or not prod.active:
                        raise ValidationError(
                            f"Rule {r.rule_id} references unknown or archived product {r.product_id}"
                        )

            elif r.kind == Kind5.REQUIRED_PRODUCT:
                if r.zone_kind != ZoneKind.SHELF:
                    raise ValidationError(
                        f"Rule {r.rule_id}: REQUIRED_PRODUCT requires zone_kind=SHELF, got {r.zone_kind}"
                    )
                if r.product_id is None:
                    raise ValidationError(
                        f"Rule {r.rule_id}: REQUIRED_PRODUCT requires non-null product_id"
                    )
                if r.product_id not in catalog_product_ids_set:
                    raise ValidationError(
                        f"Rule {r.rule_id} references product {r.product_id} not present in catalog_product_ids"
                    )
                if r.min_facings is not None:
                    raise ValidationError(
                        f"Rule {r.rule_id}: REQUIRED_PRODUCT requires min_facings to be null"
                    )
                prod = await self.catalog_repo.get_product(workspace_id, r.product_id)
                if not prod or not prod.active:
                    raise ValidationError(
                        f"Rule {r.rule_id} references unknown or archived product {r.product_id}"
                    )

            elif r.kind == Kind5.REQUIRED_DISPLAY:
                if r.zone_kind != ZoneKind.DISPLAY:
                    raise ValidationError(
                        f"Rule {r.rule_id}: REQUIRED_DISPLAY requires zone_kind=DISPLAY, got {r.zone_kind}"
                    )
                if r.product_id is not None:
                    raise ValidationError(
                        f"Rule {r.rule_id}: REQUIRED_DISPLAY requires product_id to be null"
                    )
                if r.min_facings is not None:
                    raise ValidationError(
                        f"Rule {r.rule_id}: REQUIRED_DISPLAY requires min_facings to be null"
                    )

            # Source predicates
            if r.source.kind == Kind4.DOCUMENT:
                if not promo.agreement_media_id:
                    raise ValidationError(
                        f"Rule {r.rule_id}: Promotion does not have an attached agreement media"
                    )
                if r.source.media_id != promo.agreement_media_id:
                    raise ValidationError(
                        f"Rule {r.rule_id}: DOCUMENT source media_id {r.source.media_id} does not match promotion agreement {promo.agreement_media_id}"
                    )
                agreement_media = await self.catalog_repo.get_media(
                    workspace_id, r.source.media_id
                )
                if not agreement_media:
                    raise ValidationError(
                        f"Rule {r.rule_id}: DOCUMENT source media {r.source.media_id} not found"
                    )
                if agreement_media.status != Status1.READY:
                    raise ValidationError(
                        f"Rule {r.rule_id}: DOCUMENT source media {r.source.media_id} is not in READY status"
                    )
                if r.source.page is None or r.source.page < 1 or r.source.page > 10:
                    raise ValidationError(
                        f"Rule {r.rule_id}: DOCUMENT source requires page between 1 and 10"
                    )
                if not r.source.quote or not r.source.quote.strip():
                    raise ValidationError(
                        f"Rule {r.rule_id}: DOCUMENT source requires nonempty quote"
                    )
            elif r.source.kind == Kind4.MANUAL:
                if not r.source.reviewer_note or not r.source.reviewer_note.strip():
                    raise ValidationError(
                        f"Rule {r.rule_id}: MANUAL source requires reviewer_note"
                    )
                if (
                    r.source.media_id is not None
                    or r.source.page is not None
                    or r.source.quote is not None
                ):
                    raise ValidationError(
                        f"Rule {r.rule_id}: MANUAL source must not have media_id, page, or quote"
                    )

        # 3. Calculate version number
        next_version = promo.approved_policy.version + 1 if promo.approved_policy else 1

        # 4. Compute deterministic content sha256
        content_sha256 = compute_policy_content_sha256(
            promotion_id=promo.id,
            version=next_version,
            starts_on=promo.starts_on,
            ends_on=promo.ends_on,
            store_ids=promo.store_ids,
            catalog_product_ids=payload.catalog_product_ids,
            rules=payload.rules,
        )

        now = self.clock.now_utc()
        policy_version = PolicyVersion(
            id=uuid4(),
            promotion_id=promo.id,
            version=next_version,
            rules=payload.rules,
            catalog_product_ids=payload.catalog_product_ids,
            store_ids=promo.store_ids,
            starts_on=promo.starts_on,
            ends_on=promo.ends_on,
            approved_at=now,
            approved_by=user_uid,
            content_sha256=content_sha256,
        )
        created_version = await self.repo.create_policy_version(
            workspace_id, policy_version
        )

        # 5. Update promotion: points to new approved_policy, increment version
        promo.approved_policy = created_version
        promo.version += 1
        promo.updated_at = now
        await self.repo.update_promotion(workspace_id, promo)

        return created_version

    async def list_policy_versions(
        self,
        workspace_id: UUID,
        promotion_id: UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> PolicyVersionList:
        await self.get_promotion(workspace_id, promotion_id)
        items, next_cursor = await self.repo.list_policy_versions(
            workspace_id, promotion_id, cursor=cursor, limit=limit
        )
        return PolicyVersionList(items=items, next_cursor=next_cursor)
