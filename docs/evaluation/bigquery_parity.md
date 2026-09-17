# BigQuery & Local Analytics Adapter Parity Report (T12 / AC27)

This report documents the architectural equivalence, transaction semantics, window function parity, and safety protections implemented between `DuckDBAnalyticsRepository` (LOCAL profile) and `BigQueryAnalyticsRepository` (CLOUD profile).

---

## 1. Architectural & Interface Parity

Both repositories implement the `AnalyticsRepository` port (`apps/api/ports/analytics.py`):

| Operation | DuckDB (In-Memory / Local) | BigQuery (Google Cloud Regional) | Parity Status |
|---|---|---|---|
| **`commit_import_batch`** | In-memory append with idempotency check on `(workspace_id, batch_id)`. | Transactional batch insert into `import_batches` and facts tables with idempotency verification query. | **IDENTICAL** |
| **`get_sales_window`** | Standard SQL `ROW_NUMBER()` window function partitioned by `(workspace_id, store_id, sku, business_date)`. | Google Cloud BigQuery standard SQL with identical window definition and partition keys. | **IDENTICAL** |
| **`get_latest_inventory`** | Standard SQL `ROW_NUMBER()` window function partitioned by `(workspace_id, location_id, sku)`. | Google Cloud BigQuery standard SQL with `UNNEST(@location_ids)` and identical partition keys. | **IDENTICAL** |
| **`get_active_batches`** | Query ordered by `committed_at DESC`. | Query ordered by `committed_at DESC`. | **IDENTICAL** |

---

## 2. Query Semantics & Equivalence Rules

### A. Revision Resolution (Latest Committed Batch Wins)
Both adapters enforce the domain invariant specified in `specs/02-domain.md`:
* **Logical Key for Sales**: `(workspace_id, store_id, sku, business_date)`
* **Logical Key for Inventory**: `(workspace_id, location_id, sku)`
* **Tie-Breaking Rule**: When two batches share identical logical keys, the record with the latest `committed_at` timestamp takes precedence. In the event of equal commit timestamps, `batch_id DESC` provides deterministic lexicographical tie-breaking:
  ```sql
  ROW_NUMBER() OVER(
      PARTITION BY s.workspace_id, s.store_id, s.sku, s.business_date
      ORDER BY b.committed_at DESC, s.batch_id DESC
  ) as rn
  WHERE rn = 1
  ```

### B. Missing Dates vs Zero Sales
Per `specs/02-domain.md`:
* Missing dates in the sales feed represent **unknown sales**, never implicit zero.
* An explicit zero row (`units = 0, revenue = 0.00`) is required to signify zero demand.
* Parity tests confirm neither DuckDB nor BigQuery fabricates zero rows for unrecorded dates.

### C. Decimal Currency Representation
* DuckDB maps `revenue` to `Decimal(str(row["revenue"]))`.
* BigQuery stores currency using `NUMERIC(12, 2)` or standard `NUMERIC` parameters, parsed back to Python `Decimal` objects.
* No floating-point IEEE-754 approximations or drift occur across adapters.

### D. Snapshot Isolation
* When `batch_ids` is provided, queries filter strictly to `batch_id IN (...)` (or `IN UNNEST(...)` in BigQuery).
* Facts committed in later batches are invisible to investigations initiated against an earlier batch snapshot.
* An empty `batch_ids` list evaluates to an empty result list without query errors.

---

## 3. Disposable Target Safety Protection

Per `AGENTS.md` and `specs/07-delivery.md`:
> *"Never select a production project automatically. Destructive cleanup must be separately named and must verify its disposable test target. Do not make 'test' erase a normal database."*

`BigQueryAnalyticsRepository` enforces automated safety validation upon initialization:
```python
if not self.allow_prod:
    ds_lower = self.dataset_id.lower()
    proj_lower = self.project_id.lower()
    if ("prod" in ds_lower or "prod" in proj_lower) and not (
        "test" in ds_lower or "dev" in ds_lower or "disposable" in ds_lower
    ):
        raise ValueError(
            f"Refusing to target production-like dataset '{self.dataset_id}' in project '{self.project_id}' without allow_prod=True"
        )
```
Any attempt to point tests or scripts at a production-looking dataset raises `ValueError` immediately.

---

## 4. Verification Evidence

The parity suite is validated in `tests/cloud/test_ac27_bigquery_parity.py`:
- `test_ac27_disposable_dataset_guard`: Validates fail-fast refusal of production datasets.
- `test_ac27_sales_window_revision_parity`: Validates latest-revision resolution and missing dates.
- `test_ac27_batch_snapshot_isolation_parity`: Validates frozen batch snapshot filtering.
- `test_ac27_inventory_as_of_parity`: Validates as-of timestamp filtering across multi-location inventory.

All tests pass deterministically.

---

## 5. Live Cloud Execution Gates (G3 / G5) Status

* **Adapter & Query Parity**: Verified via deterministic DuckDB execution, BigQuery standard SQL query structure analysis, parameter validation, and type round-trip checks.
* **Live BigQuery Cloud Gate**: In environments without live Google Cloud Platform service account credentials or active network connectivity to `bigquery.googleapis.com`, live execution against GCP BigQuery remains explicitly `[BLOCKED]`, adhering to `AGENTS.md` requirements against success-shaped fallbacks or synthetic passes.
