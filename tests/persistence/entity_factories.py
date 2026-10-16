"""Minimal valid contract entities for persistence round-trip tests."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from storeops_contracts.models import (
    Currency,
    Evidence,
    Freshness1,
    Investigation,
    Kind,
    Kind4,
    Kind5,
    Kind8,
    Location,
    Locator,
    Media,
    Outcome,
    PolicySource,
    PolicyVersion,
    Product,
    Promotion,
    Report,
    Rule,
    State,
    Status1,
    Status5,
    Store,
    Type1,
    Verification,
    Visit,
    ZoneKind,
)

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
SHA = "a" * 64


def ts(minutes: int = 0) -> datetime:
    return T0 + timedelta(minutes=minutes)


def store(ws: UUID, code: str = "S-001", backroom_id: UUID | None = None, minutes: int = 0) -> Store:
    return Store(
        id=uuid4(), workspace_id=ws, version=1, created_at=ts(minutes), updated_at=ts(minutes),
        code=code, name="Store", retailer="Retail", region="SG", format="Mini",
        timezone="Asia/Singapore", distributor_location_id=None, currency=Currency.SGD,
        backroom_location_id=backroom_id or uuid4(), active=True,
    )


def location(ws: UUID, code: str = "BR-001", store_id: UUID | None = None) -> Location:
    return Location(
        id=uuid4(), workspace_id=ws, version=1, created_at=ts(), updated_at=ts(),
        code=code, name="Backroom", type=Type1.BACKROOM, store_id=store_id, active=True,
    )


def product(ws: UUID, sku: str = "SKU-1") -> Product:
    return Product(
        id=uuid4(), workspace_id=ws, version=1, created_at=ts(), updated_at=ts(),
        sku=sku, name="Tea", case_units=12, reference_media_ids=[uuid4()], active=True,
    )


def media(ws: UUID, status: Status1 = Status1.PENDING_UPLOAD, byte_size: int = 10) -> Media:
    return Media(
        id=uuid4(), workspace_id=ws, version=1, created_at=ts(), updated_at=ts(),
        kind=Kind.IMPORT, filename="sales.csv", mime_type="text/csv", status=status,
        store_id=None, visit_id=None, product_id=None, zone_id=None, zone_kind=None,
        captured_at=None, original_sha256=SHA, normalized_sha256=None, byte_size=byte_size,
        width=None, height=None, rejection=None, download_url=None, download_url_expires_at=None,
    )


def promotion(ws: UUID) -> Promotion:
    return Promotion(
        id=uuid4(), workspace_id=ws, version=1, created_at=ts(), updated_at=ts(),
        name="Promo", starts_on=date(2026, 10, 1), ends_on=date(2026, 10, 31),
        store_ids=[uuid4()], agreement_media_id=None, archived=False, draft_revision=1,
        extracted_rules=[], extraction_gaps=[], approved_policy=None,
    )


def rule() -> Rule:
    return Rule(
        rule_id=uuid4(), kind=Kind5.MIN_FACINGS, zone_id="endcap-1",
        zone_kind=next(iter(ZoneKind)), product_id=uuid4(), min_facings=3,
        source=PolicySource(
            kind=Kind4.MANUAL, media_id=None, page=None, quote=None, reviewer_note="manual entry"
        ),
    )


def policy_version(promotion_id: UUID, version: int = 1) -> PolicyVersion:
    return PolicyVersion(
        id=uuid4(), promotion_id=promotion_id, version=version, rules=[rule()],
        catalog_product_ids=[uuid4()], store_ids=[uuid4()], starts_on=date(2026, 10, 1),
        ends_on=date(2026, 10, 31), approved_at=ts(), approved_by="admin-uid", content_sha256=SHA,
    )


def visit(ws: UUID, store_id: UUID | None = None) -> Visit:
    return Visit(
        id=uuid4(), workspace_id=ws, version=1, created_at=ts(), updated_at=ts(),
        store_id=store_id or uuid4(), notes="Shelf gap near entrance 🍵", visit_started_at=ts(),
        status=Status5.OPEN, before_media_ids=[uuid4()], after_media_ids=[],
        active_investigation_id=None, report_ids=[],
    )


def investigation(ws: UUID, visit_id: UUID | None = None) -> Investigation:
    return Investigation(
        id=uuid4(), workspace_id=ws, version=1, created_at=ts(), updated_at=ts(),
        store_id=uuid4(), visit_id=visit_id or uuid4(), promotion_id=uuid4(),
        policy_version_id=uuid4(), snapshot_id=uuid4(), state=State.QUEUED, snapshot_at=ts(),
        metrics=None, diagnosis=None, actions=[], plan_revision=0, accepted_at=None,
        accepted_by=None, current_job_id=uuid4(), latest_verification_id=None, policy_stale=False,
    )


def evidence(investigation_id: UUID) -> Evidence:
    return Evidence(
        id=uuid4(), investigation_id=investigation_id, kind=Kind8.SALES_ROWS, observed_at=ts(),
        retrieved_at=ts(), freshness=Freshness1.CURRENT, summary="7-day sales", source_id=uuid4(),
        source_sha256=SHA,
        locator=Locator(
            media_id=None, page=None, quote=None, box=None, row_ids=[uuid4()],
            batch_ids=[uuid4()], query_template_id="sales_window", query_job_id=None,
            query_parameters={"days": 7.0, "store": "S-001", "strict": True, "none": None},
        ),
    )


def report(ws: UUID, investigation_id: UUID) -> Report:
    return Report(
        id=uuid4(), workspace_id=ws, visit_id=uuid4(), investigation_id=investigation_id,
        verification_id=None, created_at=ts(), outcome=Outcome.PASS, summary="All good",
        checks=[], evidence_ids=[uuid4()], policy_version_id=uuid4(),
    )


def verification(ws: UUID, investigation_id: UUID, minutes: int = 0) -> Verification:
    return Verification(
        id=uuid4(), workspace_id=ws, version=1, created_at=ts(minutes), updated_at=ts(minutes),
        investigation_id=investigation_id, plan_revision=1, after_media_ids=[uuid4()],
        job_id=uuid4(), checks=[], result=None, requested_retakes=[], report_id=None,
    )
