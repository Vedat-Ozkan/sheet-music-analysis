# OMR step 2: where PDF reading runs (2026-10-11)

Local only. Nothing deployed, committed or changed in the Cloud. The production Dockerfile and the skill are untouched. Tool: Audiveris 5.11.0 (same `.deb` as the spike).

## A. Server (Cloud Run gen2, 2 vCPU, 4 GiB, concurrency 4, max 1 instance)

### A1. Method: NOT Docker

Docker Desktop's CLI is on this Windows host, but the daemon was not running and `docker` is not wired into this WSL distro, so **no image was built and no container was run**. Instead: `taskset -c 0,1` (2 CPUs) and `JAVA_TOOL_OPTIONS=-Xmx1g` (a JVM in a 4 GiB container defaults its heap to a quarter of the RAM), with `/usr/bin/time -v` for peak RSS (`bench.py`, one run per file, no repeats). The unpacked `.deb` and its bundled JRE are the same files the image would hold. The `--memory=4g` limit itself was NOT tested.

| Input | Pages | Seconds (2 CPUs) | s/page | Peak RSS | Output | Spike on 16 cores |
|---|---|---|---|---|---|---|
| MuseScore Mozart K.545 PDF | 5 | 37.1 | 7.4 | 1,069 MB | 1 `.mxl` | 36 s |
| Mutopia Chopin Op.28 No.4 PDF | 1 | 13.9 | 13.9 (dense page + JVM start) | 1,327 MB | 1 `.mxl` | 12 s |
| Mozart Peters scan | 4 | 38.1 | 9.5 | 1,307 MB | 1 `.mxl` | 31.9 s |

Two CPUs cost 3-20% over 16 cores. Planning figure: **9.5 s a page** (about 38 s for a 4-page PDF, 14 s for one dense page).

### A2. Image size

NOT RUN (no Docker daemon). Estimate from the package: the `.deb` is 78,048,872 bytes (74.4 MiB), unpacked 188 MB with the JRE. Registry storage counts compressed layers, so the image grows by about **80 MB stored (about 190 MB when pulled and unpacked)**. The bundled JRE links libX11, libXext, libXi, libXrender, libXtst, libfreetype, libasound; `libcairo2`, already in `Dockerfile.base`, brings freetype, fontconfig, X11, Xext and Xrender, so the extra apt packages are about libXi, libXtst and libasound2 (a few MB; not verified in a slim image). The server image is about 2.9 GB uncompressed per the engineering log, so this is under 7%. Put as the last layer of the base, the layers below are shared with the old base.

### A3. Memory beside the server

Audiveris peaks at 1.07-1.33 GB (with a 1 GB heap). The server's own idle RSS was NOT measured; `deploy.sh` says four drafts at about 0.8 GB each fit beside the server, which implies the server is well under 0.8 GB. Taking 0.8 GB as an upper bound: 0.8 + 1.33 = 2.1 GB leaves 1.9 GB, which is **two drafts, not four**. So a PDF read does not fit beside 4 concurrent drafts (3.2 GB). It also uses about 2.3 cores, so drafts and renders running at the same time will slow down. Needed in the server: one PDF read at a time (a semaphore), and a "busy, try again in a minute" reply, not a queue held open (open requests are billed, log 21). Not tested under a real 4 GiB limit.

### A4. Cost

Source: https://cloud.google.com/run/pricing, "Services (Requests-based billing)", fetched 2026-10-11, us-central1 (Tier 1):
- CPU $0.000024 per vCPU-second; memory $0.0000025 per GiB-second; requests $0.40 per million.
- Free tier each month: 180,000 vCPU-seconds, 360,000 GiB-seconds, 2 million requests.

One billed instance-second at 2 vCPU and 4 GiB = 2 x 0.000024 + 4 x 0.0000025 = **$0.000058**. Free tier: 180,000 / 2 = 90,000 and 360,000 / 4 = 90,000, so **90,000 instance-seconds a month** (3,000 a day), CPU and memory running out together. Requests are far below 2 million. Billing is only while a request is open; with concurrency 4 overlapping requests share the time, so counting them one after another is an upper bound.

| | Seconds | Cost beyond free tier |
|---|---|---|
| 1 page | 9.5 | 9.5 x 0.000058 = $0.00055 |
| 4-page PDF | 38 | 38 x 0.000058 = $0.0022 |
| 1 dense page | 14 | $0.0008 |

Artifact Registry (https://cloud.google.com/artifact-registry/pricing): $0.000136986 per GiB-hour, which is about $0.10 per GiB-month; first 0.5 GiB free. Today 1.3 GB: (1.3 - 0.5) x 0.10 = $0.08 a month. With +0.09 GB: (1.39 - 0.5) x 0.10 = $0.089, so **+$0.009 a month**. Negligible.

### A5. Proposed cap

Worst case for existing usage, at today's caps, every day of a 30-day month, using the engineering log's timings (draft 5.6 s incl. cold model load, render 15.2 s for the densest page measured, 24 cold starts a day at 11 s):
- 100 drafts x 5.6 = 560 s; 200 renders x 15.2 = 3,040 s; 24 x 11 = 264 s. Total 3,864 s a day, 115,920 a month. (Typical renders are about 10 s, so this is conservative.)

Budget: $5.00 - $0.09 (registry) - $0.50 reserved for Cloud Build, logging, storage, egress (my assumption, not measured) = $4.41 for Cloud Run. $4.41 / 0.000058 = 76,034 billable s + 90,000 free = 166,034 s a month = 5,534 s a day. Left for PDFs: 5,534 - 3,864 = **1,670 s a day**.

Proposal: a new key **`"pdf_page": 150`** in `DAILY_LIMITS`, where a read of an n-page PDF counts n (the counter now adds 1 per call, so this needs a small change), and a PDF over 12 pages is refused. That is 37 four-page PDFs a day.
- 150 pages x 9.5 s = 1,425 s, +15% for retries, export and upload = 1,639 s a day (under 1,670).
- Whole month at every cap: (3,864 + 1,639) x 30 = 165,090 s; minus 90,000 free = 75,090 billable; x 0.000058 = **$4.36**; + $0.09 registry = **$4.45**; $0.55 of the $5 left for the reserve.
- If the owner would rather count calls: `"pdf": 35` with a 4-page limit per read (35 x 38 s = 1,330 s). Page counting is fairer to one-page uploads.

Cold starts get a bit longer with an 80 MB larger image (not measured).

## B. Claude sandbox

### B1. Probe

`spike/omr/step2/sandbox_probe.py`. Run: `python3 sandbox_probe.py small.pdf`. Prints the machine (Python, OS, CPUs visible and usable, cgroup CPU and memory limits, RAM, free disk, `java`, `dpkg-deb`, `sudo`), whether github.com, pypi.org, objects.githubusercontent.com, mcp.sheetmusicanalysis.com and sheetmusicanalysis.com answer (HEAD, 10 s timeout), the `.deb` download (picks ubuntu22.04 or 24.04 by the sandbox OS) and time, the unpack without sudo and time (`dpkg-deb -x`; otherwise Python's `ar` + `tarfile`, installing `zstandard` from PyPI because the deb uses zstd), the PDF conversion seconds and peak RAM (`/usr/bin/time -v`, else `getrusage` children), and the one-step-fail-then-re-export-from-`.omr` fallback. Last line is `SUMMARY {json}`; a failing step is recorded in `"error"` and the summary is still printed.

Tested locally (WSL, Ubuntu 22.04, Python 3.10) end to end on the 1-page Chopin PDF: download 74.4 MB in 3.7 s, unpack 0.4 s (188 MB), run 12.5 s, peak 1,033 MB, `.mxl` written. The no-`dpkg-deb` path was also run (unpack 0.9 s, run 12.3 s, 1,062 MB). Local times are not sandbox times. **Not run in a real claude.ai sandbox** (needs the owner or the browser). Known risks the run will answer: network allowlist, missing X/freetype/asound libraries, a read-only HOME (it sets HOME to a temp dir), RAM or time limits.

### B2. Prompt to paste (attach `sandbox_probe.py` and a small PDF, e.g. `spike/omr/r2/pdf/chopin-28-4-mutopia.pdf`, 1 page, 184 KB)

```
I attached sandbox_probe.py and a PDF. Find both in your sandbox (usually /mnt/user-data/uploads/), then run exactly this with your code execution tool, without editing the script and without trying to fix any error:

python3 sandbox_probe.py <path to the PDF>

Then reply with the complete last line of the output, the one that starts with SUMMARY, copied exactly inside a code block. If the command failed or timed out, paste whatever output you got instead. Add nothing else.
```

### B3. Alternative: the sandbox sends the PDF (or page images) to our server

- Can the sandbox reach mcp.sheetmusicanalysis.com? **Unknown.** `docs/research-2026-10-01.md` line 74 says only: network on by default for Free, Pro, Max; "allowed domains include PyPI and GitHub"; Team and Enterprise default to off. Our domain is not listed anywhere in the docs, and nothing in the repo shows the sandbox calling our server directly today (the skill sends data through the connector's tool calls). The probe's `reach` block answers it. (From this machine the domain answers; that says nothing about the sandbox.) ChatGPT's sandbox has outbound network blocked (research line 89), so this route cannot exist there.
- What it would need: (1) our domain allowed by the sandbox, which the user cannot be asked to set up (rule: no workaround flows), so it only works if it is already reachable; (2) a new `POST` endpoint on the server (none today; only `GET /files`) taking the file, behind `DAILY_LIMITS`, returning MusicXML or a score id; (3) the skill steps to POST; (4) the same Audiveris in the image and the same memory limits as A.
- My view: it removes nothing from the server side. The OMR still runs on Cloud Run, so the image growth, memory and cost in section A stay. It only replaces "the host hands the server a file URL" with "the sandbox uploads it". Send the PDF itself, not page images: smaller (184 KB vs several MB of PNG), and Audiveris reads PDFs directly; images only make sense for homr. For Claude the better route, if the probe passes, is to run Audiveris in the sandbox: no Cloud cost, no cap, no memory contention, at the price of an 74 MB download and about 12 s a page per chat. The server-side install is still needed for ChatGPT, whose server receives the file through `download_url` and whose sandbox has no network. Decision order after the probe: (a) sandbox runs Audiveris within its limits, use it for Claude; (b) sandbox can reach our domain but not run Java, POST the PDF; (c) neither, server-side only via a host that gives the server the file (ChatGPT), and say plainly that Claude cannot read PDFs yet.

## Not run

Docker image build and container runs (no daemon); `--memory=4g` enforcement; server idle RSS; cold start with the larger image; the probe inside a real claude.ai sandbox; `Dockerfile` edits (forbidden here); any measurement of Cloud Run itself (times above are 2 pinned local CPUs, Cloud Run's may differ); runs on more than one file each (one run per input, no repeats).

## Files

`bench.py` (the 2-CPU benchmark), `sandbox_probe.py`, `RESULTS.md`, `.gitignore`.

## Real claude.ai sandbox run (2026-10-11)

Run in a new claude.ai chat (Sonnet 5.5) with `sandbox_probe.py` and `chopin-28-4-mutopia.pdf` attached. SUMMARY line, as returned:

```
SUMMARY {"step": "done", "machine": {"python": "3.13.16", "arch": "x86_64", "os": "Ubuntu 24.04.5 LTS", "os_version_id": "24.04", "cpus_visible": 2, "cpus_usable": 2, "cgroup_cpu_max": null, "cgroup_mem_max": null, "ram_total_mb": 8029, "ram_available_mb": 7552, "disk_free_mb": 30719, "workdir": "/tmp", "java": "/usr/bin/java", "dpkg_deb": "/usr/bin/dpkg-deb", "gnu_time": false, "sudo": "/usr/bin/sudo"}, "reach": {"github.com": {"ok": true, "status": 400, "s": 0.27}, "objects.githubusercontent.com": {"ok": true, "status": 404, "s": 0.34}, "pypi.org": {"ok": true, "status": 200, "s": 0.03}, "mcp.sheetmusicanalysis.com": {"ok": false, "error": "URLError: <urlopen error Tunnel connection failed: 403 Forbidden>"}, "sheetmusicanalysis.com": {"ok": false, "error": "URLError: <urlopen error Tunnel connection failed: 403 Forbidden>"}}, "download": {"url": "https://github.com/Audiveris/audiveris/releases/download/5.11.0/Audiveris-5.11.0-ubuntu24.04-x86_64.deb", "mb": 74.1, "s": 1.9}, "unpack": {"method": "dpkg-deb", "s": 0.7, "mb": 188}, "run": {"pdf": "chopin-28-4-mutopia.pdf", "returncode": 0, "s": 23.9, "peak_ram_mb": 784, "peak_from": "getrusage(children), covers all children so far", "mxl": ["chopin-28-4-mutopia.mxl"]}}
```

Findings: Audiveris installs and runs in the sandbox (download 1.9 s, unpack 0.7 s, 1-page PDF 23.9 s, 784 MB peak; 2 CPUs, 8 GB RAM). Our domains are blocked by the sandbox proxy (403), so the "send pages to our server" route is not possible. Claude runs OMR in the sandbox at no Cloud cost; ChatGPT runs it on the server. Accounts with sandbox network off (Team/Enterprise default) cannot download Audiveris and must be told so plainly.
