# Load Test Playbook (Step 5)

How Team 2 ran the 36 official load runs, in enough detail to repeat them. The runs were 4 candidate models ×
3 load configurations × 3 runs, on 7–8 Oct 2026.

Two laptops take part:

- **SUT laptop, operated by P1.** Runs the service, MySQL and Ollama. Its per-run procedure is in
  [`docs/P1_SUT_RUNBOOK.md`](P1_SUT_RUNBOOK.md).
- **Load-generator laptop, operated by P2.** Runs JMeter. This playbook adds the JMeter side and ties both together.

The stress test has its own playbook: [`stress-test/stress-test-playbook.md`](../stress-test/stress-test-playbook.md).

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
`docs/environment/model_pins.json`.

| Order | Model | Runs |
|---|---|---|
| 1–9 | `gemma4:e4b` | `tkt-normal` run 1–3, `tkt-peak` run 1–3, `mix-peak` run 1–3 |
| 10–18 | `llama3.2:1b` | same order |
| 19–27 | `phi3:3.8b` | same order |
| 28–36 | `mistral:7b` | same order |

**Run ID** = `<model>_load_<configuration>_run<n>`, with the `:` in the model tag written as `-`. For example,
`phi3-3.8b_load_tkt-peak_run2`.

---

## 2. Equipment and software

| | SUT laptop (P1) | Load-generator laptop (P2) |
|---|---|---|
| Machine | Lenovo Legion Pro 5, i9-14900HX, 32 GB, CPU-only inference | Acer Swift SFG14-73, Core Ultra 7 155H, 15.7 GB |
| Software | Docker Desktop: `server`, `mysql`, `ollama/ollama:0.34.4`, started with `docker compose up -d` | Apache JMeter 5.6.3, Java 17, Python 3 (for `prepare_data.py`) |
| Details recorded in | `docs/environment/p1_sut_environment.md` | `docs/environment/loadgen_environment.md` |

The service settings are frozen for every run (prompt v1, `think` default, `OLLAMA_NUM_PARALLEL=1`, temperature 0;
see `P1_SUT_RUNBOOK.md` §2). **Never run JMeter on the SUT laptop.**

**Network.** Both laptops join the same phone hotspot. All 36 official runs sent their traffic over the hotspot to
the SUT at `172.20.10.2`. One run, `gemma4-e4b_load_tkt-normal_run1`, was prepared just before the SUT joined the
hotspot; its register note records this. Attempts over university Wi-Fi, and with the two laptops on separate
networks, failed to connect, which is why the hotspot is used.

---

## 3. One-time preparation

### 3.1 Ticket file (P2)

JMeter reads one JSON request body per line from `load-generator/data/tickets.jsonl`. Build it from the team's
dataset extract, rows 2000–2999 of the course CSV. The extract is not stored in this repository.

```powershell
cd load-generator
python prepare_data.py --csv <path>\ict3113_tickets_2000_2999.csv --output data\tickets.jsonl
```

All ticket groups share one cursor on the file, in file order, and every run starts again from the first line.
Search terms come from `load-generator/data/search_terms.csv` (17 terms, committed). Both files are read on a loop.

### 3.2 Dry run: check that ticket-only runs send no searches (P2)

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

1. Plug in AC power. Set Windows power mode to **Best performance**. Set "When plugged in, put my device to sleep
   after" to **Never** (`powercfg /change standby-timeout-ac 0`).
2. Quit the native Windows Ollama app (tray icon → Quit) and close heavy applications.
3. Join the hotspot, then run:

   ```powershell
   git pull --no-edit
   docker compose up -d
   powershell -ExecutionPolicy Bypass -File scripts\p1\preflight.ps1      # must end with PREFLIGHT OK
   ipconfig                                                              # send the Wi-Fi IPv4 to P2
   ```

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

4. Send the generated `loadgen_environment.md` to P1 for `docs/environment/`.

`ping` is not a valid connectivity check: the SUT's firewall does not answer it even when port 8000 is reachable.
Use `Test-NetConnection` on port 8000.

### 4.3 P1, when the model changes (before runs 1, 10, 19 and 28)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\p1\switch_model.ps1 -Model <tag>
```

---

## 5. Every run

### Step 1: P1 prepares the SUT

```powershell
powershell -ExecutionPolicy Bypass -File scripts\p1\prepare_run.ps1 -TestType load -Config <configuration> -Run <n> -Tester P2 -Notes "<rates; 5 min send, 295 s timeout; network>"
```

`prepare_run.ps1` does the following, then prints `READY <run-id>`:
- checks the model digest, a clean git tree, AC power and power mode;
- sends one warm-up ticket and confirms the model is loaded on CPU;
- restarts the service with an empty request log and empties the database.

It refuses an ID that already has a folder, so evidence is never overwritten. P1 tells P2 "READY" and the run ID.

### Step 2: P2 runs JMeter once, in `load-generator`

The common part of every command:

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
   git add runs docs/environment
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

| File | Content |
|---|---|
| `<run-id>-<time>.jtl` | Every client sample: start time, elapsed time, status, `req_id` |
| `server_access.log` | One line per request the service handled during the run |
| `tickets.tsv`, `request_metrics.tsv` | Database rows written during the run |
| `ollama.log` | Ollama's log for the run window, one line per inference |
| `ollama_ps_before.*`, `ollama_ps_after.*` | Model resident with `size_vram = 0`, proving CPU-only inference |
| `run_info.json`, `warmup_access.log` | Model, digest, commit, power state, SUT URL, READY time; the warm-up request |

`runs/run_register.csv` indexes all runs and holds the notes explaining each reconcile result.

---

## 8. Analysis

```powershell
python analysis\requirements_matrix.py                  # requirement verdicts; drops the first 120 s of each run
python analysis\requirements_matrix.py --warmup-sec 0   # same with every sample, as a cross-check
python analysis\load_summary.py                         # per-run and per-configuration stats, all samples
```

- **Why the first 120 s are dropped.** RR-1's measurement text excludes them as warm-up. Dropping them changes no
  requirement verdict (`docs/step6_recommendation.md` §4.2).
- **p95.** Counts failed and timed-out requests as slower than any answer.
- **Spread.** A requirement passes only if all 3 runs pass.
