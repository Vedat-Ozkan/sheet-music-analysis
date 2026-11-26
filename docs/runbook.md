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

- Production deploys only from a clean checkout of `origin/main` that CI has passed; the script refuses anything else. "Passed" means a successful full run of the `tests` workflow (all four test groups ran; a text-only run does not count) on any commit with the same files as the commit being deployed (`server/ci-passed.sh`), so the pull request's run counts when `main` holds exactly what it tested. If `main` differs from the last fully tested files only in text, start the workflow by hand (GitHub, Actions, tests, Run workflow) on `main`; a manual run is always the full suite. Staging may run a branch.
- Measure and quote any change that adds Cloud Run compute first. Never raise max instances or the daily limits without asking.
- A change to `Dockerfile.base`, `pyproject.toml` or `uv.lock` rebuilds the base image first (a few minutes longer).
- The careful reading of scans is offered only on the platforms the deploy names: `CAREFUL_READING=chatgpt`, `CAREFUL_READING=claude` or `CAREFUL_READING=chatgpt,claude` before `server/deploy.sh`. Every deploy sets it again, so a deploy without it switches the offer off everywhere.
  - A platform not named gets no offer on a scan's result. Claude, not named, is not shown `careful_reading` and `use_careful_reading` at all. ChatGPT always lists both tools and they always work, so OpenAI's reviewer can run them; on every platform the steps `careful_reading` returns begin with the usage warning and a wait for the user's yes, unless the user has already said yes to it in that chat.
  - For ChatGPT the order is: deploy without `chatgpt` in `CAREFUL_READING`, wait until the plugin's MCPs tab at platform.openai.com/plugins lists `careful_reading` and `use_careful_reading` as published (OpenAI scans the server itself, or press "Rescan" there), and only then add `chatgpt`.
- `CHATGPT_APP_NAME` is the app's name as ChatGPT lists it, used in the note that tells a user in an ordinary turn to pick the app with @; it defaults to Sheet Music Analysis, and `server/deploy.sh` sets sheet-music-staging on staging.

## Roll back

Find the previous revision with the `revisions list` command above (or the `rollback` revision in the release's log entry), then send all traffic to it:

```bash
gcloud run services update-traffic sheet-music-analysis --region us-central1 --project sheet-music-analysis --to-revisions=sheet-music-analysis-<previous-revision>=100
```

Put the revision's own suffix in place of `<previous-revision>` (it looks like `00064-tcs`); the command does nothing useful until you do.

Only a revision whose image is still in the registry can start. `server/deploy.sh` tags each production image `prod-<revision>` (as the git tag) and keeps that tag on the newest three only; tagged images are never cleaned up, untagged ones are, so the last three production revisions can always be rolled back to, and older ones cannot. Check with `gcloud artifacts docker images list us-central1-docker.pkg.dev/sheet-music-analysis/sheet-music-analysis/server --include-tags`.

Traffic stays pinned to that revision: the next deploy gets none until `gcloud run services update-traffic sheet-music-analysis --region us-central1 --project sheet-music-analysis --to-latest` is run.

## After a deploy

Startup lines and errors of the new revision (a clean start logs `server imported` and `STARTUP TCP probe succeeded`, with only Python and Cloud Trace deprecation warnings):

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.revision_name="sheet-music-analysis-<new-revision>"' --project sheet-music-analysis --limit 30 --order asc
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.revision_name="sheet-music-analysis-<new-revision>" AND severity>=ERROR' --project sheet-music-analysis --freshness 1d
```

`<new-revision>` is the suffix the deploy printed, or the first one in the `revisions list` output above.

Tool calls since the deploy: `.venv/bin/python -m tools.usage_report --days 1`. Cost: `.venv/bin/python -m tools.cost_report`.

A PDF read runs inside a request of its own (`POST /read-work`, sent by the server to its own run.app address, `OWN_ADDRESS`, which `server/deploy.sh` sets), so the instance that reads keeps its processor whichever instance the waiting calls reach (log 173). If that request is refused before it starts, the read runs on the instance that got the call, as it did before, and the log has a warning `read_pdf_work was not taken as a request of its own; reading here`. Staging refuses it while sign-in is required, so every staging read logs that warning unless staging is open:

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="sheet-music-analysis" AND jsonPayload.message:"not taken as a request of its own"' --project sheet-music-analysis --freshness 1d
```

## Only the proxy may call production

Production's own run.app address is public, and the limit of uploads per internet connection lives in the `proxy/` Worker, so a call sent straight to run.app would skip it. The server answers 403 to every request that does not carry the proxy's key in the `x-proxy-key` header, except `/health`. The Worker adds that header to everything it forwards. Staging has no key; it requires sign-in instead.

The key is held in three places that must agree: a version of the Secret Manager secret `proxy-key`, the Worker secret `PROXY_KEY`, and the version number the serving Cloud Run revision is pinned to.

`proxy/set-key.sh sheet-music-analysis` makes a new random key and sets all three without refusing any call. It adds a secret version, gives the service both the new version (`PROXY_KEY`) and the one before it (`PROXY_KEY_PREVIOUS`), deploys the Worker from this checkout with the new key, then removes the old one from the service. Each service step is a new revision with the same image, not tagged `prod-*`. The key is never printed. If the service or Worker step fails, the script puts the service back on the old key, switches the new version off, and nothing has changed. `server/deploy.sh` pins every production deploy to the newest version that is switched on, and refuses to deploy production when there is none.

Turning it on for the first time, from a checkout of `main` that has the Worker change:

1. `proxy/set-key.sh sheet-music-analysis`. The server code then live does not check the key, so nothing is refused yet.
2. `server/deploy.sh sheet-music-analysis`. From this revision on the key is checked.
3. Check: `curl -s -o /dev/null -w '%{http_code}\n' -X POST https://mcp.sheetmusicanalysis.com/mcp` answers anything but 403, and the same request to the run.app address answers 403. Then make one real tool call from Claude or ChatGPT.

If every call starts failing with 403, the copies differ: run `proxy/set-key.sh sheet-music-analysis` again, which sets all three afresh. Rolling back helps only to a revision from before the key was first turned on.

Changing the key later is the same script. It needs a serving revision whose server knows `PROXY_KEY_PREVIOUS` (log 186); on an older one, calls are refused from its Worker step until its last step.

## The proxy sends a refused request once more

Cloud Run itself refuses a request when no instance slot frees up in time: it waits in Cloud Run's queue (20 to 58 seconds in November 2026), then fails with 429 or 500 and "The request was aborted after waiting too long for an available instance" on a log line that has no instance id. Our container never sees it. Every answer our server gives carries the header `x-answered-by: sheet-music-analysis`, so the Worker treats a 429 or 500 without that header as Cloud Run's refusal and sends the same request once more, at once, with the same body; an answer from our server, whatever its status, is passed on and never sent again. A second refusal is passed on as it came.

- Order: the server revision with the header must be serving before the Worker with the retry is deployed, or the Worker would send our own 429s and 500s a second time. `proxy/set-key.sh` deploys the Worker too, so the same order applies to it.
- Each refusal the Worker saw is one line in the Worker's logs (Cloudflare dashboard, Workers, `sheet-music-analysis-mcp`, Logs), `{"event": "cloud_run_refused", "method", "path", "status", "waited_ms", "retry_status", "rescued"}`; nothing else is logged there. Workers Logs keeps them 3 days on the free plan, so count them within that time. Cloud Run's own refusal lines stay in Cloud Logging for 30 days: `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="sheet-music-analysis" AND "waiting too long for an available instance"' --project sheet-music-analysis --freshness 7d`
- `node --test proxy/worker.test.mjs` tests the Worker without the network.

## Instance limits

`server/deploy.sh` sets the revision's limits (`--max-instances=2 --concurrency=2 --min-instances=0`). The production service also carries a service-level annotation `run.googleapis.com/maxScale=3`, which `server/deploy.sh` neither sets nor removes; see it with `gcloud run services describe sheet-music-analysis --region us-central1 --project sheet-music-analysis --format='value(metadata.annotations)'`.

## Release history

Each release has an entry in `docs/engineering-log.md` with its pull requests, commit, revision and rollback target (entries 145, 149, 152, 156, 158, 203, 204, 207 and 217), and a `prod-*` tag.
