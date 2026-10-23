#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT=${1:?usage: server/deploy.sh PROJECT_ID [staging]}
STAGE=${2:-production}
REGION=us-central1
SERVICE=sheet-music-analysis
BUCKET=$PROJECT-data
IMAGE=$REGION-docker.pkg.dev/$PROJECT/$SERVICE/server
RUN_SERVICE=$SERVICE
ACCESS=--allow-unauthenticated
if [ "$STAGE" = staging ]; then
  BUCKET=$PROJECT-staging-data
  IMAGE=$IMAGE:staging
  RUN_SERVICE=$SERVICE-staging
  ACCESS=--no-allow-unauthenticated
elif [ "$STAGE" != production ]; then
  echo "unknown stage: $STAGE" >&2
  exit 1
fi
ACCOUNT=$SERVICE@$PROJECT.iam.gserviceaccount.com

gcloud config set project "$PROJECT"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com storage.googleapis.com

if ! gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access
fi
cat > /tmp/$SERVICE-lifecycle.json <<'EOF'
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": 1, "matchesPrefix": ["scores/", "files/"]}}]}
EOF
gcloud storage buckets update "gs://$BUCKET" --lifecycle-file=/tmp/$SERVICE-lifecycle.json

if ! gcloud iam service-accounts describe "$ACCOUNT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SERVICE" --display-name="Sheet Music Analysis server"
fi
for attempt in 1 2 3 4 5 6; do
  gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$ACCOUNT" --role=roles/storage.objectAdmin >/dev/null && break
  [ "$attempt" = 6 ] && exit 1
  sleep 10
done

if ! gcloud artifacts repositories describe "$SERVICE" --location="$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$SERVICE" --repository-format=docker --location="$REGION"
fi
cat > /tmp/$SERVICE-cleanup.json <<'EOF'
[{"name": "untagged", "action": {"type": "Delete"}, "condition": {"tagState": "UNTAGGED"}}]
EOF
gcloud artifacts repositories set-cleanup-policies "$SERVICE" --location="$REGION" --policy=/tmp/$SERVICE-cleanup.json --no-dry-run
BASE=$REGION-docker.pkg.dev/$PROJECT/$SERVICE/base:$(cat Dockerfile.base pyproject.toml uv.lock server/requirements-agnn.txt | sha256sum | cut -c1-16)
if ! gcloud artifacts docker images describe "$BASE" >/dev/null 2>&1; then
  gcloud builds submit --config=cloudbuild.yaml --substitutions=_DOCKERFILE=Dockerfile.base,_IMAGE="$BASE"
fi
gcloud builds submit --config=cloudbuild.yaml --substitutions=_BASE="$BASE",_IMAGE="$IMAGE"

if [ "$STAGE" = staging ]; then
  PUBLIC_BASE_URL=${PUBLIC_BASE_URL:-https://$RUN_SERVICE-$(gcloud projects describe "$PROJECT" --format='value(projectNumber)').$REGION.run.app}
fi
PUBLIC_BASE_URL=${PUBLIC_BASE_URL:-https://mcp.sheetmusicanalysis.com}
gcloud run deploy "$RUN_SERVICE" --image="$IMAGE" --region="$REGION" \
  --service-account="$ACCOUNT" "$ACCESS" \
  --execution-environment=gen2 --cpu=2 --memory=4Gi --concurrency=4 --min-instances=0 --max-instances=1 --timeout=300 \
  --set-env-vars="BUCKET=$BUCKET,PUBLIC_BASE_URL=$PUBLIC_BASE_URL"
echo "Connector URL: $PUBLIC_BASE_URL/mcp"
