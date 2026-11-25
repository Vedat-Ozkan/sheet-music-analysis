#!/usr/bin/env bash
set -euo pipefail
commit=${1:-HEAD}
tree=$(git rev-parse "$commit^{tree}")
repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
gh run list --workflow tests --status success --limit 30 --json databaseId,headSha --jq '.[] | "\(.databaseId) \(.headSha)"' |
while read -r run sha; do
  [ "$(gh api "repos/$repo/commits/$sha" --jq .commit.tree.sha)" = "$tree" ] || continue
  gh run view "$run" --json jobs --jq '[.jobs[] | select(.name | startswith("groups ("))] | length == 4 and all(.conclusion == "success")' | grep -qx true || continue
  echo "$sha"
  exit 0
done
exit 1
