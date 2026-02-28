#!/bin/bash
# =============================================================================
# InspectAI — One-Click Deployment Script
# Deploys the full stack to Google Cloud
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔══════════════════════════════════════╗"
echo "║        InspectAI Deployment          ║"
echo "║      See More. Miss Nothing.         ║"
echo "╚══════════════════════════════════════╝"
echo -e "${NC}"

# ─── Check prerequisites ────────────────────────────────────────────────────

echo -e "${YELLOW}Checking prerequisites...${NC}"

command -v gcloud >/dev/null 2>&1 || { echo -e "${RED}gcloud CLI not found. Install: https://cloud.google.com/sdk/docs/install${NC}"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo -e "${RED}Docker not found. Install: https://docs.docker.com/get-docker/${NC}"; exit 1; }
command -v terraform >/dev/null 2>&1 || { echo -e "${YELLOW}Terraform not found. Skipping IaC (will use gcloud commands instead).${NC}"; USE_TERRAFORM=false; } || USE_TERRAFORM=true

echo -e "${GREEN}✓ Prerequisites OK${NC}"

# ─── Configuration ───────────────────────────────────────────────────────────

# Get project ID
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
    echo -e "${YELLOW}No GCP project set. Enter your project ID:${NC}"
    read -r PROJECT_ID
    gcloud config set project "$PROJECT_ID"
fi
echo -e "${GREEN}✓ Project: ${PROJECT_ID}${NC}"

REGION="us-central1"
REPO_NAME="inspectai"
IMAGE_NAME="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/backend"
BUCKET_NAME="${PROJECT_ID}-inspectai-evidence"
SERVICE_NAME="inspectai-backend"

# ─── Get API Key ─────────────────────────────────────────────────────────────

echo ""
echo -e "${YELLOW}Enter your Gemini API key (from https://aistudio.google.com/apikey):${NC}"
read -rs GEMINI_API_KEY
echo ""

if [ -z "$GEMINI_API_KEY" ]; then
    echo -e "${RED}API key is required${NC}"
    exit 1
fi

# ─── Enable APIs ─────────────────────────────────────────────────────────────

echo -e "\n${BLUE}Step 1/6: Enabling Google Cloud APIs...${NC}"
gcloud services enable \
    run.googleapis.com \
    firestore.googleapis.com \
    storage.googleapis.com \
    aiplatform.googleapis.com \
    secretmanager.googleapis.com \
    artifactregistry.googleapis.com \
    --quiet

echo -e "${GREEN}✓ APIs enabled${NC}"

# ─── Create Artifact Registry ────────────────────────────────────────────────

echo -e "\n${BLUE}Step 2/6: Setting up Artifact Registry...${NC}"
gcloud artifacts repositories create ${REPO_NAME} \
    --repository-format=docker \
    --location=${REGION} \
    --quiet 2>/dev/null || echo "Repository already exists"

# Configure Docker auth
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet

echo -e "${GREEN}✓ Artifact Registry ready${NC}"

# ─── Build and Push Docker Image ─────────────────────────────────────────────

echo -e "\n${BLUE}Step 3/6: Building and pushing Docker image...${NC}"
docker build -t ${IMAGE_NAME}:latest .
docker push ${IMAGE_NAME}:latest
echo -e "${GREEN}✓ Image pushed to ${IMAGE_NAME}${NC}"

# ─── Create Cloud Storage Bucket ─────────────────────────────────────────────

echo -e "\n${BLUE}Step 4/6: Setting up Cloud Storage...${NC}"
gsutil mb -p ${PROJECT_ID} -l ${REGION} gs://${BUCKET_NAME}/ 2>/dev/null || echo "Bucket already exists"
gsutil cors set <(echo '[{"origin":["*"],"method":["GET","PUT","POST"],"responseHeader":["Content-Type"],"maxAgeSeconds":3600}]') gs://${BUCKET_NAME}/
echo -e "${GREEN}✓ Storage bucket ready: ${BUCKET_NAME}${NC}"

# ─── Store API Key in Secret Manager ─────────────────────────────────────────

echo -e "\n${BLUE}Step 5/6: Storing API key in Secret Manager...${NC}"
echo -n "${GEMINI_API_KEY}" | gcloud secrets create gemini-api-key \
    --data-file=- \
    --quiet 2>/dev/null || \
echo -n "${GEMINI_API_KEY}" | gcloud secrets versions add gemini-api-key \
    --data-file=- \
    --quiet

echo -e "${GREEN}✓ API key stored securely${NC}"

# ─── Deploy to Cloud Run ─────────────────────────────────────────────────────

echo -e "\n${BLUE}Step 6/6: Deploying to Cloud Run...${NC}"
gcloud run deploy ${SERVICE_NAME} \
    --image=${IMAGE_NAME}:latest \
    --region=${REGION} \
    --platform=managed \
    --allow-unauthenticated \
    --port=8080 \
    --cpu=2 \
    --memory=1Gi \
    --timeout=3600 \
    --min-instances=0 \
    --max-instances=5 \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GCS_BUCKET_NAME=${BUCKET_NAME},USE_MEMORY_STORE=false" \
    --set-secrets="GOOGLE_API_KEY=gemini-api-key:latest" \
    --quiet

# Get the deployed URL
BACKEND_URL=$(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format='value(status.url)')

echo -e "\n${GREEN}"
echo "╔══════════════════════════════════════════════════════╗"
echo "║           🎉 Deployment Complete!                   ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║                                                      ║"
echo "║  Backend URL: ${BACKEND_URL}"
echo "║  Storage:     gs://${BUCKET_NAME}"
echo "║  Region:      ${REGION}"
echo "║                                                      ║"
echo "║  Next steps:                                         ║"
echo "║  1. Update frontend VITE_API_URL with backend URL   ║"
echo "║  2. Deploy frontend (or run locally)                 ║"
echo "║  3. Test: curl ${BACKEND_URL}/health"
echo "║                                                      ║"
echo "╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"
