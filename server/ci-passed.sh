#!/usr/bin/env bash
set -euo pipefail
commit=${1:-HEAD}
sha=$(git rev-parse "$commit")
tree=$(git rev-parse "$commit^{tree}")
ask() {
  gh "$@" || { echo "cannot ask GitHub: gh $*" >&2; exit 2; }
}
repo=$(ask repo view --json nameWithOwner --jq .nameWithOwner)
pulls=$(ask api "repos/$repo/commits/$sha/pulls" --jq '.[].head.sha')
for candidate in $sha $pulls; do
  runs=$(ask run list --workflow tests --commit "$candidate" --status success --json databaseId,headSha --jq '.[] | "\(.databaseId) \(.headSha)"')
  while read -r run head; do
    [ -n "$run" ] || continue
    [ "$(ask api "repos/$repo/commits/$head" --jq .commit.tree.sha)" = "$tree" ] || continue
    [ "$(ask run view "$run" --json jobs --jq '[.jobs[] | select(.name | startswith("groups ("))] | length == 4 and all(.conclusion == "success")')" = true ] || continue
    echo "$head"
    exit 0
  done <<< "$runs"
done
exit 1
