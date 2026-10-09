# Load Test Playbook (Step 5)

How Team 2 ran the 36 official load runs, in enough detail to repeat them. The runs were 4 candidate models ×
3 load configurations × 3 runs, on 7–8 Oct 2026. Everything here is Windows PowerShell 5.1 and runs from the
repository root unless a step says otherwise.

Two laptops take part:

- **SUT laptop, operated by P1.** Runs the service, MySQL and Ollama.
- **Load-generator laptop, operated by P2.** Runs JMeter. **Never run JMeter on the SUT laptop.**

This playbook covers both sides. The accuracy and stress tests operate the SUT the same way (§2, §4.1, §4.3, §5
steps 1 and 3, §7–§9) and have their own playbooks:
[`tests/accuracy/ACCURACY_PLAYBOOK.md`](../accuracy/ACCURACY_PLAYBOOK.md) and
[`tests/stress/stress-test-playbook.md`](../stress/stress-test-playbook.md).

---

## 1. What is measured

| Configuration | Traffic, open-loop with random (Poisson) arrivals | Requests sent per run (planned) | Requirements it tests |
|---|---|---|---|
| `tkt-normal` | `POST /tickets` at 1,312/h | about 109 tickets | TR-1 |
| `tkt-peak` | `POST /tickets` at 3,936/h | about 328 tickets | RR-1, TR-2 |
| `mix-peak` | `POST /tickets` at 3,936/h **and** `GET /search` at 7,872/h | about 328 tickets + 656 searches | RR-2 |

Where the rates come from:
- **Tickets:** 1,312/h is the average hour and 3,936/h the peak hour (3 × average), from the Step 3 workload
  model and Step 4 (TR-1, TR-2).
- **Searches:** 7,872/h is 2 searches per ticket, the middle of the 1–3 per ticket in Step 3.

Each run sends traffic for 5 minutes (300 s) at one steady rate. Every request then gets up to 295 s to answer, so
JMeter runs for about 10 minutes.

**Models, in run order.** The model changes only three times. Pinned tags and digests are in
`tests/environment/model_pins.json`.

| Order | Model | Runs |
|---|---|---|
| 1–9 | `gemma4:e4b` | `tkt-normal` run 1–3, `tkt-peak` run 1–3, `mix-peak` run 1–3 |
| 10–18 | `llama3.2:1b` | same order |
| 19–27 | `phi3:3.8b` | same order |
| 28–36 | `mistral:7b` | same order |

**Run ID** = `<model>_<test-type>_<configuration>_run<n>`, with the `:` in the model tag written as `-`. Load runs
use test type `load`, for example `phi3-3.8b_load_tkt-peak_run2`. The other playbooks use `accuracy` and `stress`,
for example `mistral-7b_accuracy_golden175_run1` and `gemma4-e4b_stress_ramp_run1`.

---

## 2. The system under test

### 2.1 Layout

```
 Load generator / accuracy / stress laptop            OFFICIAL SUT LAPTOP (P1)
 ┌───────────────────────┐   HTTP over LAN   ┌──────────────────────────────────────────────┐
 │ JMeter or test script │ ───────────────▶  │ :8000  triage service (FastAPI, synchronous) │
 └───────────────────────┘                   │          │ 1 blocking call per ticket        │
                                             │          ▼                                   │
                                             │ Ollama 0.34.4, CPU only (127.0.0.1:11434)    │
                                             │ MySQL 8.0.46 (127.0.0.1:3306)                │
                                             └──────────────────────────────────────────────┘
```

Only port 8000 is reachable from other laptops. MySQL and Ollama are bound to localhost.

### 2.2 Settings frozen for every official run

Only the model changes between official comparisons. Everything below stays identical.

| Setting | Value | Why |
| --- | --- | --- |
| Ollama image | `ollama/ollama:0.34.4` (digest in `tests/environment/p1_sut_environment.md`) | same inference engine for every run |
| MySQL image | `mysql:8.0.46` | same storage engine |
| Models | the 4 Step 4 candidates, full digests in `tests/environment/model_pins.json` | a changed digest = a different model |
| GPU | none passed to the container; `size_vram = 0` checked before and after every run | brief forbids GPU inference |
| `OLLAMA_NUM_PARALLEL` | 1 | baseline processes one ticket at a time; others wait in Ollama's queue |
| `OLLAMA_MAX_QUEUE` | 512 (Ollama default) | never reached through this service: its 40-thread pool lets at most 40 tickets into Ollama at once (§12.3) |
| `OLLAMA_MAX_LOADED_MODELS` | 1 | only the model under test uses RAM |
| `OLLAMA_KEEP_ALIVE` | -1 | a quiet period mid-test must not unload the model and turn the next ticket into a cold start |
| Context window | Ollama default 4096 tokens (longest ticket + prompt ≈ 850 tokens) | no truncation |
| Prompt | `server/prompt.py`, `PROMPT_VERSION = v1`: 7 categories + the protocol §1 definitions, no §2–3 edge-case rules | same instructions for every model |
| Decoding | `temperature 0`, `seed 42`, JSON-schema output restricted to the 7 exact category names | deterministic; the answer is always one valid category |
| `think` | not sent (`OLLAMA_THINK=default`): each model as shipped, so gemma4:e4b reasons before answering and the other three cannot | untuned baseline; matches how the Step 4 predictions were timed; see §12.1 item 4 |
| Service → Ollama timeout | 600 s, counted from when a service thread calls Ollama | failures come from the system limits under test, not an arbitrary short timeout |
| Warm-up | 1 fixed invented ticket (`$WarmupNarrative` in `scripts/p1/_common.ps1`), before each run, not measured | every run starts with the model already in RAM |
| Service | synchronous: `POST /tickets` returns only after classification; no caching, queuing or batching | Assignment 1 baseline |

### 2.3 Equipment and software

| | SUT laptop (P1) | Load-generator laptop (P2) |
|---|---|---|
| Machine | Lenovo Legion Pro 5, i9-14900HX, 32 GB, CPU-only inference | Acer Swift SFG14-73, Core Ultra 7 155H, 15.7 GB |
| Software | Docker Desktop: `server`, `mysql`, `ollama/ollama:0.34.4`, started with `docker compose up -d` | Apache JMeter 5.6.3, Java 17, Python 3 (for `prepare_data.py`) |
| Details recorded in | `tests/environment/p1_sut_environment.md` | `tests/environment/loadgen_environment.md` |

### 2.4 Network

Both laptops join the same phone hotspot. All 36 official runs sent their traffic over the hotspot to the SUT at
`172.20.10.2`. One run, `gemma4-e4b_load_tkt-normal_run1`, was prepared just before the SUT joined the hotspot; its
register note records this. Attempts over university Wi-Fi, and with the two laptops on separate networks, failed
to connect, which is why the hotspot is used.

---

## 3. One-time preparation

### 3.1 SUT laptop (P1, already done)

```powershell
docker compose up -d --build                                                  # mysql + ollama + server
powershell -ExecutionPolicy Bypass -File scripts\p1\pin_models.ps1 -Pull      # pull 4 models, write model_pins.json
powershell -ExecutionPolicy Bypass -File scripts\p1\record_environment.ps1    # Slide 7 evidence
```

Firewall (admin PowerShell, once): lets laptops on the same subnet reach port 8000 on any network type.

```powershell
New-NetFirewallRule -DisplayName 'ICT3113 SUT API (TCP 8000)' -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Any -RemoteAddress LocalSubnet
```

### 3.2 Ticket file (P2)

JMeter reads one JSON request body per line from `load-generator/data/tickets.jsonl`. Build it from the team's
dataset extract, rows 2000–2999 of the course CSV. The extract is not stored in this repository.

```powershell
cd load-generator
python prepare_data.py --csv <path>\ict3113_tickets_2000_2999.csv --output data\tickets.jsonl
```

All ticket groups share one cursor on the file, in file order, and every run starts again from the first line.
Search terms come from `load-generator/data/search_terms.csv` (17 terms, committed). Both files are read on a loop.

### 3.3 Dry run: check that ticket-only runs send no searches (P2)

This targets P2's own laptop on port 1, where nothing listens, so nothing reaches the SUT.

```powershell
jmeter -n -t load_test.jmx "-Jhost=127.0.0.1" "-Jport=1" "-Jrun_id=dryrun" "-Jsearch_k=0" "-Jtickets_per_hour_tr1=3936" "-Joffpeak_duration_sec=10" "-Jpeak_duration_sec=10" "-Jresponse_timeout_ms=1000" "-Jjtl=dryrun.jtl"
(Select-String dryrun.jtl -Pattern "GET /search").Count    # must be 0
(Select-String dryrun.jtl -Pattern "POST /tickets").Count  # about 30, all errors (expected)
Remove-Item dryrun.jtl
```

---

## 4. Start of each test session

### 4.1 P1, on the SUT laptop

1. Plug in AC power. Set Windows power mode to **Best performance** and the Legion thermal mode to **Performance**
   (Fn+Q); write the thermal mode in `-Notes` when preparing runs. Set "When plugged in, put my device to sleep
   after" to **Never** (`powercfg /change standby-timeout-ac 0`).
2. Quit the native Windows Ollama app (tray icon → Quit) and close heavy applications (games, VMs, big downloads,
   browsers playing video).
3. Join the hotspot, then run:

   ```powershell
   git pull --no-edit
   docker compose up -d
   powershell -ExecutionPolicy Bypass -File scripts\p1\preflight.ps1      # must end with PREFLIGHT OK
   ipconfig                                                              # send the Wi-Fi IPv4 to P2
   ```

`preflight.ps1` also checks that the Docker VM clock matches Windows. After the laptop sleeps, WSL2's clock can drift
and server log timestamps no longer line up with JMeter's. Restart Docker Desktop if it warns.

### 4.2 P2, on the load-generator laptop

1. Plug in AC power. Set sleep and screen-off to **Never** and turn off Wi-Fi power saving.
2. Join the same hotspot and sync the clock (Settings → Time & language → Sync now). This keeps JMeter timestamps
   comparable with the server log.
3. Run:

   ```powershell
   git pull
   Invoke-RestMethod http://<SUT-IP>:8000/health                         # status ok, shows the model
   Test-NetConnection <SUT-IP> -Port 8000                                # TcpTestSucceeded : True
   powershell -ExecutionPolicy Bypass -File scripts\record_loadgen_environment.ps1 -SutHost <SUT-IP>
   cd load-generator
   ```

4. Send the generated `loadgen_environment.md` to P1 for `tests/environment/`.

`ping` is not a valid connectivity check: the SUT's firewall does not answer it even when port 8000 is reachable.
Use `Test-NetConnection` on port 8000.

### 4.3 P1, when the model changes (before runs 1, 10, 19 and 28)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\p1\switch_model.ps1 -Model <tag>
```

To do it by hand instead, see §9.

---

## 5. Every run

### Step 1: P1 prepares the SUT

```powershell
powershell -ExecutionPolicy Bypass -File scripts\p1\prepare_run.ps1 -TestType load -Config <configuration> -Run <n> -Tester P2 -Notes "<rates; 5 min send, 295 s timeout; network; thermal mode>"
```

`prepare_run.ps1` does the following, then prints `READY <run-id>` and the SUT URL:
- checks the model digest, a clean git tree, AC power and power mode;
- sends one warm-up ticket and confirms the model is loaded on CPU;
- restarts the service with an empty request log and empties the database.

It refuses an ID that already has a folder, so evidence is never overwritten. P1 tells P2 "READY" and the run ID.

### Step 2: P2 runs JMeter once, in `load-generator`

Send traffic only between READY and `finish_run.ps1`, and only for your run: anything else lands in that run's
evidence. The common part of every command:

```
jmeter -n -t load_test.jmx "-Jhost=<SUT-IP>" "-Jport=8000" "-Jrun_id=<run-id>" "-Jsample_variables=req_id" "-Joffpeak_duration_sec=90" "-Jpeak_duration_sec=120" "-Jresponse_timeout_ms=295000" <rate flags>
```

| Configuration | `<rate flags>` |
|---|---|
| `tkt-normal` | `"-Jtickets_per_hour_tr2=1312" "-Jsearch_k=0"` |
| `tkt-peak` | `"-Jtickets_per_hour_tr1=3936" "-Jsearch_k=0"` |
| `mix-peak` | `"-Jtickets_per_hour_tr1=3936"` (default `search_k=2` gives 7,872 searches/h) |

What the flags do:

- **Phases.** `load_test.jmx` has three phases: off-peak 90 s at `tickets_per_hour_tr1` (default 1,312), peak
  120 s at `tickets_per_hour_tr2` (default 3,936), off-peak 90 s at `tickets_per_hour_tr1`. Each configuration sets
  the one rate it overrides so that **all three phases run at the same rate**. `search_k` × ticket rate gives the
  search rate, and `search_k=0` sends no searches.
- **`-Jrun_id`** is sent as the `X-Run-Id` header and stamped on every server log line.
- **`-Jsample_variables=req_id`** saves the server's `X-Request-ID` in the `.jtl`, so client and server records
  pair one-to-one.
- **`-Jresponse_timeout_ms=295000`** counts a ticket not answered within 295 s as an error. Each schedule ends with
  a drain pause of 300 s (5 s connect + 295 s response timeout), so a run lasts about 10 minutes.

JMeter writes `results\<run-id>-<yyyyMMdd-HHmmss>.jtl`, a CSV with a `req_id` column. Wait for `... end of run`,
and start JMeter only once per run. Then tell P1 "done" and send the `.jtl`.

**Optional time-saver, llama and phi3 only.** Once at least 5 minutes have passed and the latest `summary` line ends
with `Active: 0`, stop JMeter cleanly from a second window:

```powershell
& "$HOME\tools\apache-jmeter-5.6.3\bin\shutdown.cmd"
```

Let gemma4 and mistral runs finish on their own.

### Step 3: P1 finishes the run, 2 minutes after `... end of run`

```powershell
Start-Sleep 120; powershell -ExecutionPolicy Bypass -File scripts\p1\finish_run.ps1 -RunId <run-id>
```

The 2-minute wait matters in overloaded runs. Requests the server is still finishing only reach its log when they
complete, and `finish_run.ps1` stops the service.

`finish_run.ps1` does the following:
- snapshots Ollama and stops the service;
- archives `server_access.log`, exports the `tickets` and `request_metrics` tables and Ollama's log for the run
  window;
- restarts the service and marks the run DONE in `runs/run_register.csv`.

### Step 4: P1 checks and saves

1. Put the `.jtl` in `runs\<run-id>\`, checking that the folder name matches the run ID.
2. Run:

   ```powershell
   python analysis\reconcile.py runs\<run-id>
   git add runs tests/environment
   git commit -m "Load run <run-id>"
   git restore analysis/output
   git pull --no-edit
   git push
   ```

`reconcile.py` pairs every JMeter sample with its server log line (by `req_id`, else by time) and checks both
against the database export.

| Result | What it means |
|---|---|
| `PASS` | Every record pairs |
| `WARN` | Explained differences, e.g. client timeouts the service completed later |
| `FAIL` on an **overloaded** run | Known pattern: stored tickets missing from the request log, server HTTP 500s with no client record. Record the explanation as a note in `runs/run_register.csv` |
| `FAIL` for any other reason | Stop and investigate before the next run |

---

## 6. When a run fails

A run is invalid if traffic did not reach the SUT, the network dropped, or a laptop slept.

1. **Keep its evidence.** Rename the run folder with a suffix, e.g. `-dropped` or `-noconnect`, and commit it.
   Change its row in `runs/run_register.csv` to the new ID.
2. Add it to `analysis/excluded_runs.csv` with the reason.
3. Redo the run under the **same** run ID.

Examples from the official runs. Both folders were later removed from the working tree, but their files remain in
git history at the commit shown.

| Excluded run | Reason | Files in git |
|---|---|---|
| `gemma4-e4b_load_tkt-normal_run2-dropped` | Hotspot disconnected mid-run | `ad2a1af` |
| `mistral-7b_load_mix-peak_run2-noconnect` | The SUT slept while READY: AC sleep timer was 1 h, and all 981 requests timed out connecting | `5ead1f5` |

Also check every new `.jtl` for gaps in arrivals followed by bursts. These were seen on 7 Oct before P2's
sleep and power-saving settings were changed.

---

## 7. Evidence kept per run (`runs/<run-id>/`)

| File | Written by | Content |
|---|---|---|
| `<run-id>-<time>.jtl` | tester (JMeter) | Every client sample: start time, elapsed time, status, `req_id`. **Required**; for accuracy runs, the accuracy CSV instead |
| `run_info.json` | `prepare_run.ps1` | Model and digest, commit, prompt, `think`, Ollama version, power state, SUT URL, READY time |
| `warmup_access.log` | `prepare_run.ps1` | The warm-up request(s) and P1's checks before READY; not part of the run |
| `ollama_ps_before.*`, `ollama_ps_after.*` | `prepare_run.ps1` / `finish_run.ps1` | Model resident with `size_vram = 0`, proving CPU-only inference |
| `server_access.log` | `finish_run.ps1` | One line per request the service handled during the run. The first `GET /health` with `run=-` is P1's readiness check |
| `tickets.tsv`, `request_metrics.tsv` | `finish_run.ps1` | Database rows written during the run |
| `ollama.log` | `finish_run.ps1` | Ollama's own log for the run window, one `[GIN]` line per inference |

`runs/run_register.csv` has one row per run (READY → DONE), holds the notes explaining each reconcile result, and is
the index for the slides.

---

## 8. Service interface, for anyone sending traffic

- Target `http://<SUT-IP>:8000` (printed in the READY banner). Check `GET /health` first: it returns the model
  under test, e.g. `{"status":"ok","model":"phi3:3.8b","prompt_version":"v1","think":"false"}`.
- Optional header `X-Run-Id: <run-id>`: it is written into every server log line (`run=`) for that request.
  `load_test.jmx` sends it from `-Jrun_id`.
- `POST /tickets` → `200 {"id","category","narrative","classification_latency_ms"}`. `502` = classification failed;
  the log's `error=` field says why: `OllamaError` (Ollama returned an error), `ReadTimeout` (no answer within 600 s)
  or `ClassificationError` (no valid category in the answer). Count 502s as errors.
- Server log line format (UTC):
  `2026-09-26T13:17:09.317Z POST /tickets 200 3757.89ms client=… req_id=… start_ms=<epoch ms> run=… model=… ticket_id=… category="…" ollama_total_ms=… ollama_load_ms=… prompt_tokens=… prompt_eval_ms=… eval_tokens=… eval_ms=…`
  - `start_ms` is directly comparable with JMeter's `timeStamp` (epoch ms), within the two laptops' clock offset.
  - Every response carries an `X-Request-ID` header equal to `req_id`.
  - Time spent waiting in Ollama's queue ≈ `ollama_total_ms − ollama_load_ms − prompt_eval_ms − eval_ms`.
  - Time spent in the service outside the model call (under load, mostly waiting for a free thread) ≈ the line's
    latency − `classification_latency_ms` of the same ticket (`tickets.tsv`, joined on `ticket_id`).
- `client=` shows the Docker gateway, not the load generator's IP (Docker Desktop port forwarding). Runs are told
  apart by time window and `run=`.

---

## 9. Manual fallback commands (P1)

```powershell
docker compose ps                                          # all three services running / healthy
Invoke-RestMethod http://localhost:8000/health             # model the service is using
Invoke-RestMethod http://localhost:11434/api/ps            # loaded model; size_vram must be 0
docker compose exec ollama ollama ps                       # PROCESSOR column must say 100% CPU
docker compose exec -T -e MYSQL_PWD=triage mysql mysql -utriage triage -e "TRUNCATE TABLE request_metrics; TRUNCATE TABLE tickets;"
docker compose logs --tail 50 server                       # service errors
docker compose logs --tail 50 ollama                       # Ollama errors
docker compose down                                        # stop everything (volumes/models are kept)
```

Switching models by hand: set `OLLAMA_MODEL=<tag>` in `.env`, then `docker compose up -d --no-deps --force-recreate server`
and confirm `/health`. A leftover `$env:OLLAMA_MODEL` in your shell overrides `.env`. `switch_model.ps1` handles both.

---

## 10. Analysis

```powershell
python analysis\requirements_matrix.py                  # requirement verdicts; drops the first 120 s of each run
python analysis\requirements_matrix.py --warmup-sec 0   # same with every sample, as a cross-check
python analysis\load_summary.py                         # per-run and per-configuration stats, all samples
```

- **Why the first 120 s are dropped.** RR-1's measurement text excludes them as warm-up. Dropping them changes no
  requirement verdict (`docs/step6_recommendation.md` §4.2).
- **p95.** Counts failed and timed-out requests as slower than any answer.
- **Spread.** A requirement passes only if all 3 runs pass.

---

## 11. Evidence for Slide 7

| Evidence | Where |
| --- | --- |
| SUT hardware, OS, Docker/WSL, Ollama settings, model digests, network, CPU-only proof, commit | `tests/environment/p1_sut_environment.md` (re-run `record_environment.ps1` on test day) |
| Full model pins | `tests/environment/model_pins.json` |
| Load-generator hardware, JMeter/Java, separate-machine proof, network round trip | `tests/environment/loadgen_environment.md` (P2 runs `scripts/record_loadgen_environment.ps1`) |
| Per-run conditions | `runs/<run-id>/run_info.json`, `runs/run_register.csv` |

---

## 12. Background

### 12.1 Decisions settled before the official runs

P1 raised these while setting up the SUT. Each was settled before run 1.

| # | Question | Outcome |
|---|---|---|
| 1 | JMeter was closed-loop (Thread Group + Constant Throughput Timer), which the brief rejects | `load_test.jmx` uses Open Model Thread Groups with Poisson arrivals (§1) |
| 2 | JMeter and README rates were the old Tier A figures (5.5 tickets/h) | Step 4 rates: 1,312 and 3,936 tickets/h, 2 searches per ticket (§1) |
| 3 | Which laptop is the load generator | P2's laptop for every run (§2.3). Running JMeter in Docker on the compose network would put it on the SUT, so it was never used |
| 4 | Prompt v1, the `think` setting and JSON-schema output were P1 defaults, not team decisions | Kept for every official run (§2.2). Changing any of them means redoing every run |
| 5 | How the accuracy score counts 502s (no category) | Counted as incorrect (accuracy playbook) |
| 6 | University Wi-Fi often blocks laptop-to-laptop traffic | Phone hotspot (§2.4) |
| 7 | JMeter's 60 s response timeout hid every latency above 60 s; the plan appended to one fixed `results/results.jtl`; no `X-Run-Id` header | 295 s timeout chosen on purpose (`-Jresponse_timeout_ms`), a new `results/<run-id>-<time>.jtl` per run, `X-Run-Id` from `-Jrun_id` (§5 step 2) |

**The `think` setting (item 4)** only matters for gemma4:e4b. Setup check, one sample each on the invented warm-up
ticket, not official: thinking on (baseline) → 22.1 s, 295 generated tokens; `think=false` → 0.6 s warm, 8 tokens;
same answer both times. Thinking on matches the Step 4 prediction basis (35–45 s). Turning it off is an obvious
Assignment 2 optimisation. To change it: `OLLAMA_THINK=false` in `.env`, then `switch_model.ps1`.

### 12.2 Note for Slide 5

All four pulled digests match the Step 4 short IDs. The default tags use different quantisations: llama3.2:1b Q8_0,
phi3:3.8b Q4_0, mistral:7b Q4_K_M, gemma4:e4b Q4_K_M (8.0B, 8.95 GB). This affects speed and accuracy, so mention it
next to the digests.

### 12.3 Observations for P5's bottleneck analysis

These are not fixes; the baseline stays unoptimised.

- All four endpoints are sync functions, so FastAPI runs them on one shared pool of 40 threads (anyio's default,
  checked in the container). A `POST /tickets` holds its thread for the whole Ollama call.
- Ollama (NUM_PARALLEL=1) classifies one ticket at a time, so at most 40 tickets are inside Ollama: 1 being
  classified and up to 39 in its queue. Ollama's 512-request queue limit is never reached through this service.
- Once 40 tickets are in flight, every new request (ticket, search, stats or health) waits inside the service for a
  free thread, roughly first come first served, with no limit or timeout of its own. Under a ticket backlog, threads
  free up only as fast as Ollama finishes tickets, so a search can wait minutes although it never calls the model.
  This is the main risk for RR-2.
- The 600 s timeout starts when the thread calls Ollama, so a ticket's total time can exceed 600 s. With up to 39
  tickets ahead of it in Ollama's queue, a slow model can hit it (502, `error=ReadTimeout`).
- `GET /search` scans the whole `tickets` table (`LIKE '%q%'`), then fetches each match again with its own query
  (SQLAlchemy expires the loaded rows when the metric row is committed), and returns every full narrative: 1 + N
  queries for N matches (checked in the container: 2 matches → 3 queries). It slows down as a run stores more tickets.
- The database pool is SQLAlchemy's default: 5 connections + 10 overflow. A request that waits more than 30 s for a
  connection fails with 500.
- Ollama (llama.cpp) reuses the processed instruction prefix of the previous prompt. The service caches
  nothing, but Ollama itself processes only the new ticket text. Example from the setup smoke test
  (llama3.2:1b): the first ticket's prompt took 1,482 ms, the next one 179 ms for a similar-length prompt.
  `prompt_tokens` in the log still counts the whole prompt; `prompt_eval_ms` shows the real work. The warm-up
  pays the one-off cost, so every run starts in the same state. Disclose this on the architecture slide.
