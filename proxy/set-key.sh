#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT=${1:?usage: proxy/set-key.sh PROJECT_ID}
KEY=$(openssl rand -hex 32)

gcloud services enable secretmanager.googleapis.com --project "$PROJECT"
if gcloud secrets describe proxy-key --project "$PROJECT" >/dev/null 2>&1; then
  printf %s "$KEY" | gcloud secrets versions add proxy-key --project "$PROJECT" --data-file=-
else
  printf %s "$KEY" | gcloud secrets create proxy-key --project "$PROJECT" --replication-policy=automatic --data-file=-
fi
printf %s "$KEY" | npx wrangler@4 secret put PROXY_KEY -c proxy/wrangler.jsonc
echo "The Worker now sends the new key. Deploy the server next: server/deploy.sh $PROJECT"
