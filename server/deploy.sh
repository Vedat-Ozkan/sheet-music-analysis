#!/usr/bin/env bash
# Build the image on Cloud Build and deploy it to Cloud Run.
# Usage: server/deploy.sh PROJECT_ID
# Needs gcloud, logged in (`gcloud auth login`). Safe to run again; existing resources are kept.
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT=${1:?usage: server/deploy.sh PROJECT_ID}
# Cloud Run's and Cloud Storage's free tiers apply in us-central1.
REGION=us-central1
SERVICE=sheet-music-analysis
BUCKET=$PROJECT-data
IMAGE=$REGION-docker.pkg.dev/$PROJECT/$SERVICE/server
ACCOUNT=$SERVICE@$PROJECT.iam.gserviceaccount.com

gcloud config set project "$PROJECT"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com storage.googleapis.com

if ! gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access
fi
# Uploaded scores and drawn pages are deleted after a day; the daily usage counts under usage/ are kept.
cat > /tmp/$SERVICE-lifecycle.json <<'EOF'
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": 1, "matchesPrefix": ["scores/", "files/"]}}]}
EOF
gcloud storage buckets update "gs://$BUCKET" --lifecycle-file=/tmp/$SERVICE-lifecycle.json

if ! gcloud iam service-accounts describe "$ACCOUNT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SERVICE" --display-name="Sheet Music Analysis server"
fi
# A new service account takes a little while to become visible to Cloud Storage, so retry for up to a minute.
for attempt in 1 2 3 4 5 6; do
  gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$ACCOUNT" --role=roles/storage.objectAdmin >/dev/null && break
  [ "$attempt" = 6 ] && exit 1
  sleep 10
done

if ! gcloud artifacts repositories describe "$SERVICE" --location="$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$SERVICE" --repository-format=docker --location="$REGION"
fi
# The base holds PyTorch, the model and its weights (about 2 GB, 6-8 minutes to build). Its tag is a hash of what
# goes into it, so it is rebuilt only when that changes; a code change builds just the thin layer on top.
BASE=$REGION-docker.pkg.dev/$PROJECT/$SERVICE/base:$(cat Dockerfile.base pyproject.toml uv.lock server/requirements-agnn.txt | sha256sum | cut -c1-16)
if ! gcloud artifacts docker images describe "$BASE" >/dev/null 2>&1; then
  gcloud builds submit --config=cloudbuild.yaml --substitutions=_DOCKERFILE=Dockerfile.base,_IMAGE="$BASE"
fi
gcloud builds submit --config=cloudbuild.yaml --substitutions=_BASE="$BASE",_IMAGE="$IMAGE"

# One instance at most and the daily limits in server/app.py keep the cost near zero (owner's $5 limit).
# Four drafts at about 0.8 GB each fit in 4 GiB alongside the server.
# gen2: the first-generation sandbox is slow at the many small file reads of loading PyTorch (first draft 78 s).
# The Cloudflare Worker in proxy/ serves the server under our domain; links and the cards' CSP use it.
PUBLIC_BASE_URL=${PUBLIC_BASE_URL:-https://mcp.sheetmusicanalysis.com}
gcloud run deploy "$SERVICE" --image="$IMAGE" --region="$REGION" \
  --service-account="$ACCOUNT" --allow-unauthenticated \
  --execution-environment=gen2 --cpu=2 --memory=4Gi --concurrency=4 --min-instances=0 --max-instances=1 --timeout=300 \
  --set-env-vars="BUCKET=$BUCKET,PUBLIC_BASE_URL=$PUBLIC_BASE_URL"
echo "Connector URL: $PUBLIC_BASE_URL/mcp"
