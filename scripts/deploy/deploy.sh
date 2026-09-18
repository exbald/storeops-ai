#!/usr/bin/env bash
# ==============================================================================
# StoreOps Cloud Development Deployment Script (T11 / AC-41)
# Repeatable deployment to an explicitly authorized Google Cloud project.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== StoreOps Cloud Deployment (T11 / AC-41) ===${NC}"

# 1. Gate: Require explicit project ID; never deploy to an implicit or default project
PROJECT_ID="${STOREOPS_PROJECT_ID:-${GCP_PROJECT:-}}"
if [ -z "${PROJECT_ID}" ]; then
    echo -e "${RED}BLOCKED: Cloud deployment requires an explicit authorized project.${NC}"
    echo "Set STOREOPS_PROJECT_ID or GCP_PROJECT environment variable."
    echo "Example: export STOREOPS_PROJECT_ID=\"my-authorized-storeops-dev\""
    exit 2
fi

# 2. Gate: Production safety guardrail
APP_ENV="${APP_ENV:-dev}"
if [[ "${PROJECT_ID}" =~ prod ]] && [ "${STOREOPS_ALLOW_PROD:-0}" != "1" ]; then
    echo -e "${RED}ERROR: Target project '${PROJECT_ID}' appears to be PRODUCTION.${NC}"
    echo "Automatic deployment aborted. Set STOREOPS_ALLOW_PROD=1 to override."
    exit 1
fi

# 3. Gate: Tool availability
if ! command -v gcloud &>/dev/null; then
    echo -e "${RED}BLOCKED: gcloud CLI is not installed or not in PATH.${NC}"
    exit 2
fi

# Check active authentication
ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null || true)"
if [ -z "${ACTIVE_ACCOUNT}" ]; then
    echo -e "${RED}BLOCKED: No active gcloud authentication found.${NC}"
    echo "Run: gcloud auth login && gcloud auth application-default login"
    exit 2
fi

echo -e "${GREEN}✓ Authorized project:${NC} ${PROJECT_ID}"
echo -e "${GREEN}✓ Active account:${NC} ${ACTIVE_ACCOUNT}"
echo -e "${GREEN}✓ Environment:${NC} ${APP_ENV}"

REGION="${STOREOPS_REGION:-asia-southeast1}"
MEDIA_BUCKET="storeops-${PROJECT_ID}-media"
BQ_DATASET="storeops_${APP_ENV}"
TASKS_QUEUE="storeops-work-queue"
API_SA="storeops-api-sa@${PROJECT_ID}.iam.gserviceaccount.com"
WORKER_SA="storeops-worker-sa@${PROJECT_ID}.iam.gserviceaccount.com"
INVOKER_SA="storeops-invoker-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# Load GEMINI_API_KEY from .env if present and unset
if [ -z "${GEMINI_API_KEY:-}" ] && [ -f "${ROOT_DIR}/.env" ]; then
    GEMINI_API_KEY="$(grep -E '^GEMINI_API_KEY=' "${ROOT_DIR}/.env" | cut -d'=' -f2- | tr -d '\"' | tr -d "'")"
fi

# Dry run mode check
if [ "${1:-}" = "--dry-run" ]; then
    echo -e "${YELLOW}[DRY RUN MODE]${NC} Validating configuration..."
    echo "  Project: ${PROJECT_ID}"
    echo "  Region: ${REGION}"
    echo "  Bucket: ${MEDIA_BUCKET}"
    echo "  BigQuery: ${BQ_DATASET}"
    echo "  API Service Account: ${API_SA}"
    echo "  Worker Service Account: ${WORKER_SA}"
    echo "  Invoker Service Account: ${INVOKER_SA}"
    echo -e "${GREEN}Configuration valid.${NC}"
    exit 0
fi

# 4. Enable Google Cloud APIs
echo -e "\n${BLUE}Step 1: Enabling required APIs...${NC}"
gcloud services enable \
    run.googleapis.com \
    cloudtasks.googleapis.com \
    cloudscheduler.googleapis.com \
    firestore.googleapis.com \
    bigquery.googleapis.com \
    storage.googleapis.com \
    aiplatform.googleapis.com \
    artifactregistry.googleapis.com \
    --project="${PROJECT_ID}"

# 5. Service Accounts Setup
echo -e "\n${BLUE}Step 2: Provisioning least-privilege service accounts...${NC}"
for SA_NAME in "storeops-api-sa" "storeops-worker-sa" "storeops-invoker-sa"; do
    if ! gcloud iam service-accounts describe "${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" --project="${PROJECT_ID}" &>/dev/null; then
        gcloud iam service-accounts create "${SA_NAME}" \
            --display-name="StoreOps ${SA_NAME}" \
            --project="${PROJECT_ID}"
    fi
done

# Assign Roles
echo "Assigning IAM roles..."
# API SA Roles
for ROLE in "roles/datastore.user" "roles/storage.objectAdmin" "roles/bigquery.dataEditor" "roles/bigquery.jobUser" "roles/cloudtasks.enqueuer"; do
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
        --member="serviceAccount:${API_SA}" \
        --role="${ROLE}" \
        --condition=None --quiet >/dev/null
done

# Worker SA Roles
for ROLE in "roles/datastore.user" "roles/storage.objectAdmin" "roles/bigquery.dataEditor" "roles/bigquery.jobUser" "roles/aiplatform.user"; do
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
        --member="serviceAccount:${WORKER_SA}" \
        --role="${ROLE}" \
        --condition=None --quiet >/dev/null
done

# Allow API SA to generate OIDC tokens as Invoker SA
gcloud iam service-accounts add-iam-policy-binding "${INVOKER_SA}" \
    --member="serviceAccount:${API_SA}" \
    --role="roles/iam.serviceAccountUser" \
    --project="${PROJECT_ID}" --quiet >/dev/null

# 6. Storage Bucket Setup
echo -e "\n${BLUE}Step 3: Configuring Cloud Storage media bucket...${NC}"
if ! gcloud storage buckets describe "gs://${MEDIA_BUCKET}" --project="${PROJECT_ID}" &>/dev/null; then
    gcloud storage buckets create "gs://${MEDIA_BUCKET}" \
        --location="${REGION}" \
        --project="${PROJECT_ID}" \
        --uniform-bucket-level-access
fi

# 7. BigQuery Dataset & Tables Setup (applies canonical migration DDL)
echo -e "\n${BLUE}Step 4: Creating BigQuery analytics dataset...${NC}"
if ! bq show --project_id="${PROJECT_ID}" "${BQ_DATASET}" &>/dev/null; then
    bq --location="${REGION}" mk --dataset "${PROJECT_ID}:${BQ_DATASET}"
fi

BQ_DDL_FILE="${ROOT_DIR}/migrations/bigquery/001_initial_analytics.sql"
if [ ! -f "${BQ_DDL_FILE}" ]; then
    BQ_DDL_FILE="${ROOT_DIR}/infra/bigquery_schema.sql"
fi

if [ -f "${BQ_DDL_FILE}" ]; then
    echo "Applying BigQuery schema DDL statement-by-statement from ${BQ_DDL_FILE}..."
    PROJECT_ID="${PROJECT_ID}" BQ_DATASET="${BQ_DATASET}" BQ_DDL_FILE="${BQ_DDL_FILE}" python3 -c "
import os, subprocess
project_id = os.environ['PROJECT_ID']
dataset_id = os.environ['BQ_DATASET']
ddl_file = os.environ['BQ_DDL_FILE']

with open(ddl_file, 'r', encoding='utf-8') as f:
    sql = f.read()

# Filter full-line comments so statement blocks are not filtered out
cleaned_lines = [l for l in sql.splitlines() if not l.strip().startswith('--')]
cleaned_sql = '\n'.join(cleaned_lines)
statements = [s.strip() for s in cleaned_sql.split(';') if s.strip()]

for stmt in statements:
    first_line = stmt.splitlines()[0].strip()
    print(f'Executing DDL: {first_line}...')
    cmd = ['bq', 'query', '--use_legacy_sql=false', f'--dataset_id={dataset_id}', f'--project_id={project_id}', stmt]
    subprocess.run(cmd, check=True)
"
fi

# 8. Firestore Database and Indexes
echo -e "\n${BLUE}Step 5: Verifying Firestore and applying indexes...${NC}"
if [ -f "${ROOT_DIR}/infra/firestore.indexes.json" ]; then
    echo "Deploying Firestore composite indexes..."
    if [ -f "${SCRIPT_DIR}/deploy_firestore_indexes.py" ]; then
        python3 "${SCRIPT_DIR}/deploy_firestore_indexes.py" "${PROJECT_ID}"
    elif command -v firebase &>/dev/null; then
        firebase deploy --only firestore:indexes --project="${PROJECT_ID}"
    else
        echo -e "${RED}ERROR: Neither deploy_firestore_indexes.py nor firebase CLI found.${NC}"
        if [ "${ALLOW_SKIP_INDEXES:-0}" != "1" ]; then
            exit 1
        fi
    fi
fi

# 9. Cloud Tasks Queue
echo -e "\n${BLUE}Step 6: Provisioning Cloud Tasks queue...${NC}"
if ! gcloud tasks queues describe "${TASKS_QUEUE}" --location="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    gcloud tasks queues create "${TASKS_QUEUE}" \
        --location="${REGION}" \
        --max-dispatches-per-second=10 \
        --max-concurrent-dispatches=5 \
        --max-attempts=5 \
        --project="${PROJECT_ID}"
fi

# 10. Deploy Cloud Run Private Worker
echo -e "\n${BLUE}Step 7: Deploying Private Cloud Run Worker...${NC}"
gcloud run deploy storeops-worker \
    --source="${ROOT_DIR}" \
    --command="python3,-m,scripts.deploy.run_worker" \
    --port=8001 \
    --service-account="${WORKER_SA}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --ingress="internal" \
    --max-instances=3 \
    --no-allow-unauthenticated \
    --set-env-vars="APP_ENV=${APP_ENV},PROFILE=CLOUD,STATE_BACKEND=firestore,DATA_BACKEND=CLOUD,GCP_PROJECT=${PROJECT_ID},FIREBASE_PROJECT_ID=${PROJECT_ID},MEDIA_BUCKET=${MEDIA_BUCKET},BIGQUERY_DATASET=${BQ_DATASET},AI_MODE=LIVE,MODEL_ID=gemini-3.8-flash,GEMINI_API_KEY=${GEMINI_API_KEY:-}" \
    --quiet

# Grant Invoker SA permission to call private worker
gcloud run services add-iam-policy-binding storeops-worker \
    --member="serviceAccount:${INVOKER_SA}" \
    --role="roles/run.invoker" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --quiet

WORKER_URL="$(gcloud run services describe storeops-worker --region="${REGION}" --project="${PROJECT_ID}" --format="value(status.url)")"

# 11. Deploy Cloud Run Public API
echo -e "\n${BLUE}Step 8: Deploying Public Cloud Run API...${NC}"
gcloud run deploy storeops-api \
    --source="${ROOT_DIR}" \
    --command="uvicorn,apps.api.main:app,--host,0.0.0.0,--port,8000" \
    --service-account="${API_SA}" \
    --port=8000 \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --ingress="all" \
    --max-instances=1 \
    --allow-unauthenticated \
    --set-env-vars="APP_ENV=${APP_ENV},PROFILE=CLOUD,STATE_BACKEND=firestore,DATA_BACKEND=CLOUD,GCP_PROJECT=${PROJECT_ID},FIREBASE_PROJECT_ID=${PROJECT_ID},MEDIA_BUCKET=${MEDIA_BUCKET},BIGQUERY_DATASET=${BQ_DATASET},WORKER_URL=${WORKER_URL},TASKS_QUEUE=${TASKS_QUEUE},INVOKER_SERVICE_ACCOUNT=${INVOKER_SA},AI_MODE=LIVE,MODEL_ID=gemini-3.8-flash,GEMINI_API_KEY=${GEMINI_API_KEY:-},API_URL=https://storeops-api-967137522464.asia-southeast1.run.app,MEDIA_BASE_URL=https://storeops-api-967137522464.asia-southeast1.run.app/media" \
    --quiet

API_URL="$(gcloud run services describe storeops-api --region="${REGION}" --project="${PROJECT_ID}" --format="value(status.url)")"

# 12. Cloud Scheduler Outbox Draining Job
# Configured to ping GET /health as a 1-minute heartbeat until foundation /outbox/drain route is integrated
echo -e "\n${BLUE}Step 9: Configuring Cloud Scheduler outbox drain job...${NC}"
if ! gcloud scheduler jobs describe "storeops-outbox-drain" --location="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    gcloud scheduler jobs create http "storeops-outbox-drain" \
        --schedule="* * * * *" \
        --uri="${API_URL}/health" \
        --http-method=GET \
        --oidc-service-account-email="${INVOKER_SA}" \
        --oidc-token-audience="${API_URL}" \
        --location="${REGION}" \
        --project="${PROJECT_ID}" \
        --time-zone="Etc/UTC"
fi

# 13. Deploy Cloud Run Web Dashboard (Next.js)
echo -e "\n${BLUE}Step 10: Deploying Public Cloud Run Web Dashboard...${NC}"
WEB_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/storeops-web:latest"
echo "Building web image on Cloud Build..."
gcloud builds submit \
    --config="${ROOT_DIR}/infra/cloudbuild.web.yaml" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    "${ROOT_DIR}" \
    --quiet

gcloud run deploy storeops-web \
    --image="${WEB_IMAGE}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --port=3000 \
    --ingress="all" \
    --max-instances=3 \
    --allow-unauthenticated \
    --set-env-vars="NODE_ENV=production,NEXT_PUBLIC_API_URL=${API_URL},NEXT_PUBLIC_WORKSPACE_ID=00000000-0000-0000-0000-000000000001,NEXT_PUBLIC_AUTH_TOKEN=dev-admin-token" \
    --quiet

WEB_URL="$(gcloud run services describe storeops-web --region="${REGION}" --project="${PROJECT_ID}" --format="value(status.url)")"

echo -e "\n${GREEN}=== Deployment Complete ===${NC}"
echo "Web URL:      ${WEB_URL}"
echo "API URL:      ${API_URL}"
echo "Worker URL:   ${WORKER_URL} (PRIVATE)"
echo "Media Bucket: gs://${MEDIA_BUCKET}"
echo "BigQuery:     ${PROJECT_ID}:${BQ_DATASET}"
echo "Scheduler:    storeops-outbox-drain (* * * * *)"
echo ""
echo "Run smoke checks with:"
echo "  STOREOPS_API_URL=${API_URL} python3 scripts/deploy/smoke_check.py"
