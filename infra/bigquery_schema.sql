-- BigQuery analytics migration 001: Initial schema for StoreOps commercial analytics

-- 1. Import Batches manifest table
CREATE TABLE IF NOT EXISTS import_batches (
    workspace_id STRING NOT NULL,
    batch_id STRING NOT NULL,
    kind STRING NOT NULL,
    import_id STRING NOT NULL,
    source_sha256 STRING NOT NULL,
    row_count INT64 NOT NULL,
    committed_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(committed_at)
CLUSTER BY workspace_id, batch_id;

-- 2. Sales Facts table
CREATE TABLE IF NOT EXISTS sales_facts (
    workspace_id STRING NOT NULL,
    batch_id STRING NOT NULL,
    store_id STRING NOT NULL,
    sku STRING NOT NULL,
    business_date DATE NOT NULL,
    units INT64 NOT NULL,
    revenue NUMERIC(12, 2) NOT NULL,
    currency STRING NOT NULL
)
PARTITION BY business_date
CLUSTER BY workspace_id, store_id, sku;

-- 3. Inventory Facts table
CREATE TABLE IF NOT EXISTS inventory_facts (
    workspace_id STRING NOT NULL,
    batch_id STRING NOT NULL,
    location_id STRING NOT NULL,
    sku STRING NOT NULL,
    observed_at TIMESTAMP NOT NULL,
    quantity INT64 NOT NULL,
    unit STRING NOT NULL,
    normalized_units INT64 NOT NULL
)
PARTITION BY DATE(observed_at)
CLUSTER BY workspace_id, location_id, sku;
