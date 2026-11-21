#!/usr/bin/env bash
set -euo pipefail
gh api -X PUT repos/Vedat-Ozkan/sheet-music-analysis/branches/main/protection --input - --jq '{checks: .required_status_checks.contexts, admins: .enforce_admins.enabled, force_pushes: .allow_force_pushes.enabled}' <<'JSON'
{"required_status_checks": {"strict": false, "contexts": ["test"]}, "enforce_admins": true, "required_pull_request_reviews": null, "restrictions": null, "allow_force_pushes": false, "allow_deletions": false}
JSON
