# Observability and scalability plan (2026-10-23)

Week 1 is built on branch `observability` and checked locally and in a staging service (engineering log 46), except Error Reporting, whose API is off. The rest is not built. "Verify" marks what I could not confirm. §1 describes the server before week 1.

**Framing correction.** The server never calls an LLM: review runs inside Claude or ChatGPT between `draft_*` and `render_analysis`; LLM spend exists only in offline eval (`eval/review.py:96-112`). Server stages: fetch/GCS get → MEI + ScoreIndex → GNN lock wait → GNN inference (subprocess) → `draft.build` → verovio render/export → GCS publish, plus the `take()` counter. "Cost per request" means billable instance-seconds.

## 1. Current state

| Area | Today | Where |
|---|---|---|
| App logs | One JSON line per tool call (`event`, `platform`, sometimes `seconds`, `error`) to stdout. Cloud Logging parses it as `jsonPayload`. No `severity`, no trace field, no request id. | `server/app.py:104-105`, calls at 311-355, 409-446, 549-558, 593-612, 655-673 |
| Timing | Wall time per tool, rounded to 0.1 s, for `read_pdf`, `draft_analysis` and `draft_from_notes` only. `render_analysis` and `correct_bars` are untimed. | `app.py:397,445; 536,558; 657,673` |
| GNN timing | Import, model load and per-analysis seconds, printed as plain text to stderr | `engine/models/analysisgnn_runner.py:11,149-159` |
| Errors | User and server errors logged alike (`error=str(e)`), returned as HTTP 200 `isError`; uvicorn at `warning`. Error Reporting sees nothing. | `app.py:192,437,554,708` |
| Usage report | Daily counts via `gcloud logging read`; last 14 days ≈0–6 calls/day | `tools/usage_report.py` |
| Cost tracking | Eval LLM spend only. Nothing for Cloud Run. | `eval/review.py:109-112` |
| Request IDs, traces, histograms, per-stage timers, cold-start tracking, error rate by stage | None | — |
| Dashboards, alert policies, uptime checks, log-based metrics | None (`gcloud monitoring … list` returned empty, rc=0). Notification channels were not checked: that command group is not installed. | project `sheet-music-analysis` |
| Cloud Run (revision `00026-k9x`) | gen2, 2 vCPU, 4 GiB, concurrency 4, min 0, **max 1**, timeout 300 s, startup CPU boost on, request-based CPU, TCP startup probe | `server/deploy.sh:47-50`, `gcloud run services describe` |
| Known numbers | First draft after cold start ≈60 s (PyTorch import 54.6 s). Warm drafts 0.4–3 s. Container cold start ≈11 s. | `docs/engineering-log.md` §§ near lines 345-351, 381 |

**Built-in Cloud Run metrics are not enough:** every call is `POST /mcp` (no per-tool latency) and tool errors are HTTP 200 (a 5xx-based SLO reads ~100% regardless).

## 2. Instrumentation design

**Structured logs.** Replace `log()` with one JSON line per tool call. Also send root `logging`/uvicorn output through the same formatter.

- `severity`: INFO, WARNING for `user_error`/`limit`/`busy`, ERROR for `server_error`.
- `message`, `tool`, `outcome` ∈ {ok, user_error, limit, busy, server_error}, `platform`.
- `logging.googleapis.com/trace` = `projects/sheet-music-analysis/traces/<id>`, taken from `traceparent` or `X-Cloud-Trace-Context`. Read the headers via `ctx.headers`, as `platform()` already does (`app.py:91-96`). Use the same id as `request_id`. Verify that a header still arrives behind the Cloudflare proxy; otherwise generate a uuid.
- `timings_ms`: `{fetch, parse, gnn_wait, gnn, build, render, export, publish, counter, total}`.
- `cold` (first call in process), `worker_started`, `uptime_s`, input sizes (bytes, bars, notes).
- For `server_error`, add `stack_trace` (from `traceback.format_exc()`). Error Reporting picks up a `jsonPayload` stack trace automatically, or a `@type` ReportedErrorEvent with `message` (per its formatting doc).

**Per-stage timers.** `perf_counter` around each stage. `_Worker.run` (`engine/draft.py:108`) times lock wait separately; the runner replies `ok <seconds>` instead of printing to stderr, and its import/load line becomes JSON on stderr (also parsed by Cloud Run).

**Log-based metrics** (no new dependencies): `tool_calls` counter (labels `tool`, `outcome`, `platform`, `cold`); `tool_latency` distribution of `timings_ms.total`; one distribution per stage (`gnn_wait_ms`, `gnn_ms`, `render_ms`, `publish_ms`), since each extracts one field.

**OpenTelemetry → Cloud Trace** (optional, week 3): `opentelemetry-sdk` with the GCP exporter or OTLP (verify current); spans tool → fetch → gnn.wait → gnn → build → render → publish; 100% sampling.

**Metrics to have:** draft and render latency p50/p95/p99, warm vs cold; queue wait (`gnn_wait`); GNN, render and publish time; error rate by stage and outcome; billable instance-seconds per 1000 calls. LLM review time and token cost are not measurable server-side.

## 3. Dashboard, alerts, SLO

MQL is deprecated for new console work; use PromQL (`run.googleapis.com/x` → `run_googleapis_com:x`). Check each query in Metrics Explorer first.

| Row | Widgets |
|---|---|
| 1. Traffic | tool_calls/min by tool; outcome ratio (stacked); `container/instance_count` by state; `container/billable_instance_time` per day |
| 2. Latency | tool_latency p50/p95/p99 for draft tools, split by `cold`; the same for render; stage p95s (gnn_wait, gnn, render, publish) |
| 3. Platform | HTTP `request_latencies` p99; `container/startup_latencies`; CPU and memory utilizations (4 GiB holds the GNN, the JVM and the server) |
| 4. Drill-down | Logs panel (severity ≥ WARNING), links to Error Reporting and Trace |

Filters: `revision_name`, `tool`, `platform`.

Example queries (verify):
```
histogram_quantile(0.99, sum by (le) (rate(run_googleapis_com:request_latencies_bucket{monitored_resource="cloud_run_revision",service_name="sheet-music-analysis"}[5m])))
histogram_quantile(0.95, sum by (le, tool) (rate(logging_googleapis_com:user_tool_latency_bucket{monitored_resource="cloud_run_revision"}[10m])))
sum by (state) (run_googleapis_com:container_instance_count{service_name="sheet-music-analysis"})
```

**Alerts.** One email channel to the owner.

1. **Server errors:** `tool_calls{outcome="server_error"}` > 0 in 10 min.
2. **Down:** uptime check on `/health` every 15 min (less often would skew cold starts) fails from ≥2 regions.
3. **Cost guard:** billable instance time > 3,600 s/day; would have caught engineering-log §21 (15,450 s/day from held-open streams).

**SLO** (request-based ratio on the log metric; verify Service Monitoring accepts it): 99% of tool calls over 28 days not `server_error`; 95% of warm `draft_from_notes` under 3 s. At a few calls a day these are targets, not achievements.

## 4. Scalability

**What limits throughput now:**

- **max-instances 1**, a deliberate cost cap.
- **GNN serialized:** one subprocess behind a `threading.Lock` (`draft.py:84-119`); at concurrency 4, three callers queue. The subprocess avoids the GIL, but render (music21/verovio in threads) is CPU-bound on 2 vCPU. `read_pdf` refuses concurrent work (`app.py:414`). Memory is unmeasured.
- **`take()` counter** (`app.py:108-119`) rewrites one GCS object per call. GCS allows ~1 update/s per object, so it probably caps the service near 1 call/s, and loses updates across instances. Likely the first bottleneck found.

**Settings:**

- **Concurrency.** Sweep 1/2/4; keep what holds render p99 flat (probably 2), so the autoscaler adds instances instead of queueing.
- **min-instances.** 0 in production; always-on costs ≈ $150/month at the active rate (idle discount not verified). Test min 1 in staging only.
- **Startup.** Start the GNN worker at boot; HTTP `/health` startup probe ready only after it loads, so new instances get no traffic during the 54 s import. Keep CPU boost.
- **CPU allocation** request-based (no background work); **timeout** 300 s is fine; **GPU no**: inference is 0.4–3 s on CPU and the import dominates.

**Prerequisites (code changes):** `deploy.sh` takes a service name (staging service and bucket, `--no-allow-unauthenticated`); env override for `DAILY_LIMITS` (100 drafts/day would end a test); counter moved to a Firestore atomic increment or disabled in staging; eager GNN load plus the HTTP probe.

**Load test (k6 against the staging `*.run.app` with an ID token; never `mcp.sheetmusicanalysis.com`):**

- **Inputs.** 70% `draft_from_notes` (uncached, so real inference) with note lists made by `engine/notes.encode` from `tests/data/*.musicxml`, short to long; not `draft_analysis` by score_id, which returns cached output (`app.py:231`). 30% `render_analysis` on score_ids pre-seeded into the staging bucket.
- **Protocol.** First confirm locally that a stateless `tools/call` works without `initialize`.
- **Scenarios:** (a) step ramp at max 1 per concurrency value until p99 > 5 s or errors > 1%; (b) max 5, step to 3× single-instance capacity; (c) spike from idle; (d) 30 min soak; (e) 10 cold-start trials after scale-to-zero.
- **Measure:** max sustainable RPS at p99 under target (one and N instances); autoscaling reaction (load step → instance ready → p99 recovered); cold start split into container start and first draft; memory peak; cost per 1000 drafts = billable_instance_time × rate ÷ drafts.

**Honest result for "load tested and tuned autoscaling on Cloud Run":** RPS rises near-linearly from 1 to N instances, p99 meets the target at a stated load, reaction time is measured, and the chosen concurrency has a before/after table, all committed as k6 summaries plus Monitoring screenshots.

## 5. Cost and free tier

Current GCP pricing is from search snippets; the live pages were truncated, so re-check before relying on it.

| Item | Price | Expected use |
|---|---|---|
| Cloud Run, request-based, Tier 1 | $0.000024/vCPU-s, $0.0000025/GiB-s, $0.40/M requests. Free: 180k vCPU-s, 360k GiB-s, 2M requests/month. | One 2 vCPU/4 GiB instance ≈ $0.21/h. The free tier ≈ 25 instance-hours/month, enough for the load tests. |
| Logging | $0.50/GiB after 50 GiB/project/month; 30-day default retention | ≈1 KB per call: free |
| Monitoring metrics | $0.258/MiB after 150 MiB/month (whether log-based metrics are chargeable: verify) | Negligible |
| Trace | $0.20/M spans after 2.5M/month | Free |
| Alerting | $0.10 per condition per month (sources conflict) | ≈ $0.30/month |
| Error Reporting | No separate charge (logs only) | Free |

Cost per 1000 warm drafts, estimated: ≈ $0.02–0.12 (0.4–2 instance-s each); replace with the measured figure. Cloud Build minutes not checked.

## 6. Steps

| Week | Work | Done when |
|---|---|---|
| 1 | Structured logger, outcome classes, trace field, stage timers, runner timing | In staging, a draft entry shows severity, a working trace link and `timings_ms`; a forced DraftError appears in Error Reporting |
| 2 | Log-based metrics; dashboard JSON in repo (created with `gcloud monitoring dashboards create`); 3 alerts; uptime check | Each alert test-fired and the email arrived; the dashboard shows data from a scripted run |
| 3 | OTel → Cloud Trace (optional) | A trace waterfall for draft and render, linked from the log entry |
| 4 | Staging service, limits override, Firestore counter, eager GNN plus HTTP probe | Under 2 instances, counts are exact; a new instance takes traffic only after the model is loaded |
| 5 | k6 scenarios a–e | Results table, raw summaries and screenshots committed; cost per 1000 drafts computed from billable time |
| 6 | Apply the tuned production config (still capped); create the SLO; engineering-log entry | SLO object exists; 2 weeks of data collected |

## 7. CV claims

| After | Justified | Not justified |
|---|---|---|
| Weeks 1–2 | "Instrumented a PyTorch inference service on Cloud Run with structured logging, per-stage latency metrics, Cloud Monitoring dashboards and alerting" | "Production monitoring at scale"; any traffic or uptime figure |
| Week 3 | "Distributed tracing with OpenTelemetry and Cloud Trace" | "Across microservices" (it is one service) |
| Week 4 | "Removed a shared-state bottleneck and cut cold-start time from ~60 s to X s", with X measured | Anything before it is measured |
| Weeks 5–6 | "Load tested with k6 and tuned Cloud Run autoscaling: N instances sustained X drafts/s at p99 < Y s, at $Z per 1000 drafts" | "Handles high traffic in production"; "99.9% availability"; "reduced LLM costs" (the server has none); GPU or Kubernetes experience |
| Anything | — | LLM review latency or token cost from the server (they happen in the client) |

Sources: [Cloud Run pricing](https://cloud.google.com/run/pricing), [Observability pricing](https://cloud.google.com/products/observability/pricing), [MQL deprecation](https://docs.cloud.google.com/stackdriver/docs/deprecations/mql), [Error Reporting format](https://docs.cloud.google.com/error-reporting/docs/formatting-error-messages), [GCS quotas](https://docs.cloud.google.com/storage/quotas).
