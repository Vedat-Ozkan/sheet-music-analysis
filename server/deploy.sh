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
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$ACCOUNT" --role=roles/storage.objectAdmin >/dev/null

if ! gcloud artifacts repositories describe "$SERVICE" --location="$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$SERVICE" --repository-format=docker --location="$REGION"
fi
gcloud builds submit --tag "$IMAGE" --timeout=40m

# One instance at most and the daily limits in server/app.py keep the cost near zero (owner's $5 limit).
# Four drafts at about 0.8 GB each fit in 4 GiB alongside the server.
URL=$(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url)' 2>/dev/null || true)
gcloud run deploy "$SERVICE" --image="$IMAGE" --region="$REGION" \
  --service-account="$ACCOUNT" --allow-unauthenticated \
  --cpu=2 --memory=4Gi --concurrency=4 --min-instances=0 --max-instances=1 --timeout=300 \
  --set-env-vars="BUCKET=$BUCKET,PUBLIC_BASE_URL=${PUBLIC_BASE_URL:-$URL}"

# On the first deploy the address is only known afterwards, and the server needs it for its links.
if [ -z "${PUBLIC_BASE_URL:-$URL}" ]; then
  URL=$(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')
  gcloud run services update "$SERVICE" --region="$REGION" --update-env-vars="PUBLIC_BASE_URL=$URL"
fi
echo "Connector URL: ${PUBLIC_BASE_URL:-$(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')}/mcp"
