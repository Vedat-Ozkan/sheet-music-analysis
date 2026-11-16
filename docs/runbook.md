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
gcloud run services update-traffic sheet-music-analysis --region us-central1 --project sheet-music-analysis --to-revisions=sheet-music-analysis-<previous-revision>=100
```

Put the revision's own suffix in place of `<previous-revision>` (it looks like `00064-tcs`); the command does nothing useful until you do.

Traffic stays pinned to that revision: the next deploy gets none until `gcloud run services update-traffic sheet-music-analysis --region us-central1 --project sheet-music-analysis --to-latest` is run.

## After a deploy

Startup lines and errors of the new revision (a clean start logs `server imported` and `STARTUP TCP probe succeeded`, with only Python and Cloud Trace deprecation warnings):

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.revision_name="sheet-music-analysis-<new-revision>"' --project sheet-music-analysis --limit 30 --order asc
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.revision_name="sheet-music-analysis-<new-revision>" AND severity>=ERROR' --project sheet-music-analysis --freshness 1d
```

`<new-revision>` is the suffix the deploy printed, or the first one in the `revisions list` output above.

Tool calls since the deploy: `.venv/bin/python -m tools.usage_report --days 1`. Cost: `.venv/bin/python -m tools.cost_report`.

## Only the proxy may call production

Production's own run.app address is public, and the limit of uploads per internet connection lives in the `proxy/` Worker, so a call sent straight to run.app would skip it. The server answers 403 to every request that does not carry the proxy's key in the `x-proxy-key` header, except `/health`. The Worker adds that header to everything it forwards. Staging has no key; it requires sign-in instead.

The key is held in three places that must agree: a version of the Secret Manager secret `proxy-key`, the Worker secret `PROXY_KEY`, and the version number the serving Cloud Run revision is pinned to.

`proxy/set-key.sh sheet-music-analysis` makes a new random key and sets all three, in that order: it adds a secret version, deploys the Worker from this checkout with the key, then points the service at that version (a new revision with the same image, not tagged `prod-*`). The key is never printed. If the Worker step fails, the script switches the new version off again and nothing has changed. `server/deploy.sh` pins every production deploy to the newest version that is switched on, and refuses to deploy production when there is none.

Turning it on for the first time, from a checkout of `main` that has the Worker change:

1. `proxy/set-key.sh sheet-music-analysis`. The server code then live does not check the key, so nothing is refused yet.
2. `server/deploy.sh sheet-music-analysis`. From this revision on the key is checked.
3. Check: `curl -s -o /dev/null -w '%{http_code}\n' -X POST https://mcp.sheetmusicanalysis.com/mcp` answers anything but 403, and the same request to the run.app address answers 403. Then make one real tool call from Claude or ChatGPT.

If every call starts failing with 403, the copies differ: run `proxy/set-key.sh sheet-music-analysis` again, which sets all three afresh. Rolling back helps only to a revision from before the key was first turned on.

Changing the key later is the same script. Calls are refused for the short time between its Worker step and its last step, because the serving revision still holds the old key.

## Release history

Each release has an entry in `docs/engineering-log.md` with its pull requests, commit, revision and rollback target (entries 145, 149, 152, 156 and 158), and a `prod-*` tag.
