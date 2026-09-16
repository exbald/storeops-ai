-- BigQuery Analytics Tables for StoreOps Cloud Profile
-- Dataset: storeops_${APP_ENV} (e.g. storeops_dev)

-- 1. Daily Sales Table
CREATE TABLE IF NOT EXISTS daily_sales (
    workspace_id STRING NOT NULL,
    store_code STRING NOT NULL,
    sku STRING NOT NULL,
    business_date DATE NOT NULL,
    units INT64 NOT NULL,
    revenue NUMERIC(12, 2) NOT NULL,
    currency STRING NOT NULL,
    batch_id STRING NOT NULL,
    committed_at TIMESTAMP NOT NULL
)
PARTITION BY business_date
CLUSTER BY workspace_id, store_code, sku
OPTIONS (
    description = "Partitioned daily sales records committed from sales CSV imports"
);

-- 2. Inventory Snapshots Table
CREATE TABLE IF NOT EXISTS inventory_snapshots (
    workspace_id STRING NOT NULL,
    location_code STRING NOT NULL,
    sku STRING NOT NULL,
    observed_at TIMESTAMP NOT NULL,
    business_date DATE NOT NULL,
    on_hand INT64 NOT NULL,
    batch_id STRING NOT NULL,
    committed_at TIMESTAMP NOT NULL
)
PARTITION BY business_date
CLUSTER BY workspace_id, location_code, sku
OPTIONS (
    description = "Partitioned inventory on-hand snapshots committed from inventory CSV imports"
);

-- 3. Import Batches Table
CREATE TABLE IF NOT EXISTS import_batches (
    batch_id STRING NOT NULL,
    workspace_id STRING NOT NULL,
    import_id STRING NOT NULL,
    kind STRING NOT NULL,
    row_count INT64 NOT NULL,
    source_sha256 STRING NOT NULL,
    committed_at TIMESTAMP NOT NULL
)
CLUSTER BY workspace_id, batch_id
OPTIONS (
    description = "Committed import batch metadata for auditability and deduplication"
);
