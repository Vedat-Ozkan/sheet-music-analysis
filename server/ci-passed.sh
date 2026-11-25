#!/usr/bin/env bash
set -euo pipefail
commit=${1:-HEAD}
tree=$(git rev-parse "$commit^{tree}")
repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
for sha in $(gh run list --workflow tests --status success --limit 100 --json headSha --jq '.[].headSha'); do
  if [ "$(gh api "repos/$repo/commits/$sha" --jq .commit.tree.sha)" = "$tree" ]; then
    echo "$sha"
    exit 0
  fi
done
exit 1
