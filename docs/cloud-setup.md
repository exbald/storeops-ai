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
| Gemini 2.5 / |
|   Vertex AI  |
+--------------+
```

### Components

| Component | GCP Service | Visibility | Configuration / Notes |
|---|---|---|---|
| **API Service** | Cloud Run (`storeops-api`) | Public Ingress | Port 8000. Firebase token authentication. Ingress `all`. |
| **Worker Service** | Cloud Run (`storeops-worker`) | Private / Internal | Port 8001. Ingress `internal`. Only invokable by Invoker SA via OIDC. |
| **Asynchronous Jobs** | Cloud Tasks (`storeops-work-queue`) | Regional | Rate-limited (10 dispatches/sec, max 5 concurrent). |
| **Scheduled Outbox** | Cloud Scheduler (`storeops-outbox-drain`) | Regional | Runs `* * * * *` (every 1 min), calls `/outbox/drain` with OIDC. |
| **Media Storage** | Cloud Storage (`storeops-${PROJECT_ID}-media`) | Private | Uniform bucket-level access, signed download URLs, CORS enabled. |
| **Operational DB** | Cloud Firestore | Native Mode | Composite indexes (`infra/firestore.indexes.json`). |
| **Analytics Store** | BigQuery (`storeops_${APP_ENV}`) | Regional | Partitioned by `business_date`, clustered by `workspace_id, store_code, sku`. |
| **Foundation Model** | Vertex AI / Gemini API | Global Endpoint | `gemini-2.5-flash`, structured outputs, one-shot repair. |

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
1. Enables required APIs (`run`, `cloudtasks`, `cloudscheduler`, `firestore`, `bigquery`, `storage`, `aiplatform`).
2. Creates the 3 least-privilege service accounts and binds IAM roles.
3. Provisions the private media storage bucket with uniform bucket-level access.
4. Creates BigQuery dataset and executes `infra/bigquery_schema.sql` (partitioning & clustering).
5. Deploys Firestore composite indexes from `infra/firestore.indexes.json`.
6. Configures Cloud Tasks queue `storeops-work-queue`.
7. Deploys Private Worker Cloud Run service (`--no-allow-unauthenticated`).
8. Deploys Public API Cloud Run service.
9. Sets up Cloud Scheduler outbox drain job on `* * * * *`.

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
- `GET /health` returns HTTP 200 `{"status": "ok"}`.
- Unauthenticated requests to protected API endpoints return HTTP 401.
- Direct public requests to the Worker service return HTTP 401 or 403 (enforcing private internal ingress).
- Zero sample business records exist in the database (bootstrap is clean).

---

## 6. Budget & Quotas

1. **Development Budget**:
   A budget of **$100.00 USD** is configured with notification thresholds at 50%, 80%, and 100%.
2. **Quotas & Cost Controls**:
   - Model calls: Rate limited to 10 requests per second.
   - Max concurrent dispatches in Cloud Tasks: 5.
   - BigQuery query byte limit: 100 MB per analytical query.
   - Cloud Run container scaling: `max-instances=3` for development.

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
