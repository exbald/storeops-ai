# Domain and data contract

## Shared conventions

All entity IDs are UUID strings, independent of names and external codes. Workspace
scope comes from membership and resource lookup, never a trusted client workspace_id.
All timestamps are RFC 3339 UTC. Business dates use the store timezone. Store/product
codes are unique within a workspace. Decimal money is a string with two places in
APIs and NUMERIC in BigQuery; never use floating point for currency.

Every mutable Firestore document has id, workspace_id, version (integer ≥1), created_at
and updated_at. Existing-resource mutation commands carry expected_version. A mismatch
returns 409 VERSION_CONFLICT, without any partial mutation. Archival blocks new usage
but does not delete historical evidence. Unknown fields are rejected.

## Firestore collections

| Collection | Additional fields and invariant |
|---|---|
| workspaces | name, brand_name, currency (SGD/USD/AUD), status; currency cannot change after the first committed import |
| memberships | workspace_id + uid unique; role ADMIN/REP; provisioned through the bootstrap/member CLI, no email invitation flow |
| stores | code, name, retailer, region, format, timezone, currency, backroom_location_id, distributor_location_id?, active |
| locations | code, name, type BACKROOM/DISTRIBUTOR, store_id?; a backroom belongs to exactly one store |
| products | sku, name, case_units, reference_media_ids[], active; sku is data, not a schema enum |
| media | kind, subject/store/visit/product IDs as applicable, original_sha256, normalized_sha256, MIME, size, dimensions, captured_at?, object generation, status |
| imports | kind, media_id, validation status, row_count, errors (first 50 plus total), staging reference, committed batch ID and result version |
| promotions | name, dates, eligible store_ids, agreement_media_id?, current draft revision and approved version; archived flag |
| policy_versions | immutable promotion_id/version, reviewed rules, source pointers, approved_by/at, covered catalog IDs and content hash |
| visits | store_id, notes, visit_started_at, status OPEN/CLOSED, before_media_ids, after_media_ids and report IDs |
| investigations | visit/store, state, source snapshot, rule version, metrics, diagnosis, plan revision, accepted_by/at and latest verification ID |
| actions | investigation_id, stable action ID, kind, rule/evidence IDs, instruction, status OPEN/CLAIMED_DONE/VERIFIED |
| verifications | immutable attempt ID, investigation/plan version, media IDs, checks, aggregate result, model metadata and report |
| reports | immutable report ID, visit/investigation/verification IDs, outcome, checks and policy version; readable independently of job state |
| evidence | immutable type, payload/value/unit, observed/retrieved times, source IDs, locators and hash; scoped to investigation |
| jobs | type, resource_id, status, attempt, lease, progress stage, timestamps, error, model/usage metadata and result reference |
| job_events | job_id + increasing sequence; stage, status, human-readable summary and timestamp; no model private reasoning |
| outbox | job_id, dispatch status, next_attempt_at, retry count; created atomically with the job |
| idempotency | uid + method + route + key; canonical body hash, response/resource IDs and expiry |

Firestore indexes must cover workspace+active catalog lists, store+visit time, workspace+
job status, and undispatched outbox entries. Include index definitions in infra; do not
rely on console-only setup. Deny direct browser reads/writes; API/worker service accounts
are the only data clients.

## BigQuery tables

All tables include workspace_id STRING. Validate foreign keys in the importing service;
BigQuery constraints alone are not enforcement. Store row hashes and source line numbers
to support audit and replay. Keep the application dataset separate from evaluation data.

| Table | Grain and columns |
|---|---|
| import_batches | batch_id STRING; kind STRING; import_id STRING; source_sha256 STRING; committed_at TIMESTAMP; row_count INT64; source_schema_version STRING |
| sales_revisions | batch_id STRING, row_id STRING, store_id STRING, product_id STRING, business_date DATE, units INT64, revenue NUMERIC, currency STRING, source_line INT64, row_sha256 STRING |
| inventory_revisions | batch_id STRING, row_id STRING, location_id STRING, product_id STRING, observed_at TIMESTAMP, quantity INT64, unit STRING, units_normalized INT64, case_units_at_import INT64, source_line INT64, row_sha256 STRING |

Sales logical key: workspace/store/product/business_date. Inventory logical key:
workspace/location/product/observed_at. A correcting import appends a new revision; the
latest committed batch wins for the same logical key. Break commit timestamp ties with
batch_id lexicographically. Partition facts by business_date or observed_at and cluster
by workspace, store/location and product. Partition import_batches by committed_at.

Validate and stage all rows first. Commit facts and manifest atomically. Serialize import
commit within a workspace using a leased Firestore lock so identical source hashes cannot
commit concurrently. Recheck existing batch/row identities after acquiring the lock.
Retried commit jobs reuse their batch_id. Do not use load append plus a separate unchecked
Firestore status update as an atomic commit.

## Snapshot and completeness semantics

At investigation start capture the set of committed batch IDs, policy version, product
reference versions, visit notes and media hashes. Query only those batches. Freeze the
actual returned rows and SQL template/parameters/job ID in evidence. Later imports must
not change an existing report. Verification creates a new image-evidence snapshot and
references the accepted plan; it does not rewrite the investigation snapshot.

Missing sales rows are unknown, not zero. Complete weekly coverage requires a row for
each active relevant product on every date; a zero-sales day is an explicit zero row.
Inventory is the latest snapshot per location/product at or before the investigation
time; no row means unknown. Stock at a distributor never proves stock in a store backroom.
Negative sales/stock quantities are unsupported in this MVP and rejected with row errors.

References and policies use the relevant product catalog frozen with the policy version.
Changing the active catalog or a policy creates a new revision; historical runs retain
their prior references. A product cannot be archived while required by an active policy.
Archived stores cannot start new visits; completed reports remain readable.
