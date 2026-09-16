# StoreOps Cloud Development Deployment (T11 / AC-41)

This runbook documents the architecture, provisioning procedures, IAM policies, and operational runbooks for the StoreOps Cloud Development profile on Google Cloud.

---

## 1. Cloud Architecture Overview

The StoreOps Cloud profile implements a serverless, decoupled architecture on Google Cloud:

```
                  +--------------------------------+
                  |         Client Web App         |
                  |     (Next.js / Dashboard)      |
                  +---------------+----------------+
                                  |
                                  | HTTPS (Bearer Firebase ID Token)
                                  v
                  +--------------------------------+
                  |    Public Cloud Run Service    |
                  |        (storeops-api)          |
                  +---------------+----------------+
                                  |
       +--------------------------+--------------------------+
       |                          |                          |
       v                          v                          v
+--------------+          +---------------+          +---------------+
|  Cloud Run   |          | Cloud Storage |          |   Firestore   |
| Worker (VPC) |<--OIDC---| (Media Assets)|          | (Native Mode) |
|   (Private)  |          +---------------+          +---------------+
+------+-------+                                             |
       |                  +---------------+                  |
       |                  |   BigQuery    |                  |
       +----------------->| (Analytics)   |<-----------------+
       |                  +---------------+
       |
       v
+--------------+
| Gemini 3.8 / |
|   Vertex AI  |
+--------------+
```

### Components

| Component | GCP Service | Visibility | Configuration / Notes |
|---|---|---|---|
| **API Service** | Cloud Run (`storeops-api`) | Public Ingress | Port 8000. Firebase token authentication. Ingress `all`. |
| **Worker Service** | Cloud Run (`storeops-worker`) | Private / Internal | Ingress `internal`. Runs `scripts.deploy.run_worker` (port 8001 HTTP listener + worker outbox loop). Only invokable by Invoker SA via OIDC. |
| **Asynchronous Jobs** | Cloud Tasks (`storeops-work-queue`) | Regional | Rate-limited (10 dispatches/sec, max 5 concurrent). |
| **Scheduled Outbox** | Cloud Scheduler (`storeops-outbox-drain`) | Regional | Runs `* * * * *` (every 1 min), pings `/health` with OIDC (heartbeat until `/outbox/drain` route is integrated). |
| **Media Storage** | Cloud Storage (`storeops-${PROJECT_ID}-media`) | Private | Uniform bucket-level access, signed download URLs, CORS enabled. |
| **Operational DB** | Cloud Firestore | Native Mode | Composite indexes (`infra/firestore.indexes.json`). |
| **Analytics Store** | BigQuery (`storeops_${APP_ENV}`) | Regional | Partitioned by `business_date`, clustered by `workspace_id, store_code, sku`. |
| **Foundation Model** | Vertex AI / Gemini API | Global Endpoint | `gemini-3.8-flash` per architecture spec, structured outputs, one-shot repair. |

---

## 2. Least-Privilege IAM Matrix

Three dedicated service accounts isolate privileges across components:

| Service Account | Role / Display Name | Granted Roles | Justification |
|---|---|---|---|
| `storeops-api-sa` | Public API Identity | `roles/datastore.user`<br>`roles/storage.objectAdmin`<br>`roles/bigquery.dataEditor`<br>`roles/bigquery.jobUser`<br>`roles/cloudtasks.enqueuer`<br>`roles/iam.serviceAccountUser` | Read/write Firestore entities, generate signed URLs, query BigQuery analytics, enqueue async worker tasks. |
| `storeops-worker-sa` | Private Worker Identity | `roles/datastore.user`<br>`roles/storage.objectAdmin`<br>`roles/bigquery.dataEditor`<br>`roles/bigquery.jobUser`<br>`roles/aiplatform.user` | Process background jobs, write analytics batches, execute Gemini multimodal vision and extraction. |
| `storeops-invoker-sa` | Cloud Tasks & Scheduler Caller | `roles/run.invoker` (on `storeops-worker` and API outbox) | Authenticates Cloud Tasks HTTP dispatches and Cloud Scheduler outbox draining via OIDC tokens. |

---

## 3. Deployment Prerequisites

Before deploying, ensure:
1. Google Cloud SDK (`gcloud`) version >= 460.0.0 is installed.
2. An **explicit authorized development project** is designated (e.g., `storeops-dev-12345`).
3. Billing is enabled on the project with a budget alert.
4. Active `gcloud` authentication:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   ```

> **IMPORTANT**: The deployment scripts refuse to run if `STOREOPS_PROJECT_ID` or `GCP_PROJECT` is unset, preventing accidental deployment to arbitrary or production projects.

---

## 4. Automated Deployment

### Option A: Via Makefile (Recommended)

```bash
# 1. Set explicit target project and region
export STOREOPS_PROJECT_ID="your-authorized-project-id"
export STOREOPS_REGION="asia-southeast1"
export APP_ENV="dev"

# 2. Deploy infrastructure and services
make deploy-dev
```

### Option B: Via Terraform

```bash
cd infra/
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your project_id

terraform init
terraform plan
terraform apply
```

### Idempotent Deployment Steps Performed:
1. Enables required APIs (`run`, `cloudtasks`, `cloudscheduler`, `firestore`, `bigquery`, `storage`, `aiplatform`, `artifactregistry`).
2. Creates the 3 least-privilege service accounts and binds IAM roles.
3. Provisions the private media storage bucket with uniform bucket-level access.
4. Creates BigQuery dataset in Terraform and executes canonical DDL from `migrations/bigquery/001_initial_analytics.sql` (mirrored in `infra/bigquery_schema.sql`) to avoid Terraform table schema drift.
5. Deploys Firestore composite indexes from `infra/firestore.indexes.json` using `firebase deploy --only firestore:indexes --project=${PROJECT_ID}`.
6. Configures Cloud Tasks queue `storeops-work-queue`.
7. Deploys Private Worker Cloud Run service (`--no-allow-unauthenticated`, executing `python3 -m scripts.deploy.run_worker` on port 8001). Security is enforced by Cloud Run internal ingress and Google IAM; no in-container auth token parsing is needed.
8. Deploys Public API Cloud Run service.
9. Sets up Cloud Scheduler outbox drain job on `* * * * *` (pings `/health` heartbeat pending foundation `/outbox/drain` route integration).

---

## 5. Verification & Smoke Checks

Use `scripts/deploy/smoke_check.py` to verify the deployment:

```bash
# 1. Verify infrastructure configs offline
python3 scripts/deploy/smoke_check.py --verify-config-only

# 2. Run live smoke check against deployed service
export STOREOPS_API_URL="https://storeops-api-xxxx-as.a.run.app"
export STOREOPS_WORKER_URL="https://storeops-worker-xxxx-as.a.run.app"
python3 scripts/deploy/smoke_check.py
```

### Verification Criteria (AC-41):
- **Scaffold & Config Verification**: All infrastructure specifications, composite index definitions, versioned DDL, worker IAM policies, and Terraform modules are syntactically valid and verified.
- **Fail-Closed Verification**: `smoke_check.py` requires live URLs and credentials; without them, it exits 2 `[BLOCKED]` per fail-closed conventions.
- **Health Endpoint**: `GET /health` returns HTTP 200 with `status: "READY"` (or `"DEGRADED"`) conforming to `contracts/openapi.json`.
- **API Authentication**: Unauthenticated requests to protected API endpoints return HTTP 401.
- **Worker Isolation**: Direct public requests to the Worker service return HTTP 401, 403, or connection drop (enforcing private internal ingress and IAM perimeter isolation).
- **Clean Bootstrap**: Zero sample business records exist in the database (bootstrap is clean).
- **Live Dispatch Scope Note**: AC-41 verifies deployment repeatability, infrastructure definitions, and local job runner execution. Full end-to-end cloud dispatch with live Cloud Tasks and Cloud Run execution is validated in Task T12 (AC-29) once cloud infrastructure is provisioned.

---

## 6. Budget, Quotas & Cost Controls

1. **Development Budget Configuration ($100.00 USD)**:
   Google Cloud Billing budgets require billing-account level permissions. Configure the budget manually in the Cloud Console or via the Billing Budgets CLI:
   ```bash
   gcloud billing budgets create \
     --billing-account="<YOUR_BILLING_ACCOUNT_ID>" \
     --display-name="StoreOps Development Budget" \
     --budget-amount=100.00USD \
     --threshold-rule=percent=0.5 \
     --threshold-rule=percent=0.8 \
     --threshold-rule=percent=1.0
   ```
2. **Resource Scaling Caps**:
   - **Cloud Run Concurrency & Scaling**: Enforced via `--max-instances=3` in `deploy.sh` and `scaling { max_instance_count = 3 }` in `infra/main.tf` to prevent accidental cost overrun.
   - **Cloud Tasks Rate Limiting**: `max-dispatches-per-second=10`, `max-concurrent-dispatches=5`.
   - **Outbox Drain Heartbeat**: Cloud Scheduler triggers `GET /health` once per minute (`* * * * *`) as a liveness heartbeat pending foundation/coordinator integration of the internal `/outbox/drain` route.
   - **Foundation Model**: `gemini-3.8-flash` per `specs/01-architecture.md:83`.

---

## 7. Rollback Procedure

If a deployed revision introduces defects, roll back traffic immediately using `scripts/deploy/rollback.sh`:

```bash
# Roll back API to previous revision
./scripts/deploy/rollback.sh api

# Roll back Worker to specific revision
./scripts/deploy/rollback.sh worker storeops-worker-00003-def

# Roll back all services to their immediate previous revisions
./scripts/deploy/rollback.sh all
```

The script shifts 100% of Cloud Run traffic back to the specified revision with zero downtime.
