# Runbook

Google Cloud project `sheet-music-analysis`, region `us-central1`.

## What runs where

| | Cloud Run service | Address |
|---|---|---|
| Production | `sheet-music-analysis` | `https://mcp.sheetmusicanalysis.com/mcp` (the `proxy/` Worker in front of Cloud Run) |
| Staging | `sheet-music-analysis-staging` | its run.app address, sign-in required |

The revision serving traffic, and the last few:

```bash
gcloud run services describe sheet-music-analysis --region us-central1 --project sheet-music-analysis --format='value(status.latestReadyRevisionName,status.traffic)'
gcloud run revisions list --service sheet-music-analysis --region us-central1 --project sheet-music-analysis --limit 4
```

Each production deploy tags the commit it deployed `prod-<revision>` (for example `prod-00062-fzf`), so `git tag -l 'prod-*'` lists what has been live.

## Deploy

```bash
server/deploy.sh sheet-music-analysis            # production
server/deploy.sh sheet-music-analysis staging    # staging
```

- Production deploys only from a clean checkout of `origin/main` that CI has passed; the script refuses anything else. Staging may run a branch.
- Measure and quote any change that adds Cloud Run compute first. Never raise max instances or the daily limits without asking.
- A change to `Dockerfile.base`, `pyproject.toml` or `uv.lock` rebuilds the base image first (a few minutes longer).

## Roll back

Find the previous revision with the `revisions list` command above (or the `rollback` revision in the release's log entry), then send all traffic to it:

```bash
gcloud run services update-traffic sheet-music-analysis --region us-central1 --project sheet-music-analysis --to-revisions=sheet-music-analysis-00062-fzf=100
```

Traffic stays pinned to that revision: the next deploy gets none until `gcloud run services update-traffic sheet-music-analysis --region us-central1 --project sheet-music-analysis --to-latest` is run.

## After a deploy

Startup lines and errors of the new revision (a clean start logs `server imported` and `STARTUP TCP probe succeeded`, with only Python and Cloud Trace deprecation warnings):

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.revision_name="sheet-music-analysis-00063-qcs"' --project sheet-music-analysis --limit 30 --order asc
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.revision_name="sheet-music-analysis-00063-qcs" AND severity>=ERROR' --project sheet-music-analysis --freshness 1d
```

Tool calls since the deploy: `.venv/bin/python -m tools.usage_report --days 1`. Cost: `.venv/bin/python -m tools.cost_report`.

## Release history

Each release has an entry in `docs/engineering-log.md` with its pull requests, commit, revision and rollback target (entries 145, 149, 152, 156 and 158), and a `prod-*` tag.
