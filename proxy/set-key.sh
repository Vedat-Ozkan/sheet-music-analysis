#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT=${1:?usage: proxy/set-key.sh PROJECT_ID}
SERVICE=sheet-music-analysis
REGION=us-central1
ACCOUNT=$SERVICE@$PROJECT.iam.gserviceaccount.com
KEY=$(openssl rand -hex 32)

gcloud services enable secretmanager.googleapis.com --project "$PROJECT"
if ! gcloud secrets describe proxy-key --project "$PROJECT" >/dev/null 2>&1; then
  gcloud secrets create proxy-key --project "$PROJECT" --replication-policy=automatic
fi
gcloud secrets add-iam-policy-binding proxy-key --project "$PROJECT" --member="serviceAccount:$ACCOUNT" --role=roles/secretmanager.secretAccessor >/dev/null
VERSION=$(printf %s "$KEY" | gcloud secrets versions add proxy-key --project "$PROJECT" --data-file=- --format='value(name)')
VERSION=${VERSION##*/}

trap 'gcloud secrets versions disable "$VERSION" --secret proxy-key --project "$PROJECT" >/dev/null; echo "The Worker was not updated. Key version $VERSION is switched off again; nothing has changed." >&2' ERR
npx wrangler@4 deploy -c proxy/wrangler.jsonc
printf %s "$KEY" | npx wrangler@4 secret put PROXY_KEY -c proxy/wrangler.jsonc
trap - ERR

if ! gcloud run services update "$SERVICE" --project "$PROJECT" --region "$REGION" --update-secrets="PROXY_KEY=proxy-key:$VERSION"; then
  echo "The Worker sends key version $VERSION but the server was not given it. Run this script again." >&2
  exit 1
fi
echo "The Worker and the server both hold key version $VERSION."
