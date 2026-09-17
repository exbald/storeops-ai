import logging
from uuid import UUID, uuid4

from pydantic import ValidationError
from storeops_contracts.models import (
    Evidence,
    Freshness1,
    Investigation,
    Job,
    Kind8,
    Locator,
    Media,
    Outcome,
    Report,
    ResourceType,
    Result1,
    State,
    Status1,
    Status2,
    Status5,
    Status6,
    Type2,
    Verification,
    VerificationList,
    VerifyRequest,
    Visit,
)

from apps.api.ai.extract import extract_image_observations
from apps.api.ai.gateway import ModelGatewayError, ModelSchemaError
from apps.api.ai.schemas import ImageObservation
from apps.api.ai.verifier.evaluator import ExecutionVerifier, VerifierGroundingError
from apps.api.core.errors import ApiError
from apps.api.modules.verification.ports import (
    VerificationCatalogPort,
    VerificationPolicyPort,
    VerificationVisitPort,
)
from apps.api.modules.verification.repository import VerificationRepository
from apps.api.ports.blob import BlobRepository
from apps.api.ports.clock import SystemClock
from apps.api.ports.model import ModelGateway
from apps.api.ports.state import StateRepository

logger = logging.getLogger(__name__)


class VerificationService:
    """Service orchestrating execution verification and saga-coordinated resolution.

    Implementation uses sequential writes with compensating rollbacks: non-PASS outcomes
    transition the investigation to NEEDS_WORK; PASS outcomes resolve actions, investigation,
    and visit in sequence with rollback compensation if a downstream write fails.
    OCC version fencing is evaluated in-process for LOCAL and transactional adapters for CLOUD.
    """

    def __init__(
        self,
        verification_repo: VerificationRepository,
        visit_port: VerificationVisitPort,
        policy_port: VerificationPolicyPort,
        catalog_port: VerificationCatalogPort,
        blob_repo: BlobRepository,
        state_repo: StateRepository,
        model_gateway: ModelGateway,
        clock: SystemClock,
    ) -> None:
        self.verification_repo = verification_repo
        self.visit_port = visit_port
        self.policy_port = policy_port
        self.catalog_port = catalog_port
        self.blob_repo = blob_repo
        self.state_repo = state_repo
        self.model_gateway = model_gateway
        self.clock = clock

    async def verify_investigation(
        self,
        workspace_id: UUID,
        investigation_id: UUID,
        payload: VerifyRequest,
        uid: str,
    ) -> Job:
        """Trigger verification of an accepted/needs-work investigation."""

        # 1. Fetch Investigation
        inv = await self.visit_port.get_investigation(workspace_id, investigation_id)
        if not inv:
            raise ApiError(
                status_code=404,
                code="INVESTIGATION_NOT_FOUND",
                message=f"Investigation {investigation_id} not found in workspace",
            )

        # 2. State Guard: Only ACCEPTED or NEEDS_WORK
        if inv.state not in (State.ACCEPTED, State.NEEDS_WORK):
            raise ApiError(
                status_code=409,
                code="INVALID_STATE",
                message=f"Cannot verify investigation in state {inv.state.value}; must be ACCEPTED or NEEDS_WORK",
            )

        # 3. OCC Guard: expected_version check
        if inv.version != payload.expected_version:
            raise ApiError(
                status_code=409,
                code="VERSION_CONFLICT",
                message=f"Expected version {payload.expected_version} but investigation is at version {inv.version}",
            )

        # 4. Visit check
        visit = await self.visit_port.get_visit(workspace_id, inv.visit_id)
        if not visit or visit.status == Status5.CLOSED:
            raise ApiError(
                status_code=409,
                code="VISIT_CLOSED",
                message="Cannot verify against a closed or nonexistent visit",
            )

        # 5. Stale policy check (AC34)
        promo = await self.policy_port.get_promotion(workspace_id, inv.promotion_id)
        if promo and promo.approved_policy and promo.approved_policy.id != inv.policy_version_id:
            inv.policy_stale = True
            inv.version += 1
            inv.updated_at = self.clock.now_utc()
            await self.visit_port.update_investigation(workspace_id, inv)
            raise ApiError(
                status_code=409,
                code="STALE_POLICY",
                message="Approved policy version has been superseded; verification prohibited",
            )

        # 6. Media eligibility checks (AC19)
        # Collect before-image hashes from visit
        before_hashes: set[str] = set()
        for b_id in visit.before_media_ids:
            b_media = await self.catalog_port.get_media(workspace_id, b_id)
            if b_media:
                if b_media.normalized_sha256:
                    before_hashes.add(b_media.normalized_sha256)
                if b_media.original_sha256:
                    before_hashes.add(b_media.original_sha256)

        now = self.clock.now_utc()
        after_media_list = []
        for m_id in payload.after_media_ids:
            m = await self.catalog_port.get_media(workspace_id, m_id)
            if not m:
                raise ApiError(
                    status_code=422,
                    code="MEDIA_NOT_FOUND",
                    message=f"Media {m_id} not found in workspace",
                )
            if m.status != Status1.READY:
                raise ApiError(
                    status_code=422,
                    code="MEDIA_NOT_READY",
                    message=f"Media {m_id} is not in READY status",
                )
            if m.visit_id != visit.id or m.store_id != visit.store_id:
                raise ApiError(
                    status_code=422,
                    code="MEDIA_NOT_BOUND_TO_VISIT",
                    message=f"Media {m_id} is not bound to visit {visit.id} and store {visit.store_id}",
                )
            media_hash = m.normalized_sha256 or m.original_sha256
            if media_hash and media_hash in before_hashes:
                raise ApiError(
                    status_code=422,
                    code="REUSED_BEFORE_MEDIA",
                    message=f"Media {m_id} reuses a before-image normalized hash",
                )
            # Timestamp checks
            cap_time = m.captured_at or m.created_at
            age_seconds = (now - cap_time).total_seconds()
            if age_seconds > 1800:
                raise ApiError(
                    status_code=422,
                    code="MEDIA_TOO_OLD",
                    message=f"Media {m_id} capture is older than 30 minutes ({age_seconds:.0f}s)",
                )
            future_seconds = (cap_time - now).total_seconds()
            if future_seconds > 300:
                raise ApiError(
                    status_code=422,
                    code="MEDIA_FUTURE_DATED",
                    message=f"Media {m_id} capture timestamp is more than 5 minutes in the future",
                )
            after_media_list.append(m)

        # 7. Create Verification Placeholder Resource (SEMANTICS.md:75-76)
        verification_id = uuid4()
        job_id = uuid4()
        verification = Verification(
            id=verification_id,
            workspace_id=workspace_id,
            version=1,
            created_at=now,
            updated_at=now,
            investigation_id=inv.id,
            plan_revision=inv.plan_revision,
            after_media_ids=payload.after_media_ids,
            job_id=job_id,
            checks=[],
            result=None,
            requested_retakes=[],
            report_id=None,
        )
        await self.verification_repo.save_verification(workspace_id, verification)

        # 8. Transition Investigation to VERIFYING
        pre_job_inv_state = inv.state
        pre_job_latest_ver = inv.latest_verification_id
        pre_job_current_job = inv.current_job_id

        inv.state = State.VERIFYING
        inv.latest_verification_id = verification_id
        inv.current_job_id = job_id
        inv.version += 1
        inv.updated_at = now
        await self.visit_port.update_investigation(workspace_id, inv)

        # 9. Create Job
        job = Job(
            id=job_id,
            workspace_id=workspace_id,
            version=1,
            created_at=now,
            updated_at=now,
            type=Type2.VERIFY,
            status=Status2.QUEUED,
            resource_id=verification_id,
            resource_type=ResourceType.VERIFICATION,
            attempt=0,
            stage="QUEUED",
            started_at=None,
            finished_at=None,
            error=None,
            linked_previous_job_id=None,
            model_id=None,
            usage=None,
        )
        try:
            await self.state_repo.create_job_with_outbox(job)
        except (RuntimeError, ValueError, KeyError, OSError) as job_err:
            logger.error(f"Failed to create verification job: {job_err}")
            # Saga compensation: rollback investigation state to original entry state
            inv.state = pre_job_inv_state
            inv.latest_verification_id = pre_job_latest_ver
            inv.current_job_id = pre_job_current_job
            inv.version += 1
            inv.updated_at = self.clock.now_utc()
            await self.visit_port.update_investigation(workspace_id, inv)
            raise

        # Synchronous execution for in-process testing / LOCAL profile
        await self._run_verification_job(
            workspace_id=workspace_id,
            job=job,
            verification=verification,
            inv=inv,
            visit=visit,
            after_media_list=after_media_list,
        )

        latest_job = await self.state_repo.get_job(workspace_id, job.id)
        return latest_job or job

    async def _run_verification_job(
        self,
        workspace_id: UUID,
        job: Job,
        verification: Verification,
        inv: Investigation,
        visit: Visit,
        after_media_list: list[Media],
    ) -> None:
        """Execute verification workflow, derive aggregate, and coordinate state resolution."""
        # Claim lease
        gen = await self.state_repo.acquire_job_lease(
            job.id, worker_id="verifier-worker", lease_seconds=60
        )
        if gen is None:
            logger.warning(f"Could not claim lease for verification job {job.id}")
            return

        now = self.clock.now_utc()
        await self.state_repo.update_job_stage(
            job_id=job.id,
            generation=gen,
            stage="ANALYZING_IMAGES",
            status="RUNNING",
            summary="Analyzing after-action verification media",
        )

        # 1. Fetch Policy Version first to guide multimodal extraction
        policy_ver = await self.policy_port.get_policy_version_by_id(
            workspace_id, inv.policy_version_id
        )
        if not policy_ver:
            logger.error(f"Policy version {inv.policy_version_id} not found")
            inv.state = State.NEEDS_WORK
            inv.version += 1
            inv.updated_at = self.clock.now_utc()
            await self.visit_port.update_investigation(workspace_id, inv)

            verification.result = Result1.INCONCLUSIVE
            verification.version += 1
            verification.updated_at = self.clock.now_utc()
            await self.verification_repo.update_verification(workspace_id, verification)

            if gen is not None:
                await self.state_repo.update_job_stage(
                    job_id=job.id,
                    generation=gen,
                    stage="COMPLETED",
                    status="FAILED",
                    summary="Policy version not found",
                )
            return

        # 2. Ingest Media bytes, generate Evidence records, and derive Observations
        observations: list[ImageObservation] = []
        raw_images: list[bytes] = []
        valid_evidence_ids: list[UUID] = []
        media_to_ev_map: dict[UUID, UUID] = {}

        for m in after_media_list:
            ev_id = uuid4()
            media_to_ev_map[m.id] = ev_id
            valid_evidence_ids.append(ev_id)
            valid_evidence_ids.append(m.id)

            zone_id = m.zone_id or "unassigned-zone"
            zone_kind_val = m.zone_kind.value if m.zone_kind else "SHELF"
            cap_time = m.captured_at or m.created_at

            evidence = Evidence(
                id=ev_id,
                investigation_id=inv.id,
                kind=Kind8.PHOTO,
                observed_at=cap_time,
                retrieved_at=now,
                freshness=Freshness1.CURRENT,
                summary=f"After-action verification photo {m.id}",
                source_id=m.id,
                source_sha256=m.normalized_sha256 or m.original_sha256,
                locator=Locator(
                    media_id=m.id,
                    page=None,
                    quote=None,
                    box=None,
                    row_ids=[],
                    batch_ids=[],
                    query_template_id=None,
                    query_job_id=None,
                    query_parameters={},
                ),
            )
            await self.visit_port.save_evidence(workspace_id, evidence)

            # Read actual bytes from BlobRepository (required by multimodal verification)
            raw_bytes: bytes | None = None
            try:
                raw_bytes = await self.blob_repo.read_bytes(m.id)
                raw_images.append(raw_bytes)
            except (OSError, FileNotFoundError, RuntimeError) as e:
                logger.warning(f"Could not read blob bytes for media {m.id}: {e}")

            # Derive observation via model gateway if available, otherwise initialize cleanly from media metadata
            obs: ImageObservation | None = None
            if raw_bytes:
                try:
                    obs = await extract_image_observations(
                        gateway=self.model_gateway,
                        image_bytes=raw_bytes,
                        media_id=m.id,
                        zone_id=zone_id,
                        zone_kind=zone_kind_val,
                        catalog_product_ids=policy_ver.catalog_product_ids,
                    )
                except (
                    ModelGatewayError,
                    ModelSchemaError,
                    ValidationError,
                    ValueError,
                    KeyError,
                ) as e:
                    logger.warning(f"Could not extract image observations for media {m.id}: {e}")
                    obs = None

            if obs is None:
                # Fail-closed: unextracted or failed observation is UNUSABLE, leading to UNKNOWN/INCONCLUSIVE
                obs = ImageObservation(
                    media_id=m.id,
                    zone_id=zone_id,
                    zone_kind=zone_kind_val,
                    quality="UNUSABLE",
                    coverage="UNKNOWN",
                    occluded=False,
                    detections=[],
                    display="UNKNOWN",
                    limitations=["Image observation extraction failed or unparsed"],
                )
            observations.append(obs)

        # 3. Execute Verifier with untrusted visit notes delimited as data (AC32)
        verifier = ExecutionVerifier(self.model_gateway)
        try:
            checks, aggregate_result, requested_retakes = await verifier.verify(
                visit_id=visit.id,
                policy_version=policy_ver,
                observations=observations,
                valid_evidence_ids=valid_evidence_ids,
                raw_images=raw_images,
                visit_notes=visit.notes,
                media_to_ev_map=media_to_ev_map,
            )
        except (
            ModelGatewayError,
            ModelSchemaError,
            VerifierGroundingError,
            ValidationError,
            ValueError,
            KeyError,
            RuntimeError,
            OSError,
        ) as err:
            logger.error(f"Verification engine failure: {err}")
            # states.json: A failed verification job returns its investigation to NEEDS_WORK without an aggregate PASS
            inv.state = State.NEEDS_WORK
            inv.version += 1
            inv.updated_at = self.clock.now_utc()
            await self.visit_port.update_investigation(workspace_id, inv)

            verification.result = Result1.INCONCLUSIVE
            verification.version += 1
            verification.updated_at = self.clock.now_utc()
            await self.verification_repo.update_verification(workspace_id, verification)

            if gen is not None:
                await self.state_repo.update_job_stage(
                    job_id=job.id,
                    generation=gen,
                    stage="COMPLETED",
                    status="FAILED",
                    summary=str(err),
                )
            return

        # 4. Coordinated Resolution with OCC Fencing and Rollback Compensation
        report_id = uuid4()
        grounded_ev_ids = [
            media_to_ev_map[m.id] for m in after_media_list if m.id in media_to_ev_map
        ]

        # Snapshot pre-resolution state for saga compensation
        orig_inv_state = inv.state
        orig_inv_version = inv.version
        orig_inv_latest_ver = inv.latest_verification_id
        orig_act_statuses = [a.status for a in inv.actions]
        orig_visit_status = visit.status
        orig_visit_version = visit.version
        orig_visit_active_inv = visit.active_investigation_id

        if aggregate_result == Result1.PASS:
            report = Report(
                id=report_id,
                workspace_id=workspace_id,
                visit_id=visit.id,
                investigation_id=inv.id,
                verification_id=verification.id,
                created_at=now,
                outcome=Outcome.PASS,
                summary="Execution verification PASSED: all policy rules verified compliant.",
                checks=checks,
                evidence_ids=grounded_ev_ids,
                policy_version_id=inv.policy_version_id,
            )

            try:
                # Step 1: Save Report
                await self.visit_port.save_report(workspace_id, report)

                # Step 2: Update Actions and Investigation
                for act in inv.actions:
                    act.status = Status6.VERIFIED
                inv.state = State.RESOLVED
                inv.latest_verification_id = verification.id
                inv.version += 1
                inv.updated_at = now
                await self.visit_port.update_investigation(workspace_id, inv)

                # Step 3: Update Visit
                visit.status = Status5.CLOSED
                visit.active_investigation_id = None
                visit.version += 1
                visit.updated_at = now
                await self.visit_port.update_visit(workspace_id, visit)

                # Step 4: Update Verification
                verification.result = Result1.PASS
                verification.checks = checks
                verification.requested_retakes = requested_retakes
                verification.report_id = report_id
                verification.version += 1
                verification.updated_at = now
                await self.verification_repo.update_verification(workspace_id, verification)
            except (RuntimeError, ValueError, KeyError, OSError) as cascade_err:
                logger.error(
                    f"PASS resolution cascade failed, executing compensating rollback: {cascade_err}"
                )
                try:
                    # Fail-closed: cascade failure aborts resolution and transitions investigation to NEEDS_WORK
                    inv.state = State.NEEDS_WORK
                    inv.version = orig_inv_version + 1
                    inv.latest_verification_id = orig_inv_latest_ver
                    for a, st in zip(inv.actions, orig_act_statuses, strict=False):
                        a.status = st
                    inv.updated_at = self.clock.now_utc()
                    await self.visit_port.update_investigation(workspace_id, inv)
                except (RuntimeError, ValueError, KeyError, OSError) as rollback_err:
                    logger.critical(
                        f"Compensating rollback for investigation failed: {rollback_err}"
                    )

                try:
                    visit.status = orig_visit_status
                    visit.version = orig_visit_version + 1
                    visit.active_investigation_id = orig_visit_active_inv
                    visit.updated_at = self.clock.now_utc()
                    await self.visit_port.update_visit(workspace_id, visit)
                except (RuntimeError, ValueError, KeyError, OSError) as rollback_err:
                    logger.critical(
                        f"Compensating rollback for visit failed: {rollback_err}"
                    )

                if gen is not None:
                    await self.state_repo.update_job_stage(
                        job_id=job.id,
                        generation=gen,
                        stage="COMPLETED",
                        status="FAILED",
                        summary=f"Cascade error: {cascade_err}",
                    )
                return

            if gen is not None:
                await self.state_repo.update_job_stage(
                    job_id=job.id,
                    generation=gen,
                    stage="COMPLETED",
                    status="SUCCEEDED",
                    summary="Execution verification PASSED: investigation and visit resolved.",
                )
        else:
            outcome_val = Outcome(aggregate_result.value)
            report = Report(
                id=report_id,
                workspace_id=workspace_id,
                visit_id=visit.id,
                investigation_id=inv.id,
                verification_id=verification.id,
                created_at=now,
                outcome=outcome_val,
                summary=f"Execution verification {aggregate_result.value}: policy rules not fully satisfied.",
                checks=checks,
                evidence_ids=grounded_ev_ids,
                policy_version_id=inv.policy_version_id,
            )

            try:
                # Step 1: Save Report
                await self.visit_port.save_report(workspace_id, report)

                # Step 2: Investigation returns to NEEDS_WORK
                inv.state = State.NEEDS_WORK
                inv.latest_verification_id = verification.id
                inv.version += 1
                inv.updated_at = now
                await self.visit_port.update_investigation(workspace_id, inv)

                # Step 3: Update Verification
                verification.result = aggregate_result
                verification.checks = checks
                verification.requested_retakes = requested_retakes
                verification.report_id = report_id
                verification.version += 1
                verification.updated_at = now
                await self.verification_repo.update_verification(workspace_id, verification)
            except (RuntimeError, ValueError, KeyError, OSError) as cascade_err:
                logger.error(
                    f"Non-PASS resolution cascade failed, executing compensating rollback: {cascade_err}"
                )
                try:
                    inv.state = orig_inv_state
                    inv.version = orig_inv_version + 1
                    inv.latest_verification_id = orig_inv_latest_ver
                    inv.updated_at = self.clock.now_utc()
                    await self.visit_port.update_investigation(workspace_id, inv)
                except (RuntimeError, ValueError, KeyError, OSError) as rollback_err:
                    logger.critical(
                        f"Compensating rollback failed: {rollback_err}"
                    )
                raise

            if gen is not None:
                await self.state_repo.update_job_stage(
                    job_id=job.id,
                    generation=gen,
                    stage="COMPLETED",
                    status="SUCCEEDED",
                    summary=f"Execution verification ended with {aggregate_result.value}",
                )

    async def list_verifications(
        self,
        workspace_id: UUID,
        investigation_id: UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> VerificationList:
        # Validate investigation exists
        inv = await self.visit_port.get_investigation(workspace_id, investigation_id)
        if not inv:
            raise ApiError(
                status_code=404,
                code="INVESTIGATION_NOT_FOUND",
                message=f"Investigation {investigation_id} not found",
            )
        items, next_cursor = await self.verification_repo.list_verifications(
            workspace_id=workspace_id,
            investigation_id=investigation_id,
            cursor=cursor,
            limit=limit,
        )
        return VerificationList(items=items, next_cursor=next_cursor)

    async def get_verification(
        self, workspace_id: UUID, verification_id: UUID
    ) -> Verification:
        v = await self.verification_repo.get_verification(workspace_id, verification_id)
        if not v:
            raise ApiError(
                status_code=404,
                code="VERIFICATION_NOT_FOUND",
                message=f"Verification {verification_id} not found in workspace",
            )
        return v
