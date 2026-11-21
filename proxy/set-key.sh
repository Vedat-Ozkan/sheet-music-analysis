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
PREVIOUS=$(gcloud secrets versions list proxy-key --project "$PROJECT" --filter=state:enabled --sort-by=~createTime --limit=1 --format='value(name)')
PREVIOUS=${PREVIOUS##*/}
VERSION=$(printf %s "$KEY" | gcloud secrets versions add proxy-key --project "$PROJECT" --data-file=- --format='value(name)')
VERSION=${VERSION##*/}
BOTH="PROXY_KEY=proxy-key:$VERSION${PREVIOUS:+,PROXY_KEY_PREVIOUS=proxy-key:$PREVIOUS}"
if [ -n "$PREVIOUS" ]; then
  BACK=(--update-secrets="PROXY_KEY=proxy-key:$PREVIOUS" --remove-secrets=PROXY_KEY_PREVIOUS)
else
  BACK=(--remove-secrets=PROXY_KEY)
fi

trap 'gcloud secrets versions disable "$VERSION" --secret proxy-key --project "$PROJECT" >/dev/null; echo "The server was not given key version $VERSION. It is switched off again; nothing has changed." >&2' ERR
gcloud run services update "$SERVICE" --project "$PROJECT" --region "$REGION" --update-secrets="$BOTH"

trap 'gcloud run services update "$SERVICE" --project "$PROJECT" --region "$REGION" "${BACK[@]}"; gcloud secrets versions disable "$VERSION" --secret proxy-key --project "$PROJECT" >/dev/null; echo "The Worker was not updated. The server is back on what it accepted before, and version $VERSION is switched off." >&2' ERR
npx wrangler@4 deploy -c proxy/wrangler.jsonc
printf %s "$KEY" | npx wrangler@4 secret put PROXY_KEY -c proxy/wrangler.jsonc
trap - ERR

if [ -n "$PREVIOUS" ] && ! gcloud run services update "$SERVICE" --project "$PROJECT" --region "$REGION" --remove-secrets=PROXY_KEY_PREVIOUS; then
  echo "The Worker and the server hold key version $VERSION, but the server still accepts version $PREVIOUS too. Run: gcloud run services update $SERVICE --region $REGION --remove-secrets=PROXY_KEY_PREVIOUS" >&2
  exit 1
fi
echo "The Worker and the server both hold key version $VERSION."
