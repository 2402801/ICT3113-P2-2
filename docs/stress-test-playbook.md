# Stress Test Playbook (Step 5)

How Team 2 ran the stress test, in enough detail to repeat it: one arrival-rate ramp on **gemma4:e4b**, run on
7 Oct 2026, preceded by a baseline latency measurement on 29 Sep 2026. An invalid first attempt on 7 Oct is kept
as evidence and excluded (section 5).

- **SUT laptop, operated by P1.** Runs the service, MySQL and Ollama. Its procedure is in
  `docs/LOAD_TEST_PLAYBOOK.md` (sections 2, 3 and 4).
- **Load-generator laptop, operated by P5.** Runs JMeter, on a separate machine from the SUT.
- Commands run from the repository root unless a step says otherwise. Paths are relative to the repository root.
  Times are UTC.

Related playbooks: `docs/ACCURACY_PLAYBOOK.md` (accuracy tests) and `docs/LOAD_TEST_PLAYBOOK.md` (load tests).

---

## 1. What is tested

**Objectives**

- Find the maximum sustainable arrival rate for **gemma4:e4b** before `POST /tickets` latency grows unbounded.
- Check the Prediction Record's bottleneck claim: the Ollama backend (sequential, no cache, no queue) is the
  binding constraint.
- Confirm or deny that latency diverges near the predicted ceiling (80 tickets/h, from the 35–45 s predicted
  single-request latency).
- Satisfy Step 5's "one stress test" requirement on the highest-value candidate: gemma4:e4b has the lowest
  predicted throughput ceiling and is the only candidate predicted to breach RR-1 (p95 ≤ 30 s at peak).

**Design decisions**

| Decision | Choice | Why |
|---|---|---|
| Test type | Arrival-rate ramp (not concurrency ramp) | Directly tests the Prediction Record's own wording: "latency grows without bound as arrival rate approaches [ceiling]". Reuses the open-loop JMeter protocol already required for the load tests. |
| Target model | gemma4:e4b only | Lowest predicted throughput ceiling (80/h) of the candidates. Only candidate predicted to breach RR-1 (p95 ≤ 30 s). Highest-value single target. |
| Baseline source | Measured (5 sequential single requests), not the 35–45 s prediction | The test exists to check the prediction, not assume it. |
| Ramp anchor | Steps at 60 / 90 / 110 / 140 / 180% of the **measured** ceiling (107/h) | Budget too tight to explore far from the interesting zone; the ceiling is where divergence is expected. The spacing was planned around the predicted 80/h and recentred after the baseline came in faster. |
| Divergence / failure criterion | Intra-step growth ≥ 2× **or** step mean ≥ 3× baseline | Baseline is measured, not predicted. Two conditions, since small n per step makes percentile thresholds unreliable alone. |
| Time budget | < 30 min total | Team constraint. Drove the step count (5) and step duration (4 min). |
| Step duration | 4 min per step, 5 steps | Fits the budget including setup and drain. Sends 4–12 requests per step. |
| Reset between steps | No, continuous ramp | Backlog carry-over matches a realistic sustained-load climb; also cheaper than restarting the service 5 times inside the time budget. |
| Percentile stats (p50 / p95 / p99) | Not used for the limit | Too few requests per step for percentiles to mean anything; the per-request latency trend is used instead. |
| JMeter build | `tests/stress/stress-test-plan.jmx`: one **Open Model Thread Group per step** (5 steps + a recovery group), stock JMeter 5.6.3, no plugins | Open Model is one of the two open-loop options the brief allows. It starts a thread per arrival, so no thread pool can become the bottleneck. A first attempt with chained closed Thread Groups + a throughput timer capped at 3 in flight and was discarded (section 5). |
| Arrival pattern | Evenly spaced (`even_arrivals`), not Poisson | With only 4–12 requests per step, Poisson noise would swamp the step-to-step comparison. Every run sends the same count per step. The load tests use Poisson arrivals, so this difference is stated in the report. |
| Request data | `tests/stress/data/tickets.jsonl`: 100 JSON bodies (first 100 rows of the team's dataset extract, rows 2000–2999), read tab-delimited | Narratives contain commas, quotes and newlines, which broke the earlier CSV read. 41 requests were sent, so no row is reused. |
| Recovery check | Included as a 6th group (`Recovery`, 120 s at the step-1 rate) | Distinguishes a queueing-delay explanation (recovers) from a harder failure mode (does not). |
| Repeat runs | Single ramp, no repeat | Time budget does not allow it; stated as a limitation (section 9). |
| Traceability | Every request carries `X-Run-Id`; `req_id` is saved in the `.jtl` | `analysis/reconcile.py` pairs each client sample with its server log line by request ID. |
| Server-side CPU / memory monitoring | Planned alongside the ramp; **not captured** in the run | See section 4.4 for the command and section 9 for the effect. |

**Ramp** (rates recentred on the measured ceiling of 107 tickets/h, section 8.1):

| Group | Starts at | Duration | Rate (tickets/h) | Rate (req/s) | % of measured ceiling | Requests sent |
|---|---|---|---|---|---|---|
| Step 1 | 0 s | 240 s | 64 | 0.0178 | 60% | 4 |
| Step 2 | 240 s | 240 s | 97 | 0.0269 | 90% | 6 |
| Step 3 | 480 s | 240 s | 118 | 0.0328 | 110% | 7 |
| Step 4 | 720 s | 240 s | 150 | 0.0417 | 140% | 10 |
| Step 5 | 960 s | 240 s | 193 | 0.0536 | 180% | 12 |
| Recovery | 1,200 s | 120 s | 64 | 0.0178 | 60% | 2 |

Total run length is 5 × 240 s + 120 s + a 305 s drain = about 27 min, inside the 30 min budget.

**Run ID** = `gemma4-e4b_stress_ramp_run<n>`. The counted run is `gemma4-e4b_stress_ramp_run2`.

---

## 2. Environment and files

| | SUT laptop (P1) | Load-generator laptop (P5) |
|---|---|---|
| Machine | Lenovo Legion Pro 5 (83DF), i9-14900HX, 32 GB, Windows 11 Home, CPU-only inference | P5's laptop (no environment record committed, section 9) |
| Software | Docker Desktop: `server`, `mysql`, `ollama/ollama:0.34.4`, started with `docker compose up -d` | Apache JMeter 5.6.3, no plugins |
| Details recorded in | `tests/environment/p1_sut_environment.md`; per-run state in `runs/<run-id>/run_info.json` | – |

**Network.** Both laptops on the same phone hotspot; the SUT was at `172.20.10.2` on 7 Oct (`172.20.10.3` for the
29 Sep baseline).

**Service settings** are the frozen ones used for every official run (`docs/LOAD_TEST_PLAYBOOK.md` section 2):
gemma4:e4b digest `c6eb396dbd59…` (matches the Step 4 ID, `tests/environment/model_pins.json`), prompt v1,
`think` default (gemma4 reasons before answering), `temperature 0`, `OLLAMA_NUM_PARALLEL=1`, service-to-Ollama
timeout 600 s.

| File | Role |
|---|---|
| `tests/stress/5-single-request-latency-test-plan.jmx` | Baseline plan: 1 thread, 5 sequential requests |
| `tests/stress/baseline.jtl` | Baseline result (29 Sep) |
| `tests/stress/stress-test-plan.jmx` | The ramp plan |
| `tests/stress/data/tickets.jsonl` | 100 request bodies for the ramp |
| `load-generator/prepare_data.py` | Builds `tickets.jsonl` from the dataset extract |
| `scripts/p1/prepare_run.ps1`, `finish_run.ps1` | SUT steps before and after the run |
| `analysis/reconcile.py`, `analysis/load_summary.py` | Reconciliation and per-step statistics |

**How the ramp plan is built** (`tests/stress/stress-test-plan.jmx`):

- Open-loop only: closed-loop self-throttles, hides queue build-up and is not accepted as evidence. There is no
  thread count to size: an Open Model Thread Group starts one thread per arrival, so the arrival rate is the rate
  in the table whatever the server does.
- Six Open Model Thread Groups named `Step 1` … `Step 5`, `Recovery`. Each sampler is labelled after its group
  (`Step 3 POST /tickets`), so a `.jtl` splits by step on `label`.
- Schedule per group: `pause(start) rate(R/hour) even_arrivals(240 sec) rate(R/hour) pause(drain)`. No reset
  between steps.
- The trailing `pause(drain)` is needed because JMeter interrupts a group's in-flight requests the moment its
  schedule ends. Drain = 5 s connect timeout + `drain_sec` (default 300 s). A request still unanswered then is
  recorded as an error and means the backlog never cleared: report it, do not discard it.
- Response timeout 630 s (the service's own 600 s Ollama limit + 30 s), so JMeter sees every answer the service
  gives (200, or 502 when the service gives up).
- CSV Data Set Config per group: `jsonBody` variable, tab delimiter, shared across threads, `recycle=true` as a
  safety net only.
- Header Manager adds `X-Run-Id: ${RUN_ID}`. A Regex Extractor stores the response's `X-Request-ID` as `req_id`.
- The plan's own warm-up request is off by default (`-Jwarmup=1` adds one; its label is `Warm-up POST /tickets`,
  exclude it from step statistics).

---

## 3. Preconditions

1. Golden set and Prediction Record committed (`datasets/`).
2. Baseline service running in Docker on the SUT; gemma4:e4b pulled and matching its pinned digest.
3. JMeter on a **separate machine** from the service and Ollama. Co-hosting steals CPU and distorts the latency
   numbers. On the load-generator laptop, run `scripts\record_loadgen_environment.ps1 -SutHost <SUT-IP>` once per
   session and commit the output to `tests/environment/`.
4. Service logging on, so every request reconciles with a log line.
5. SUT session checklist from `docs/LOAD_TEST_PLAYBOOK.md` section 3.4: AC power, Windows power mode **Best
   performance**, heavy apps closed, `scripts\p1\preflight.ps1` ends with `PREFLIGHT OK`.
6. Sync both laptops' clocks (Settings → Time & language → Sync now), so JMeter `timeStamp` lines up with the
   server log `start_ms`.
7. `tests/stress/data/tickets.jsonl` exists (committed). To rebuild it from the dataset extract, which is not stored
   in the repository:

   ```powershell
   cd load-generator
   python prepare_data.py --csv <path>\ict3113_tickets_2000_2999.csv --limit 100 --output ..\tests\stress\data\tickets.jsonl
   ```

---

## 4. Procedure

### 4.1 Baseline single-request latency (about 3.5 min, done once on 29 Sep)

5 sequential single requests to `POST /tickets`, one at a time with no overlap, using
`tests/stress/5-single-request-latency-test-plan.jmx` (1 thread, 5 loops; the SUT address is set in the plan).

- The mean of the 5 is `BASELINE_LATENCY`. Use this, not the 35–45 s prediction, since the test is checking the
  prediction, not assuming it.
- If the baseline is far from 35–45 s, note it and recentre the ramp rates on the measured ceiling
  (3,600 / `BASELINE_LATENCY`). This was done: see section 8.1.

### 4.2 P1 prepares the SUT (unmeasured warm-up)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\p1\prepare_run.ps1 -TestType stress -Config ramp -Run <n> -Tester P5 -Notes "<thermal mode; step rates>"
```

`prepare_run.ps1` checks the model digest and a clean git tree, sends one fixed warm-up ticket (not measured, so
the ramp does not pay a cold start), confirms the model is loaded on CPU, restarts the service with an empty log,
empties the database and prints `READY <run-id>` with the SUT address. Send traffic only between READY and
`finish_run.ps1`.

### 4.3 P5 runs the ramp and recovery (about 27 min)

On the load-generator laptop, from `tests/stress/`. Check `GET http://<SUT-IP>:8000/health` first. The command is
one line and works in PowerShell and Git Bash:

```
jmeter -n -t stress-test-plan.jmx "-Jhost=<SUT-IP>" "-Jport=8000" "-Jrun_id=<run-id>" "-Jsample_variables=req_id" "-Jdata_file=data/tickets.jsonl" "-Jjtl=<run-id>.jtl" -j <run-id>_jmeter.log
```

- `-Jrun_id` and `-Jsample_variables=req_id` are mandatory: without them reconcile cannot trace requests. Use the
  run ID that `prepare_run.ps1` printed (see the run record in section 4.6).
- Do **not** pass `-l` as well: the plan writes its own `.jtl` to the `-Jjtl` path.
- Optional overrides: `-Jrate_1` … `-Jrate_5` (tickets/hour), `-Jstep_sec`, `-Jrecovery_sec`, `-Jdrain_sec`. To
  skip the recovery check, disable the `Recovery` group.
- One continuous run: 5 steps, then the `Recovery` group drops back to the step-1 rate (64/h) for 120 s with no
  reset, then the drain.

### 4.4 Server-side monitoring (concurrent with the ramp)

Log CPU and memory on the SUT with timestamps for the full ramp, to line up the saturation point against where
latency diverges. On the SUT (Windows 11):

```powershell
Get-Counter '\Processor(_Total)\% Processor Time','\Memory\Available MBytes' -Continuous -SampleInterval 5 | Export-Csv cpu.csv
```

On a Linux host the equivalent is `docker stats --no-stream` polled on an interval, `top -b -d 5 >> cpu.log` or
`vmstat 5 >> vmstat.log`.

**This step was not carried out in the 7 Oct run**: no CPU or memory trace exists for it (section 9).

### 4.5 P1 finishes the run

```powershell
powershell -ExecutionPolicy Bypass -File scripts\p1\finish_run.ps1 -RunId <run-id>
```

Then copy the `.jtl` (and the JMeter log) into `runs\<run-id>\`, commit, and run the checks in section 6.

### 4.6 Run record (7 Oct 2026)

| Time (UTC) | Event |
|---|---|
| 04:05:13 – 04:23:52 | `gemma4-e4b_stress_ramp_run1`: invalid first attempt (section 5) |
| 11:46:16 | P1 prepares the redo as **`gemma4-e4b_stress_ramp_run2`**, since `run1` was already taken. READY |
| 11:49:04 | First request of the ramp |
| 12:09:59 | Last request sent (second recovery request) |
| 12:14:49 | Last answer received; all 41 requests answered |
| 12:16:36 | `finish_run.ps1` done |

JMeter was started with `-Jrun_id=gemma4-e4b_stress_ramp_run1` by mistake. As a result the `X-Run-Id` in the server
log says `run1` and the `.jtl` is named `gemma4-e4b_stress_ramp_run1.jtl`, although it sits in
`runs/gemma4-e4b_stress_ramp_run2/`. All 41 requests in that window are this run's traffic and pair one-to-one by
`req_id`. The plan used was `tests/stress/stress-test-plan.jmx` (committed after the run in `cbfbb73`), not
`load-generator/stress_test.jmx` (since deleted); the register row records this correction, including the 630 s timeout.

---

## 5. Invalid runs and exclusions

An invalid run is **never deleted**: it is listed in `analysis/excluded_runs.csv` with the reason, and the test is
redone under the next run number.

**`gemma4-e4b_stress_ramp_run1` (7 Oct, 04:05–04:23 UTC) is not evidence.** It sent 19 requests in 17 min, of which
12 returned 422. Causes found in the plan it used (kept in the run folder as `stress-test-plan.jmx`):

- The narrative variable was set by a JSR223 *Listener*, which runs after the sampler, so each thread's first
  request carried the literal `${narrative_json}`.
- The CSV was read with `quotedData=false`, so multi-line narratives split into fragments (2 of the 7 stored
  tickets were text fragments).
- Closed-loop Thread Groups with 2–3 threads: at most 3 requests in flight, so no queue could form and the planned
  rates were never reached.
- No `X-Run-Id` and no `req_id`, so reconciliation FAILed.

Its 7 successful samples (26–60 s) are not used. The run folder is kept in `runs/` so the report can say why
there is a later run.

---

## 6. Reconciliation and validity checks

```powershell
python analysis\reconcile.py runs\gemma4-e4b_stress_ramp_run2
```

Check all of these before using any number. The first attempt failed all of them.

| # | Check | Result for `gemma4-e4b_stress_ramp_run2` |
|---|---|---|
| 1 | Zero or near-zero HTTP 422s (a 422 is a bad request body: a test bug, not a model result) | 0 of 41; all 41 returned 200 |
| 2 | Requests sent per step ≈ rate × 240 s / 3,600, rounded down | 4 / 6 / 7 / 10 / 12, plus 2 in recovery, as expected |
| 3 | The run ends only after the drain, not early | Yes: last answer at 12:14:49, no request cut off |
| 4 | Every `.jtl` row pairs to a server log line by `req_id` | 41 of 41 pair; 41 tickets stored |
| 5 | Stored tickets are full narratives (spot-check `tickets.tsv`) | 41 stored narratives of 225–2,006 characters, no fragments |

**Reconcile verdict: FAIL, explained.** `reconcile.py` fails the run on two points only, both recorded in
`runs/run_register.csv`:

- the 41 requests are tagged `gemma4-e4b_stress_ramp_run1` (the mistyped `-Jrun_id`, section 4.6);
- one `GET /favicon.ico` 404 at 11:47:05, from a browser health check before JMeter started.

It also warns that all 41 paired requests took slightly less time at the client than at the server.

---

## 7. Analysis

```powershell
python analysis\load_summary.py      # per-step rows for the stress run are in analysis/output/load_summary.md
```

**Limit.** Per step, compute:

1. Intra-step growth = last request's latency / first request's latency within the step.
2. Step mean latency / `BASELINE_LATENCY`.

The limit is exceeded if **either** growth ≥ 2 (queue visibly growing within the step) **or** step mean ≥ 3×
baseline. Report the **first step** (lowest rate) that trips either condition, the rate, and which condition
fired.

No p50 / p95 / p99 is used for the limit: each 4-minute step sends only 4–12 requests, too few for percentiles.
The signal is the per-request latency trend within a step. The small n is a consequence of the time budget, not an
oversight.

**Recovery.** Watch for latency returning toward baseline. The backlog from step 5 must clear first, so the first
recovery requests are expected to be slow; judge the trend. Requests unanswered at the end of the drain count as
"no recovery".

- Recovers: the queueing-delay explanation holds (matches the prediction).
- No recovery, or the service or Ollama unresponsive: a harder failure mode (resource exhaustion and so on); report
  it as such.

---

## 8. Results

### 8.1 Baseline (29 Sep 2026, `tests/stress/baseline.jtl`)

5 of 5 successful, 0 errors. Latencies: 33.92 s, 33.57 s, 33.26 s, 33.54 s, 33.27 s.

**`BASELINE_LATENCY` = 33.51 s.** This is just below the 35–45 s prediction. The implied ceiling is
3,600 / 33.51 ≈ **107 tickets/h**, not the predicted 80/h, so the ramp was recentred on 107/h.

### 8.2 Ramp (7 Oct 2026, `runs/gemma4-e4b_stress_ramp_run2/`)

41 requests sent, 41 answered with HTTP 200, 0 errors, 0 unanswered at the drain. Slowest request 309.2 s.

| Group | Rate (tickets/h) | Sent | First (s) | Last (s) | Growth | Mean (s) | × baseline | Most open at once | Limit exceeded? |
|---|---|---|---|---|---|---|---|---|---|
| Step 1 | 64 | 4 | 42.3 | 29.5 | 0.70 | 35.0 | 1.04 | 1 | No |
| Step 2 | 97 | 6 | 31.0 | 46.6 | 1.50 | 37.5 | 1.12 | 2 | No |
| Step 3 | 118 | 7 | 47.9 | 116.6 | **2.44** | 78.3 | 2.34 | 4 | **Yes: growth ≥ 2** |
| Step 4 | 150 | 10 | 103.3 | 151.7 | 1.47 | 124.3 | **3.71** | 8 | Yes: mean ≥ 3× |
| Step 5 | 193 | 12 | 157.0 | 302.4 | 1.93 | 215.5 | **6.43** | 10 | Yes: mean ≥ 3× |
| Recovery | 64 | 2 | 309.2 | 290.1 | 0.94 | 299.6 | 8.94 | 2 | – |

The full per-request series is the `.jtl` (41 rows). "Most open at once" is JMeter's `allThreads`.

### 8.3 Limit

**The limit is first exceeded at step 3 (118 tickets/h), on the growth criterion (2.44 ≥ 2).** Step 2 (97/h) trips
neither condition. The maximum sustainable arrival rate is therefore **between 97 and 118 tickets/h**, which
brackets the 107/h implied by the baseline.

### 8.4 Recovery

The two recovery requests took 309.2 s and 290.1 s: latency **did not return toward baseline within the 120 s
recovery window**. Both were answered, the backlog cleared 4 min 50 s after the last arrival, and the service
returned no errors at any point. This fits a queueing delay rather than a harder failure, but the window was too
short (2 requests) to show latency coming back to baseline.

### 8.5 Against the prediction

| Prediction (Prediction Record) | Measured | Verdict |
|---|---|---|
| Single-request latency 35–45 s | 33.5 s mean (baseline); 35.0 s mean at 64/h | Just below the range |
| Throughput ceiling 80 tickets/h | Limit between 97 and 118/h; baseline implies 107/h | Higher than predicted |
| Latency grows without bound as the arrival rate approaches the ceiling | Mean latency 37.5 s at 97/h, 78.3 s at 118/h, 215.5 s at 193/h, still rising | Confirmed |
| gemma4:e4b breaches RR-1 (p95 ≤ 30 s) | One request alone takes about 34 s, above 30 s before any queueing | Confirmed |
| Bottleneck is the Ollama backend | Consistent: the limit matches 1 ÷ single-request time. Not confirmed by a CPU trace (section 9) | Consistent |

### 8.6 Against the requirements

The measured limit of 97–118 tickets/h is far below TR-1 (1,312/h, 11–14× higher) and TR-2 (3,936/h, 33–41×
higher). One node running gemma4:e4b cannot meet either. The bottleneck is the model's per-ticket time with Ollama
classifying one ticket at a time; as the brief allows for Assignment 1, it is diagnosed and not fixed.

---

## 9. Limitations

- **Single run.** One ramp, so there is no spread across runs.
- **Small n per step** (4–12 requests), so no percentiles are used for the limit.
- **Evenly spaced arrivals**, not Poisson as in the load tests.
- **No CPU or memory trace.** The monitoring in section 4.4 was not run, so the bottleneck claim rests on the
  latency series and the service and Ollama logs, not on a resource trace.
- **Baseline taken outside the run procedure.** The 29 Sep baseline was sent without `prepare_run.ps1`, so there is
  no run folder, service log or power-state record for it. Step 1 of the ramp (mean 35.0 s at 64/h) supports it.
- **Short recovery window.** 120 s and 2 requests cannot show a return to baseline (section 8.4).
- **Mistyped run tag.** The `.jtl` name and `X-Run-Id` say `run1` while the evidence is in the `run2` folder, which
  is why reconciliation reports FAIL (section 6).
- **No load-generator environment record** was committed for P5's laptop.
- **An invalid first attempt** preceded this run (section 5).

---

## 10. Evidence

| What | Where |
|---|---|
| Baseline samples | `tests/stress/baseline.jtl` |
| Ramp client samples (named after the run ID JMeter was given) | `runs/gemma4-e4b_stress_ramp_run2/gemma4-e4b_stress_ramp_run1.jtl` |
| Ramp server side | `runs/gemma4-e4b_stress_ramp_run2/server_access.log`, `tickets.tsv`, `request_metrics.tsv`, `ollama.log` |
| Model, digest, commit, power state, READY time; CPU-only proof | `runs/gemma4-e4b_stress_ramp_run2/run_info.json`; `ollama_ps_before.*`, `ollama_ps_after.*` |
| Run notes and the explained reconcile FAIL | `runs/run_register.csv` |
| Invalid first attempt | `runs/gemma4-e4b_stress_ramp_run1/`; reason in `analysis/excluded_runs.csv` |
| Per-step statistics | `analysis/output/load_summary.md` (section `gemma4-e4b_stress_ramp`) |
| Plans and data | `tests/stress/stress-test-plan.jmx`, `tests/stress/5-single-request-latency-test-plan.jmx`, `tests/stress/data/tickets.jsonl` |
