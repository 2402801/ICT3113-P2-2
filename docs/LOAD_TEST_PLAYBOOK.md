# Load Test Playbook (Step 5)

How Team 2 ran the 36 official load runs, in enough detail to repeat them. The runs were 4 candidate models ×
3 load configurations × 3 runs, on 7–8 Oct 2026. Eight earlier or failed attempts are excluded and kept as
evidence (section 5).

- **SUT laptop, operated by P1.** Runs the service, MySQL and Ollama. Its per-run procedure is in
  `docs/P1_SUT_RUNBOOK.md`.
- **Load-generator laptop, operated by P2.** Runs JMeter, on a separate machine from the SUT. This playbook adds
  the JMeter side and ties both together.
- Commands are Windows PowerShell 5.1 and run from the repository root unless a step says otherwise. Paths are
  relative to the repository root. Times are UTC unless marked SGT.

Related playbooks: `docs/ACCURACY_PLAYBOOK.md` (accuracy tests) and `docs/stress-test-playbook.md`
(stress test).

---

## 1. What is tested

| Configuration | Traffic, open-loop with random (Poisson) arrivals | Requests per run: planned | Requests per run: sent | Requirements it tests |
|---|---|---|---|---|
| `tkt-normal` | `POST /tickets` at 1,312/h | about 109 tickets | 107 tickets | TR-1 |
| `tkt-peak` | `POST /tickets` at 3,936/h | about 328 tickets | 327 tickets | RR-1, TR-2 |
| `mix-peak` | `POST /tickets` at 3,936/h **and** `GET /search` at 7,872/h | about 328 tickets + 656 searches | 327 tickets + 654 searches | RR-2 |

The sent counts were the same in every one of the 36 runs.

Where the rates come from:
- **Tickets:** 1,312/h is the average hour and 3,936/h the peak hour (3 × average), from the Step 3 workload
  model and Step 4 (TR-1, TR-2).
- **Searches:** 7,872/h is 2 searches per ticket, the middle of the 1–3 per ticket in Step 3.

Each run sends traffic for 5 minutes (300 s) at one steady rate. Every request then gets up to 295 s to answer, so
JMeter runs for about 10 minutes.

**Requirements checked** (Step 4):

| Requirement | Pass condition |
|---|---|
| RR-1 | `POST /tickets` p95 ≤ 30 s at 3,936/h, with < 1% errors |
| RR-2 | `GET /search` p95 ≤ 500 ms under the mixed load, with < 1% errors |
| TR-1 | 1,312 tickets/h sustained, with < 1% errors and no latency drift |
| TR-2 | 3,936 tickets/h sustained, with < 1% errors |

**Models, in run order.** The model changes only three times. Pinned tags and digests are in
`docs/environment/model_pins.json`.

| Order | Model | Date | Runs |
|---|---|---|---|
| 1–9 | `gemma4:e4b` | 7 Oct | `tkt-normal` run 1–3, `tkt-peak` run 1–3, `mix-peak` run 1–3 |
| 10–18 | `llama3.2:1b` | 7 Oct | same order |
| 19–27 | `phi3:3.8b` | 8 Oct | same order |
| 28–36 | `mistral:7b` | 8 Oct | same order |

**Run ID** = `<model>_load_<configuration>_run<n>`, with the `:` in the model tag written as `-`. For example,
`phi3-3.8b_load_tkt-peak_run2`.

---

## 2. Environment and files

| | SUT laptop (P1) | Load-generator laptop (P2) |
|---|---|---|
| Machine | Lenovo Legion Pro 5 (83DF), i9-14900HX, 32 GB, Windows 11 Home, CPU-only inference | Acer Swift SFG14-73, Core Ultra 7 155H, 15.7 GB, Windows 11 Home |
| Software | Docker Desktop: `server`, `mysql`, `ollama/ollama:0.34.4`, started with `docker compose up -d` | Apache JMeter 5.6.3, Java 17, Python 3 (for `prepare_data.py`) |
| Details recorded in | `docs/environment/p1_sut_environment.md` (recorded 26 Sep); per-run power state and address in `runs/<run-id>/run_info.json` | `docs/environment/loadgen_environment_2026-10-08.md` (8 Oct session); `docs/environment/loadgen_environment.md` (29 Sep rehearsal) |

The service settings are frozen for every run (prompt v1, `think` default, `OLLAMA_NUM_PARALLEL=1`, temperature 0;
see `docs/P1_SUT_RUNBOOK.md` section 2). **Never run JMeter on the SUT laptop.**

**Network.** Both laptops join the same phone hotspot. All 36 official runs sent their traffic over the hotspot to
the SUT at `172.20.10.2` (HTTP round trip to `/health` on 8 Oct: median 11.9 ms). One run,
`gemma4-e4b_load_tkt-normal_run1`, was prepared just before the SUT joined the hotspot; its register note records
this. Attempts over university Wi-Fi, and with the two laptops on separate networks, failed to connect, which is
why the hotspot is used.

| File | Role |
|---|---|
| `load-generator/load_test.jmx` | The JMeter plan (Open Model Thread Groups, no plugins) |
| `load-generator/prepare_data.py` | Builds the ticket file from the dataset extract |
| `load-generator/data/tickets.jsonl` | One JSON request body per line (built locally, not committed) |
| `load-generator/data/search_terms.csv` | 17 search terms (committed) |
| `scripts/p1/preflight.ps1`, `switch_model.ps1`, `prepare_run.ps1`, `finish_run.ps1` | SUT steps |
| `scripts/record_loadgen_environment.ps1` | Records the load-generator machine and its link to the SUT |
| `analysis/reconcile.py` | Checks each run's `.jtl` against the service's own logs (section 6) |
| `analysis/load_summary.py`, `analysis/requirements_matrix.py` | Statistics and requirement verdicts (section 7) |
| `analysis/excluded_runs.csv` | Runs that were invalidated, with the reason (section 5) |

---

## 3. Preconditions

### 3.1 One-time: ticket file (P2)

JMeter reads one JSON request body per line from `load-generator/data/tickets.jsonl`. Build it from the team's
dataset extract, rows 2000–2999 of the course CSV. The extract is not stored in this repository.

```powershell
cd load-generator
python prepare_data.py --csv <path>\ict3113_tickets_2000_2999.csv --output data\tickets.jsonl
```

All ticket groups share one cursor on the file, in file order, and every run starts again from the first line.
Search terms come from `load-generator/data/search_terms.csv`. Both files are read on a loop.

### 3.2 One-time: dry run, to check that ticket-only runs send no searches (P2)

This targets P2's own laptop on port 1, where nothing listens, so nothing reaches the SUT.

```powershell
jmeter -n -t load_test.jmx "-Jhost=127.0.0.1" "-Jport=1" "-Jrun_id=dryrun" "-Jsearch_k=0" "-Jtickets_per_hour_tr1=3936" "-Joffpeak_duration_sec=10" "-Jpeak_duration_sec=10" "-Jresponse_timeout_ms=1000" "-Jjtl=dryrun.jtl"
(Select-String dryrun.jtl -Pattern "GET /search").Count    # must be 0
(Select-String dryrun.jtl -Pattern "POST /tickets").Count  # about 30, all errors (expected)
Remove-Item dryrun.jtl
```

### 3.3 Start of each test session: P1, on the SUT laptop

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

### 3.4 Start of each test session: P2, on the load-generator laptop

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

### 3.5 When the model changes: P1 (before runs 1, 10, 19 and 28)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\p1\switch_model.ps1 -Model <tag>
```

---

## 4. Procedure

Repeat these four steps for every run.

### Step 1: P1 prepares the SUT

```powershell
powershell -ExecutionPolicy Bypass -File scripts\p1\prepare_run.ps1 -TestType load -Config <configuration> -Run <n> -Tester P2 -Notes "<rates; 5 min send, 295 s timeout; network>"
```

`prepare_run.ps1` does the following, then prints `READY <run-id>`:
- checks the model digest, a clean git tree and that the native Windows Ollama is not running;
- records AC power and power mode, with a warning if the SUT is on battery or not on Best performance;
- sends one warm-up ticket (not measured) and confirms the model is loaded on CPU;
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
- **`-Jresponse_timeout_ms=295000`** counts a request not answered within 295 s as an error. Each schedule ends
  with a drain pause of 300 s (5 s connect + 295 s response timeout), so a run lasts about 10 minutes.

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

**As run:** in several overloaded runs on 7–8 Oct, `finish_run.ps1` was started 20–60 s after JMeter ended, before
the stalled log lines were written. This is one cause of the reconcile FAILs in section 6; the register note of
each affected run gives the actual gap.

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

3. Read the reconcile verdict against section 6 before the next run.
4. Check the new `.jtl` for gaps in arrivals followed by bursts. These were seen on 7 Oct, before P2's sleep and
   power-saving settings were changed, and are recorded in the register notes of the affected gemma4 runs.

---

## 5. Invalid runs and exclusions

A run is invalid if traffic did not reach the SUT, the network dropped, or a laptop slept.

1. **Keep its evidence.** An invalid run is never deleted from history. Rename the run folder with a suffix, e.g.
   `-dropped` or `-noconnect`, and commit it. Change its row in `runs/run_register.csv` to the new ID.
2. Add it to `analysis/excluded_runs.csv` with the reason.
3. Redo the run under the **same** run ID.

Excluded load runs. Their folders were later removed from the working tree, but their files remain in git history
at the commit shown:

| Excluded run | Date | Reason | Files in git |
|---|---|---|---|
| `llama3.2-1b_load_tr1tr2_run1` | 5 Oct | Prepared but never used: no test traffic. The plan changed to separate normal and peak runs | `6a3d05f` |
| `llama3.2-1b_load_tr1_run1`, `_run2`, `_run3` | 5 Oct | Superseded old design (tickets + search at 1,312/h). The plan restarted as the 36 runs in section 1 | `297b708` (runs 1–2), `c2fb0c2` (run 3) |
| `gemma4-e4b_load_tkt-normal_run2-dropped` | 7 Oct | Hotspot disconnected mid-run | `ad2a1af` |
| `phi3-3.8b_load_tkt-normal_run1-noconnect` | 7 Oct | SUT on university Wi-Fi while JMeter targeted the hotspot address: 107 × connect timed out | `bc625eb` |
| `phi3-3.8b_load_tkt-normal_run1-refused` | 8 Oct | P2 on a different network: 107 × connection refused | `bb3e89c` |
| `mistral-7b_load_mix-peak_run2-noconnect` | 8 Oct | The SUT slept while READY: AC sleep timer was 1 h, and all 981 requests timed out connecting | `5ead1f5` |

---

## 6. Reconciliation

```powershell
python analysis\reconcile.py        # no arguments = every finished run; writes analysis/output/reconciliation.csv
```

`reconcile.py` pairs every JMeter sample with its server log line (by `req_id`, else by time) and checks both
against the database export.

| Result | What it means |
|---|---|
| `PASS` | Every record pairs |
| `WARN` | Explained differences, e.g. client timeouts the service completed later |
| `FAIL` on an **overloaded** run | Known pattern: stored tickets missing from the request log, server HTTP 500s with no client record. Record the explanation as a note in `runs/run_register.csv` |
| `FAIL` for any other reason | Stop and investigate before the next run |

**Result for the 36 official runs: 8 PASS, 10 WARN, 18 FAIL.** Every FAIL is on an overloaded run and is explained
in `runs/run_register.csv`. Every client sample in the `.jtl` files is kept.

| Model | `tkt-normal` | `tkt-peak` | `mix-peak` |
|---|---|---|---|
| llama3.2:1b | PASS, PASS, WARN | WARN × 3 | WARN × 3 |
| phi3:3.8b | PASS × 3 | FAIL × 3 | FAIL × 3 |
| mistral:7b | PASS × 3 | FAIL × 3 | FAIL × 3 |
| gemma4:e4b | FAIL × 3 | WARN, WARN, FAIL | WARN, FAIL, FAIL |

The explained FAIL pattern:
- **Stored but not logged.** Tickets are in the database but have no `POST /tickets 200` line in the service log,
  because `finish_run.ps1` stopped the service before the stalled lines were written. In the phi3 and mistral
  peak and mixed runs this is exactly 15 tickets per run, the size of the database connection pool.
- **Unpaired HTTP 500s.** The service returned 500 (sqlalchemy QueuePool limit: 5 + 10 overflow, 30 s wait) to
  requests whose client sample had already timed out.

The committed `analysis/output/reconciliation.csv` predates the 8 Oct runs; re-run the command above to refresh
it.

---

## 7. Analysis

```powershell
python analysis\requirements_matrix.py                  # requirement verdicts; drops the first 120 s of each run
python analysis\requirements_matrix.py --warmup-sec 0   # same with every sample, as a cross-check
python analysis\load_summary.py                         # per-run and per-configuration stats, all samples
```

Outputs are written to `analysis/output/`: `requirements_matrix.md`, `requirements_matrix_load.csv`,
`load_summary.md`, `load_summary.csv`, `load_runs.csv`.

- **Why the first 120 s are dropped.** RR-1's measurement text excludes them as warm-up. This leaves about 3
  minutes of traffic per run. Dropping them changes no requirement verdict (`docs/step6_recommendation.md`
  section 4.2).
- **p95.** Counts failed and timed-out requests as slower than any answer, so it shows "> 295 s" once more than 5%
  of requests failed.
- **Drift (TR-1, TR-2).** Median latency of the second half of the window divided by the first half; 1.5 or more
  counts as a growing queue.
- **Spread.** Each figure is the mean of 3 runs. A requirement passes only if all 3 runs pass.

---

## 8. Results

From `analysis/output/requirements_matrix.md`: requests sent after the first 120 s of each run, mean of 3 runs.

| Requirement | llama3.2:1b | phi3:3.8b | mistral:7b | gemma4:e4b |
|---|---|---|---|---|
| RR-1 | **PASS**: p95 20.0 s (worst run 23.7 s), 0.0% errors | FAIL: p95 > 295 s, 98.5% errors | FAIL: p95 > 295 s, 100.0% errors | FAIL: p95 > 295 s, 100.0% errors |
| RR-2 | **PASS**: p95 134 ms (worst run 155 ms), 0.0% errors | FAIL: p95 > 295 s, 79.1% errors | FAIL: p95 > 295 s, 97.0% errors | FAIL: p95 > 295 s, 100.0% errors |
| TR-1 | **PASS**: 190/190 answered OK, drift ×0.82–1.01 | **PASS**: 192/192 answered OK, drift ×0.61–1.31 | FAIL: 191/191 answered OK but drift ×1.70–2.38 (queue grows) | FAIL: 0/193 answered OK |
| TR-2 | **PASS**: 575/575 answered OK, drift ×0.41–1.39 | FAIL: 9/589 answered OK | FAIL: 0/583 answered OK | FAIL: 0/585 answered OK |

**Only llama3.2:1b meets all four load requirements. phi3:3.8b meets TR-1 only. mistral:7b and gemma4:e4b meet
none.**

Server-side errors per run (all samples):

| Model | Configuration | HTTP 500 per run | HTTP 502 per run |
|---|---|---|---|
| llama3.2:1b | all three | 0, 0, 0 | 0, 0, 0 |
| phi3:3.8b | `tkt-normal` | 0, 0, 0 | 0, 0, 0 |
| phi3:3.8b | `tkt-peak` | 165, 174, 175 | 0, 0, 0 |
| phi3:3.8b | `mix-peak` | 365, 367, 348 | 0, 0, 0 |
| mistral:7b | `tkt-normal` | 0, 0, 0 | 0, 0, 0 |
| mistral:7b | `tkt-peak` | 90, 105, 101 | 0, 0, 0 |
| mistral:7b | `mix-peak` | 325, 298, 370 | 0, 0, 0 |
| gemma4:e4b | `tkt-normal` | 0, 0, 0 | 11, 14, 22 |
| gemma4:e4b | `tkt-peak` | 7, 7, 0 | 17, 18, 0 |
| gemma4:e4b | `mix-peak` | 12, 2, 3 | 13, 0, 0 |

HTTP 500 = database connection pool exhausted (5 + 10 overflow, 30 s wait). HTTP 502 = the service's 600 s limit
on one Ollama call.

Per-configuration latency, throughput and error figures for all samples (mean ± SD, min–max across the 3 runs) are
in `analysis/output/load_summary.md`.

---

## 9. Limitations

| Step 4 says | What was done | Effect |
|---|---|---|
| 10-min steady-state window (RR-1, RR-2, TR-2); 30 min for TR-1 | 5-min runs with the first 120 s excluded, so about 3 min × 3 runs | Verdicts are clear-cut (0% against ≥ 79% errors), but drift beyond 5 min is untested |
| Response timeout 120 s | 295 s | No verdict changes: the slowest successful request in any passing configuration was 27.4 s |
| Searches at 11,808/h | 7,872/h (2 per ticket) | llama3.2:1b's RR-2 pass is shown at 7,872/h only |
| Ticket store pre-loaded before mixed runs | Each run starts with an empty store; tickets enter only through `POST /tickets` | Searches run against a smaller store than in production |
| CPU / RAM monitoring log | Not run | The bottleneck diagnosis rests on service, Ollama and JMeter logs |

Other limitations:

- **Reconciliation.** 18 of the 36 runs fail `reconcile.py`; each is explained in `runs/run_register.csv`
  (section 6).
- **`finish_run.ps1` timing.** The 2-minute wait in Step 3 was not kept in every overloaded run.
- **Load-generator glitches on 7 Oct.** Three gemma4 runs had short gaps in arrivals followed by bursts, or
  connection resets, on P2's side (`gemma4-e4b_load_tkt-normal_run2` and `_run3`, `gemma4-e4b_load_mix-peak_run1`).
  All requests still reached the service; the register notes give the times.
- **Environment records.** The SUT record is from 26 Sep and shows Balanced power mode and a home network; the
  power state and address of each run are in its `run_info.json`. There is no separate load-generator record for
  the 7 Oct session (same laptop and hotspot as 8 Oct).
- **Test setup.** One consumer laptop (CPU only) as the SUT, over a phone hotspot, so network jitter is part of
  every measured response time.

---

## 10. Evidence

Kept per run in `runs/<run-id>/`:

| File | Content |
|---|---|
| `<run-id>-<time>.jtl` | Every client sample: start time, elapsed time, status, `req_id` |
| `server_access.log` | One line per request the service handled during the run |
| `tickets.tsv`, `request_metrics.tsv` | Database rows written during the run |
| `ollama.log` | Ollama's log for the run window, one line per inference |
| `ollama_ps_before.*`, `ollama_ps_after.*` | Model resident with `size_vram = 0`, proving CPU-only inference |
| `run_info.json`, `warmup_access.log` | Model, digest, commit, power state, SUT URL, READY time; the warm-up request |

Across runs:

| What | Where |
|---|---|
| Index of all runs, with the note explaining each reconcile result | `runs/run_register.csv` |
| Excluded runs and reasons | `analysis/excluded_runs.csv` |
| Reconciliation result | `analysis/output/reconciliation.csv` |
| Requirement verdicts and load metrics (both windows) | `analysis/output/requirements_matrix.md`, `requirements_matrix_load.csv` |
| Per-run and per-configuration statistics, all samples | `analysis/output/load_summary.md`, `load_summary.csv`, `load_runs.csv` |
| Environment records | `docs/environment/` |
