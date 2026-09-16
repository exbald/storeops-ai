#!/usr/bin/env bash
# ==============================================================================
# StoreOps Cloud Run Rollback Script (T11 / AC-41)
# Reverts traffic to a previous stable revision.
# ==============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SERVICE="${1:-}"
TARGET_REVISION="${2:-}"

usage() {
    echo "Usage: $0 <api|worker|all> [revision-name]"
    echo ""
    echo "Examples:"
    echo "  $0 api storeops-api-00004-abc   # Roll back API to specific revision"
    echo "  $0 api                          # Interactively select previous revision"
    echo "  $0 all                          # Roll back both services to previous revisions"
    exit 1
}

if [ -z "${SERVICE}" ]; then
    usage
fi

PROJECT_ID="${STOREOPS_PROJECT_ID:-${GCP_PROJECT:-}}"
if [ -z "${PROJECT_ID}" ]; then
    echo -e "${RED}ERROR: STOREOPS_PROJECT_ID or GCP_PROJECT environment variable must be set.${NC}"
    exit 1
fi

REGION="${STOREOPS_REGION:-asia-southeast1}"

rollback_service() {
    local SVC_NAME="storeops-${1}"
    local REV="${2:-}"

    echo -e "${BLUE}=== Rolling back ${SVC_NAME} ===${NC}"

    if [ -z "${REV}" ]; then
        echo "Fetching last 3 revisions for ${SVC_NAME}..."
        gcloud run revisions list \
            --service="${SVC_NAME}" \
            --region="${REGION}" \
            --project="${PROJECT_ID}" \
            --limit=3 \
            --format="table(name,active,creationTimestamp)"

        PREV_REV="$(gcloud run revisions list \
            --service="${SVC_NAME}" \
            --region="${REGION}" \
            --project="${PROJECT_ID}" \
            --limit=2 \
            --format="value(name)" | tail -n 1)"

        if [ -z "${PREV_REV}" ]; then
            echo -e "${RED}No previous revision found for ${SVC_NAME}.${NC}"
            return 1
        fi
        REV="${PREV_REV}"
    fi

    echo -e "${YELLOW}Shifting 100% traffic of ${SVC_NAME} to revision: ${REV}${NC}"
    gcloud run services update-traffic "${SVC_NAME}" \
        --to-revisions="${REV}=100" \
        --region="${REGION}" \
        --project="${PROJECT_ID}"

    echo -e "${GREEN}✓ ${SVC_NAME} traffic routed to ${REV}.${NC}"
}

case "${SERVICE}" in
    api)
        rollback_service "api" "${TARGET_REVISION}"
        ;;
    worker)
        rollback_service "worker" "${TARGET_REVISION}"
        ;;
    all)
        rollback_service "api" ""
        rollback_service "worker" ""
        ;;
    *)
        echo -e "${RED}Unknown service: ${SERVICE}${NC}"
        usage
        ;;
esac

echo -e "\n${GREEN}Rollback operation completed.${NC}"
