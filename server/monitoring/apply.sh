#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PROJECT=${1:?usage: server/monitoring/apply.sh PROJECT_ID ALERT_EMAIL}
EMAIL=${2:?usage: server/monitoring/apply.sh PROJECT_ID ALERT_EMAIL}
API=https://monitoring.googleapis.com/v3/projects/$PROJECT
TOKEN=$(gcloud auth print-access-token)

for file in tool_calls.yaml tool_latency.yaml held_open_requests.yaml *_ms.yaml; do
  name=${file%.yaml}
  gcloud logging metrics update "$name" --project="$PROJECT" --config-from-file="$file" 2>/dev/null \
    || gcloud logging metrics create "$name" --project="$PROJECT" --config-from-file="$file"
done


CHANNEL=$(curl -sf -H "Authorization: Bearer $TOKEN" "$API/notificationChannels" \
  | python3 -c "import json,sys; print(next((c['name'] for c in json.load(sys.stdin).get('notificationChannels', []) if c['labels'].get('email_address') == '$EMAIL'), ''))")
if [ -z "$CHANNEL" ]; then
  CHANNEL=$(curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$API/notificationChannels" \
    -d "{\"type\": \"email\", \"displayName\": \"Owner email\", \"labels\": {\"email_address\": \"$EMAIL\"}}" \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['name'])")
fi

for file in alert-*.json; do
  title=$(python3 -c "import json; print(json.load(open('$file'))['displayName'])")
  policy=$(curl -sf -H "Authorization: Bearer $TOKEN" "$API/alertPolicies" \
    | python3 -c "import json,sys; print(next((p['name'] for p in json.load(sys.stdin).get('alertPolicies', []) if p['displayName'] == '$title'), ''))")
  body=$(python3 -c "import json; d = json.load(open('$file')); d['notificationChannels'] = ['$CHANNEL']; print(json.dumps(d))")
  for attempt in 1 2 3 4 5 6; do
    if [ -n "$policy" ]; then
      echo "$body" | curl -sf -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "https://monitoring.googleapis.com/v3/$policy" -d @- >/dev/null && break
    else
      echo "$body" | curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$API/alertPolicies" -d @- >/dev/null && break
    fi
    [ "$attempt" = 6 ] && exit 1
    sleep 20
  done
done

SERVICE=$API/services/sheet-music-analysis
if ! curl -sf -H "Authorization: Bearer $TOKEN" "$SERVICE" >/dev/null; then
  curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$API/services?serviceId=sheet-music-analysis" \
    -d '{"displayName": "Sheet Music Analysis (production)", "custom": {}}' >/dev/null
fi
for file in slo-*.json; do
  id=${file%.json}
  if curl -sf -H "Authorization: Bearer $TOKEN" "$SERVICE/serviceLevelObjectives/$id" >/dev/null; then continue; fi
  curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$SERVICE/serviceLevelObjectives?serviceLevelObjectiveId=$id" -d @"$file" >/dev/null
done

title=$(python3 -c "import json; print(json.load(open('dashboard.json'))['displayName'])")
if ! gcloud monitoring dashboards list --project="$PROJECT" --format='value(displayName)' | grep -qxF "$title"; then
  gcloud monitoring dashboards create --project="$PROJECT" --config-from-file=dashboard.json
fi
