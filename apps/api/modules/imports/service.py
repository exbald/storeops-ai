import hashlib
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

from storeops_contracts.models import (
    Freshness,
    Import,
    ImportCreate,
    Job,
    Readines,
    ResourceType,
    Status2,
    Status4,
    StoreHealth,
    Type2,
    VersionCommand,
)

from apps.api.analytics.metrics import compute_peer_gap_metrics
from apps.api.modules.catalog.repository import CatalogRepository
from apps.api.modules.imports.repository import ImportRepository
from apps.api.modules.imports.validator import validate_csv_content
from apps.api.ports.analytics import AnalyticsRepository
from apps.api.ports.blob import BlobRepository
from apps.api.ports.clock import Clock
from apps.api.ports.state import StateRepository


class ImportServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ConflictError(ImportServiceError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=409)


class NotFoundError(ImportServiceError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=404)


class ValidationError(ImportServiceError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422)


class ImportService:
    def __init__(
        self,
        import_repo: ImportRepository,
        analytics_repo: AnalyticsRepository,
        catalog_repo: CatalogRepository,
        state_repo: StateRepository,
        blob_repo: BlobRepository,
        clock: Clock,
    ) -> None:
        self.import_repo = import_repo
        self.analytics_repo = analytics_repo
        self.catalog_repo = catalog_repo
        self.state_repo = state_repo
        self.blob_repo = blob_repo
        self.clock = clock

    async def list_imports(
        self,
        workspace_id: UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Import], str | None]:
        return await self.import_repo.list_imports(
            workspace_id, cursor=cursor, limit=limit
        )

    async def get_import(self, workspace_id: UUID, import_id: UUID) -> Import:
        imp = await self.import_repo.get_import(workspace_id, import_id)
        if not imp:
            raise NotFoundError(
                f"Import {import_id} not found in workspace {workspace_id}"
            )
        return imp

    async def create_import(
        self,
        workspace_id: UUID,
        payload: ImportCreate,
        user_id: UUID,
    ) -> Job:
        workspace = await self.state_repo.get_workspace(workspace_id)
        if not workspace:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        # 1. Validate media existence, readiness and mime_type
        media = await self.catalog_repo.get_media(workspace_id, payload.media_id)
        if not media:
            raise NotFoundError(f"Media {payload.media_id} not found in workspace")

        if media.status.value != "READY":
            raise ValidationError(
                f"Media {payload.media_id} is in status {media.status.value}, expected READY"
            )

        if media.kind.value != "IMPORT":
            raise ValidationError(
                f"Media {payload.media_id} has kind {media.kind.value}, expected IMPORT"
            )

        if media.mime_type != "text/csv":
            raise ValidationError(
                f"Media {payload.media_id} has mime_type {media.mime_type}, expected text/csv"
            )

        # 2. Read raw CSV bytes from blob store
        csv_bytes = await self.blob_repo.read_bytes(payload.media_id)
        source_sha256 = hashlib.sha256(csv_bytes).hexdigest()

        # Deduplication check: per contracts/imports.json:
        # "Same workspace/kind/source hash returns existing committed import; repeat commits reuse batch_id."
        existing_committed = await self.import_repo.find_committed_import(
            workspace_id=workspace_id,
            kind=payload.kind,
            source_sha256=source_sha256,
        )

        now = self.clock.now_utc()

        # 3. Create Import record
        import_id = uuid4()
        import_record = Import(
            id=import_id,
            workspace_id=workspace_id,
            version=1,
            created_at=now,
            updated_at=now,
            kind=payload.kind,
            media_id=payload.media_id,
            status=Status4.VALIDATING,
            row_count=0,
            error_count=0,
            errors=[],
            batch_id=existing_committed.batch_id if existing_committed else None,
            committed_at=None,
            source_sha256=source_sha256,
        )
        await self.import_repo.save_import(import_record)

        # 4. Create Job
        job_id = uuid4()
        job = Job(
            id=job_id,
            workspace_id=workspace_id,
            version=1,
            created_at=now,
            updated_at=now,
            type=Type2.IMPORT_VALIDATE,
            status=Status2.QUEUED,
            resource_id=import_id,
            resource_type=ResourceType.IMPORT,
            attempt=0,
            stage="VALIDATING",
            started_at=now,
            finished_at=None,
            error=None,
            linked_previous_job_id=None,
            model_id=None,
            usage=None,
        )
        await self.state_repo.create_job_with_outbox(job)

        # 5. Perform synchronous validation (local/worker profile)
        stores, _ = await self.catalog_repo.list_stores(workspace_id, limit=1000)
        locations, _ = await self.catalog_repo.list_locations(workspace_id, limit=1000)
        products, _ = await self.catalog_repo.list_products(workspace_id, limit=1000)

        active_stores_by_code = {s.code: s for s in stores if s.active}
        active_locations_by_code = {loc.code: loc for loc in locations if loc.active}
        active_products_by_sku = {p.sku: p for p in products if p.active}

        val_result = validate_csv_content(
            kind=payload.kind,
            csv_bytes=csv_bytes,
            workspace_currency=workspace.currency.value,
            active_stores_by_code=active_stores_by_code,
            active_locations_by_code=active_locations_by_code,
            active_products_by_sku=active_products_by_sku,
            now=now,
        )

        completed_now = self.clock.now_utc()
        if val_result.is_valid:
            import_record.status = Status4.VALIDATED
            import_record.row_count = val_result.row_count
            import_record.error_count = 0
            import_record.errors = []
            import_record.updated_at = completed_now
            await self.import_repo.save_import(
                import_record, staged_rows=val_result.parsed_rows
            )

            gen = await self.state_repo.acquire_job_lease(
                job.id, worker_id="validation-worker"
            )
            if gen is not None:
                await self.state_repo.update_job_stage(
                    job_id=job.id,
                    generation=gen,
                    stage="VALIDATED",
                    status="SUCCEEDED",
                    summary=f"Validated {val_result.row_count} rows successfully",
                )
                updated_job = await self.state_repo.get_job(workspace_id, job.id)
                if updated_job:
                    job = updated_job
        else:
            import_record.status = Status4.INVALID
            import_record.row_count = val_result.row_count
            import_record.error_count = len(val_result.errors)
            import_record.errors = val_result.errors
            import_record.updated_at = completed_now
            await self.import_repo.save_import(import_record, staged_rows=[])

            gen = await self.state_repo.acquire_job_lease(
                job.id, worker_id="validation-worker"
            )
            if gen is not None:
                await self.state_repo.update_job_stage(
                    job_id=job.id,
                    generation=gen,
                    stage="INVALID",
                    status="SUCCEEDED",
                    summary=f"Validation completed with {len(val_result.errors)} errors",
                )
                updated_job = await self.state_repo.get_job(workspace_id, job.id)
                if updated_job:
                    job = updated_job

        return job

    async def commit_import(
        self,
        workspace_id: UUID,
        import_id: UUID,
        command: VersionCommand,
        user_id: UUID,
    ) -> Job:
        import_record = await self.import_repo.get_import(workspace_id, import_id)
        if not import_record:
            raise NotFoundError(
                f"Import {import_id} not found in workspace {workspace_id}"
            )

        # Check version
        if import_record.version != command.expected_version:
            raise ConflictError(
                f"Version conflict for import {import_id}: expected {command.expected_version}, actual {import_record.version}"
            )

        # Idempotent replay if already committed
        now = self.clock.now_utc()
        if import_record.status == Status4.COMMITTED:
            replay_job = Job(
                id=uuid4(),
                workspace_id=workspace_id,
                version=1,
                created_at=now,
                updated_at=now,
                type=Type2.IMPORT_COMMIT,
                status=Status2.SUCCEEDED,
                resource_id=import_id,
                resource_type=ResourceType.IMPORT,
                attempt=0,
                stage="COMMITTED",
                started_at=now,
                finished_at=now,
                error=None,
                linked_previous_job_id=None,
                model_id=None,
                usage=None,
            )
            await self.state_repo.create_job_with_outbox(replay_job)
            return replay_job

        if import_record.status != Status4.VALIDATED:
            raise ConflictError(
                f"Cannot commit import in status {import_record.status.value}; must be VALIDATED"
            )

        # Staged rows retrieval
        staged_rows = await self.import_repo.get_staged_rows(import_id)
        if staged_rows is None:
            # Re-read and re-validate from media
            media = await self.catalog_repo.get_media(
                workspace_id, import_record.media_id
            )
            if not media:
                raise NotFoundError(f"Media {import_record.media_id} not found")
            csv_bytes = await self.blob_repo.read_bytes(import_record.media_id)
            workspace = await self.state_repo.get_workspace(workspace_id)
            if not workspace:
                raise NotFoundError(f"Workspace {workspace_id} not found")

            stores, _ = await self.catalog_repo.list_stores(workspace_id, limit=1000)
            locations, _ = await self.catalog_repo.list_locations(
                workspace_id, limit=1000
            )
            products, _ = await self.catalog_repo.list_products(
                workspace_id, limit=1000
            )

            active_stores_by_code = {s.code: s for s in stores if s.active}
            active_locations_by_code = {
                loc.code: loc for loc in locations if loc.active
            }
            active_products_by_sku = {p.sku: p for p in products if p.active}

            res = validate_csv_content(
                kind=import_record.kind,
                csv_bytes=csv_bytes,
                workspace_currency=workspace.currency.value,
                active_stores_by_code=active_stores_by_code,
                active_locations_by_code=active_locations_by_code,
                active_products_by_sku=active_products_by_sku,
                now=now,
            )
            if not res.is_valid:
                raise ConflictError("References are no longer valid at commit time")
            staged_rows = res.parsed_rows

        # Re-check references are still active at commit time
        stores, _ = await self.catalog_repo.list_stores(workspace_id, limit=1000)
        locations, _ = await self.catalog_repo.list_locations(workspace_id, limit=1000)
        products, _ = await self.catalog_repo.list_products(workspace_id, limit=1000)

        active_store_ids = {s.id for s in stores if s.active}
        active_loc_ids = {loc.id for loc in locations if loc.active}
        active_skus = {p.sku for p in products if p.active}

        for row in staged_rows:
            if "store_id" in row and row["store_id"] not in active_store_ids:
                raise ConflictError(
                    f"Store {row['store_id']} is no longer active at commit time"
                )
            if "location_id" in row and row["location_id"] not in active_loc_ids:
                raise ConflictError(
                    f"Location {row['location_id']} is no longer active at commit time"
                )
            if row["sku"] not in active_skus:
                raise ConflictError(
                    f"SKU {row['sku']} is no longer active at commit time"
                )

        # Deduplication / batch_id assignment:
        # Check if another committed import in workspace has same kind and source_sha256
        existing_committed = await self.import_repo.find_committed_import(
            workspace_id=workspace_id,
            kind=import_record.kind,
            source_sha256=import_record.source_sha256,
        )
        if existing_committed and existing_committed.batch_id:
            batch_id_str = str(existing_committed.batch_id)
        else:
            batch_id_str = str(uuid4())

        # Commit rows atomically to AnalyticsRepository
        await self.analytics_repo.commit_import_batch(
            workspace_id=workspace_id,
            batch_id=batch_id_str,
            kind=import_record.kind.value,
            import_id=import_record.id,
            source_sha256=import_record.source_sha256,
            rows=staged_rows,
        )

        commit_time = self.clock.now_utc()
        import_record.status = Status4.COMMITTED
        import_record.batch_id = UUID(batch_id_str)
        import_record.committed_at = commit_time
        import_record.version += 1
        import_record.updated_at = commit_time
        await self.import_repo.save_import(import_record)

        # Create commit job record
        job_id = uuid4()
        commit_job = Job(
            id=job_id,
            workspace_id=workspace_id,
            version=1,
            created_at=commit_time,
            updated_at=commit_time,
            type=Type2.IMPORT_COMMIT,
            status=Status2.SUCCEEDED,
            resource_id=import_id,
            resource_type=ResourceType.IMPORT,
            attempt=0,
            stage="COMMITTED",
            started_at=commit_time,
            finished_at=commit_time,
            error=None,
            linked_previous_job_id=None,
            model_id=None,
            usage=None,
        )
        await self.state_repo.create_job_with_outbox(commit_job)
        return commit_job

    async def get_store_health(self, workspace_id: UUID, store_id: UUID) -> StoreHealth:
        store = await self.catalog_repo.get_store(workspace_id, store_id)
        if not store:
            raise NotFoundError(
                f"Store {store_id} not found in workspace {workspace_id}"
            )

        all_stores, _ = await self.catalog_repo.list_stores(workspace_id, limit=1000)

        # Sales fetcher against analytics repository
        async def sales_fetcher(
            sid: UUID, start: str, end: str
        ) -> list[dict[str, Any]]:
            return await self.analytics_repo.get_sales_window(
                workspace_id=workspace_id,
                store_id=sid,
                start_date=start,
                end_date=end,
                batch_ids=None,
            )

        as_of_date = self.clock.now_utc().date()
        metrics = await compute_peer_gap_metrics(
            store=store,
            all_stores=all_stores,
            as_of_date=as_of_date,
            sales_fetcher=sales_fetcher,
        )

        # Readiness indicators
        readiness: list[Readines] = []
        if store.active:
            readiness.append(Readines(root="Store is active"))
        if store.distributor_location_id:
            readiness.append(Readines(root="Distributor location assigned"))

        # Check sales facts presence
        focal_sales = await sales_fetcher(
            store_id,
            str(as_of_date - timedelta(days=14)),
            str(as_of_date - timedelta(days=1)),
        )

        # Freshness determination
        if not focal_sales:
            freshness = Freshness.MISSING
            readiness.append(Readines(root="Missing sales history"))
        else:
            latest_date_str = max(r["business_date"] for r in focal_sales)
            latest_date = date.fromisoformat(latest_date_str)
            if (as_of_date - latest_date).days <= 2:
                freshness = Freshness.CURRENT
                readiness.append(Readines(root="Sales data is current"))
            else:
                freshness = Freshness.STALE
                readiness.append(Readines(root="Sales data is stale (>2 days old)"))

        return StoreHealth(
            store=store,
            metrics=metrics,
            readiness=readiness,
            freshness=freshness,
        )
