#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PROJECT=${1:?usage: server/monitoring/apply.sh PROJECT_ID ALERT_EMAIL}
EMAIL=${2:?usage: server/monitoring/apply.sh PROJECT_ID ALERT_EMAIL}
API=https://monitoring.googleapis.com/v3/projects/$PROJECT
TOKEN=$(gcloud auth print-access-token)

for file in tool_calls.yaml tool_latency.yaml *_ms.yaml; do
  name=${file%.yaml}
  gcloud logging metrics update "$name" --project="$PROJECT" --config-from-file="$file" 2>/dev/null \
    || gcloud logging metrics create "$name" --project="$PROJECT" --config-from-file="$file"
done

existing() { curl -sf -H "Authorization: Bearer $TOKEN" "$API/$1" | python3 -c "import json,sys; print('\n'.join(x['$2'] for x in json.load(sys.stdin).get('$1', [])))"; }

CHANNEL=$(curl -sf -H "Authorization: Bearer $TOKEN" "$API/notificationChannels" \
  | python3 -c "import json,sys; print(next((c['name'] for c in json.load(sys.stdin).get('notificationChannels', []) if c['labels'].get('email_address') == '$EMAIL'), ''))")
if [ -z "$CHANNEL" ]; then
  CHANNEL=$(curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$API/notificationChannels" \
    -d "{\"type\": \"email\", \"displayName\": \"Owner email\", \"labels\": {\"email_address\": \"$EMAIL\"}}" \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['name'])")
fi

for file in alert-*.json; do
  title=$(python3 -c "import json; print(json.load(open('$file'))['displayName'])")
  if existing alertPolicies displayName | grep -qxF "$title"; then continue; fi
  python3 -c "import json; d = json.load(open('$file')); d['notificationChannels'] = ['$CHANNEL']; print(json.dumps(d))" \
    | curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$API/alertPolicies" -d @- >/dev/null
done

title=$(python3 -c "import json; print(json.load(open('dashboard.json'))['displayName'])")
if ! gcloud monitoring dashboards list --project="$PROJECT" --format='value(displayName)' | grep -qxF "$title"; then
  gcloud monitoring dashboards create --project="$PROJECT" --config-from-file=dashboard.json
fi
