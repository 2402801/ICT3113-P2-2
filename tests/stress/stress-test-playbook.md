# Step 5: Stress Test Playbook

## Objectives

- Find max sustainable arrival rate, **gemma4:e4b**, before POST /tickets latency grows unbounded
- Check Prediction Record bottleneck claim: Ollama backend, sequential, no cache, no queue, is the binding constraint
- Confirm/deny: latency diverges near predicted ceiling (80 tickets/hr, from 35-45s single-req latency)
- Satisfy Step 5's "one stress test" requirement, on the highest-value candidate: gemma4:e4b, lowest predicted throughput ceiling, only candidate predicted to breach RR-1 (p95 <=30s @ peak)

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Test type | Arrival-rate ramp (not concurrency ramp) | Directly tests Prediction Record's own wording: "latency grows without bound as arrival rate approaches [ceiling]". Reuses open-loop JMeter protocol already required for load tests. |
| Target model | gemma4:e4b only | Lowest predicted throughput ceiling (80/hr) of candidates. Only candidate predicted to breach RR-1 (p95<=30s). Highest-value single target. |
| Divergence/failure criterion | Intra-step growth >=2x OR step mean >=3x baseline | Baseline = measured, not predicted. Two conditions since small-n per step makes percentile thresholds unreliable alone. |
| Baseline source | Measured (5 sequential single requests), not the 35-45s prediction | Test exists to check the prediction, not assume it. |
| Time budget | <30 min total | Team constraint. Drove step count (5) and step duration (4 min) below. |
| Ramp anchor | Steps centered on predicted ceiling (60%-180%) | Budget too tight to explore far from the interesting zone; ceiling is where divergence is expected to live. |
| Step duration | 4 min/step, 5 steps | Fits budget incl. baseline measurement, setup, buffer. Yields ~4-12 completed requests/step given ~40s latency. |
| Reset between steps | No, continuous ramp | Backlog carryover matches a realistic sustained-load climb; also cheaper than restarting the service 5x inside the time budget. |
| Percentile stats (p50/p95/p99) | Not used for this test | Too few requests per step for percentiles to mean anything; per-request latency trend used instead. |
| Monitoring OS | Deferred, command given for both Linux and Windows | Host OS not yet decided by team; playbook stays executable either way once confirmed. |
| JMeter build | `stress-test/stress-test-plan.jmx`: one **Open Model Thread Group per step** (5 steps + a recovery group), stock JMeter 5.6.3, no plugins | Open Model is one of the two open-loop options the brief allows. It starts a thread per arrival, so no thread pool can become the bottleneck. A first attempt with chained closed Thread Groups + a throughput timer capped at 3 in flight and was discarded (see "Invalid first attempt"). |
| Arrival pattern | Evenly spaced (`even_arrivals`), not Poisson | With only ~4-13 requests per step, Poisson noise would swamp the step-to-step comparison. Every run sends the same count per step. The load tests use Poisson arrivals, so state this difference in the report. |
| Request data | `stress-test/data/tickets.jsonl`: 100 JSON bodies from `datasets/ict3113_tickets_2000_2999.csv` (first 100 rows), read tab-delimited | Narratives contain commas, quotes and newlines, which broke the earlier CSV read. ~42 requests are planned, so no row is reused. |
| Repeat runs | Single ramp, no repeat | Time budget doesn't allow it; flagged as a limitation to state explicitly in the report rather than silently assumed fine. |
| Recovery check | Included as a 6th group (`Recovery`, 120 s at the step-1 rate) | Distinguishes a queueing-delay explanation (recovers) from a harder failure mode (doesn't). |
| Traceability | Every request carries `X-Run-Id`; `req_id` is saved in the `.jtl` | `analysis/reconcile.py` pairs each client sample with its server log line by request ID. Without them the run FAILs reconciliation. |

## Preconditions

- Golden set + Prediction Record: committed. Done.
- Baseline service running, Docker. gemma4:e4b pulled, pinned tag+digest.
- JMeter on **separate machine** from service/Ollama. No co-host: steals CPU, fakes the latency numbers. On the load-generator laptop run `scripts\record_loadgen_environment.ps1 -SutHost <SUT-IP>` once per session and commit the output to `docs/environment/` (Slide 7).
- Service logging on, writing to repo log path. Every request must reconcile w/ a log line.
- SUT session checklist (AC power, Best performance, close heavy apps, `preflight.ps1` ends `PREFLIGHT OK`): `tests/load/LOAD_TEST_PLAYBOOK.md` §4.1. Sync both laptops' clocks first, so JMeter `timeStamp` lines up with the server log `start_ms`.
- `[OPEN]` Ollama host spec (CPU/RAM/OS), TBD, fill in before run. Drives monitoring branch below + Slide 7.

## Step 0: Warm-up (unmeasured)

Done by the SUT operator's `prepare_run.ps1` (sends a warm-up request and prints READY before the run). Loads model into memory. Avoids cold-start penalty polluting the ramp. The plan's own warm-up request is off by default (`-Jwarmup=1` adds one; its label is `Warm-up POST /tickets`, exclude it from step statistics).

```powershell
# SUT laptop
powershell -ExecutionPolicy Bypass -File scripts\p1\prepare_run.ps1 -TestType stress -Config ramp -Run 1 -Tester P2 -Notes "<thermal mode>"
```

Run ID = `gemma4-e4b_stress_ramp_run1`. Send traffic only between READY and `finish_run.ps1`.

**Run record (2026-10-07):** `gemma4-e4b_stress_ramp_run1` was already taken by the invalid first attempt (see below; kept as evidence and listed in `analysis/excluded_runs.csv`), so P1 prepared this ramp as **`gemma4-e4b_stress_ramp_run2`** (READY 11:46:16Z, finished 12:16:36Z). The JMeter command below was run with `-Jrun_id=gemma4-e4b_stress_ramp_run1`, so the `X-Run-Id` in the server log and the `.jtl` file name say `run1`; all 41 requests in that window are this run's traffic. The evidence is in `runs/gemma4-e4b_stress_ramp_run2/`.

## Step 1: Baseline single-req latency (~3.5 min) — DONE

5 sequential single requests. One at a time, no overlap. Log latency client-side + service-side.

- Mean of the 5 = `BASELINE_LATENCY`. Use this, not the 35-45s prediction, since the test is checking the prediction, not assuming it.
- Baseline way off 35-45s? Note it. Changes req count per ramp step below.

**Result (2026-09-29 run, `baseline.jtl`):** 5/5 success, 0 errors. Latencies: 33.92s, 33.57s, 33.26s, 33.54s, 33.27s.
`BASELINE_LATENCY = 33.51s` (33510ms).

This is *below* the 35-45s prediction — implied ceiling is `3600/33.51 ≈ 107 tickets/hr`, not the predicted 80/hr. Per the note-it rule above, Step 2's ramp is recentered on the measured ceiling (107/hr), not the prediction, below.

## Step 2: Arrival-rate ramp (~20 min)

One continuous **open-loop** JMeter run, POST /tickets, 5 stages stepping rate up. No reset between steps: backlog carries over, matches real sustained-load climb.

Rates recentered on the *measured* ceiling (107 tickets/hr from Step 1), same 60/90/110/140/180% spacing as originally planned around the predicted 80/hr ceiling:

| Step | Duration | Rate (tickets/hr) | Rate (req/s) | % of measured ceiling | Expected completions |
|---|---|---|---|---|---|
| 1 | 4 min | 64  | 0.0178 | 60%  | ~4  |
| 2 | 4 min | 97  | 0.0269 | 90%  | ~6  |
| 3 | 4 min | 118 | 0.0328 | 110% | ~8  |
| 4 | 4 min | 150 | 0.0417 | 140% | ~10 |
| 5 | 4 min | 193 | 0.0536 | 180% | ~13 |

After step 5, a **Recovery** group (Step 4 below) sends 120 s at the step-1 rate (64/hr). Total run length is 5 x 240 s + 120 s + a 305 s drain = about 27 min, inside the 30 min budget.

### JMeter build

Open-loop only: closed-loop self-throttles, hides queue buildup, not accepted as evidence. No thread count to size: an Open Model Thread Group starts one thread per arrival, so the arrival rate is the rate in the table whatever the server does.

`stress-test/stress-test-plan.jmx`, JMeter 5.6.3, no plugins:
- Six Open Model Thread Groups named `Step 1` ... `Step 5`, `Recovery`. Each sampler is labelled the same (`Step 3 POST /tickets`), so a `.jtl` splits by step on `label`.
- Schedule per group: `pause(start) rate(R/hour) even_arrivals(240 sec) rate(R/hour) pause(drain)`. Starts are 0 / 240 / 480 / 720 / 960 / 1200 s. No reset between steps.
- The trailing `pause(drain)` is needed because JMeter interrupts a group's in-flight requests the moment its schedule ends. Drain = 5 s connect timeout + `drain_sec` (default 300 s). A request still unanswered then is recorded as an error and means the backlog never cleared: report it, don't discard it.
- Response timeout 630 s (the service's own 600 s Ollama limit + 30 s), so JMeter sees every answer the service gives (200, or 502 when the service gives up).
- CSV Data Set Config per group: `jsonBody` variable, tab delimiter, shared across threads, `recycle=true` as a safety net only (100 rows vs ~42 requests, so no row is reused).
- Header Manager adds `X-Run-Id: ${RUN_ID}`. A Regex Extractor stores the response's `X-Request-ID` as `req_id`.

**Prepare the data once** (on the load-generator laptop, from the repo root):

```bash
cd load-generator
python prepare_data.py --csv ../datasets/ict3113_tickets_2000_2999.csv --limit 100 --output ../stress-test/data/tickets.jsonl
```

**Run** (load-generator laptop, from `stress-test/`; `<SUT-IP>` is in P1's READY banner; check `GET /health` first):

```bash
jmeter -n -t stress-test-plan.jmx \
  -Jhost=<SUT-IP> -Jport=8000 \
  -Jrun_id=gemma4-e4b_stress_ramp_run1 \
  -Jsample_variables=req_id \
  -Jdata_file=data/tickets.jsonl \
  -Jjtl=gemma4-e4b_stress_ramp_run1.jtl \
  -j gemma4-e4b_stress_ramp_run1_jmeter.log
```

`-Jsample_variables=req_id` and `-Jrun_id` are mandatory: without them reconcile cannot trace requests. Do **not** pass `-l` as well: the plan writes its own `.jtl` to the `-Jjtl` path. Optional overrides: `-Jrate_1 ... -Jrate_5` (tickets/hour), `-Jstep_sec`, `-Jrecovery_sec`, `-Jdrain_sec`. To skip the recovery check, disable the `Recovery` group.

**After the run:** on the SUT laptop run `scripts\p1\finish_run.ps1 -RunId gemma4-e4b_stress_ramp_run1`, then copy the `.jtl` (and the JMeter log) into `runs\gemma4-e4b_stress_ramp_run1\` and commit. Then `python analysis/reconcile.py` must report PASS (or explained WARN) for the run.

**Validity checks before using any number** (the first attempt failed all of these):
1. Zero or near-zero HTTP 422s. A 422 is a bad request body, a test bug, not a model result.
2. Requests sent per step is about rate x 240 s / 3600 (4 / 6 / 8 / 10 / 13), plus ~2 in the recovery group.
3. The run ends only after the drain, not early.
4. `reconcile.py` has no FAIL: every `.jtl` row pairs to a server log line by `req_id`.
5. Stored tickets are full narratives (spot-check `tickets.tsv`).

Keep the `.jtl` in repo.

### Invalid first attempt (2026-10-07, not evidence)

A first run (19 requests in 17 min, 12 of 19 were 422) was discarded. Causes found in the plan: narrative variable set by a JSR223 *Listener* (runs after the sampler, so each thread's first request carried the literal `${narrative_json}`); CSV read with `quotedData=false` so multi-line narratives split into fragments; closed-loop Thread Groups with 2-3 threads (at most 3 in flight, so no queue could form); no `X-Run-Id` / `req_id`, so reconcile FAILed. Its 7 good samples (26-60 s) are not used. Keep the note so the report can say why there is a later run.

### Server-side monitoring (concurrent w/ ramp)

CPU + memory on Ollama host, timestamped, full duration of Step 2. Lines up saturation point against where latency diverges (Step 3). Turns "latency exploded" into "Ollama pinned CPU", attributable, not just a symptom.

- **Linux:** `docker stats --no-stream` polled on interval into a log, or `top -b -n <count> -d 5 >> cpu.log` (5s interval), or `vmstat 5 >> vmstat.log`.
- **Windows:** `Get-Counter '\Processor(_Total)\% Processor Time','\Memory\Available MBytes' -Continuous -SampleInterval 5 | Export-Csv cpu.csv`, or Perfmon data collector set, same counters.

`[OPEN]` Pick branch once host OS confirmed. Record exact command here.

## Step 3: Determine the limit

Per step, compute:
1. Intra-step growth = last req latency / first req latency (within step)
2. Step mean latency / `BASELINE_LATENCY`

Limit exceeded if EITHER:
- growth ratio >= 2 (queue visibly growing within step), or
- step mean >= 3x baseline

Report **first step** (lowest rate) tripping either condition. Report rate + which condition fired. Cross-check against CPU/mem log: was Ollama ~100% CPU at/before that point? That's the evidence for/against the bottleneck claim.

No p50/p95/p99 here: each 4-min step only completes ~4-12 requests, too few for percentiles. Signal is the per-request latency trend within a step, not a percentile. State this explicitly: small-n isn't an oversight, it's the time budget.

## Step 4: Recovery check (~2 min, in the plan)

The plan's `Recovery` group drops back to Step 2's step-1 rate (64/hr) for 120 s straight after step 5, no reset. Watch for latency to return toward baseline. Note the backlog from step 5 must clear first, so the first recovery requests are expected to still be slow; judge the trend, and requests unanswered at the end of the drain count as "no recovery". Recovers: queueing-delay story holds (matches prediction). No recovery, or service/Ollama unresponsive: harder failure mode (resource exhaustion etc.), report as such.

## Reporting (Slide 9)

- `BASELINE_LATENCY` + the 5 raw measurements
- Full per-request latency series, all 5 steps (not just summary, small-n caveat above)
- Step + rate where limit hit, which criterion fired
- CPU/mem trace, annotated w/ step boundaries
- Per step: requests sent, achieved throughput (completions per hour), error rate (count 502s and unanswered-at-drain separately from 200s)
- Recovery check result
- vs. prediction: predicted ceiling was 80/hr, measured single-req latency implies ~107/hr, state the step-2 limit against both, and whether predicted RR-1 breach (p95<=30s) actually showed up
- vs. requirements: state the measured limit next to TR-1 (1,312/hr) and TR-2 (3,936/hr). If the limit is below them, say so plainly and name the bottleneck; no fix is needed at this stage.
- Limitations stated explicitly: single run (no spread across runs), evenly spaced rather than Poisson arrivals, small n per step (no percentiles), the invalid first attempt and why a second was run.
- Evidence: `.jtl` (`gemma4-e4b_stress_ramp_run1.jtl`, named after the run ID JMeter was given), server log, DB export and the reconcile result, all in `runs/gemma4-e4b_stress_ramp_run2/`.

## Open items, blocks execution as-written

- `[OPEN]` Ollama host OS + hardware spec
- `[OPEN]` Monitoring command (Linux vs Windows branch above) once host OS is confirmed
- `[OPEN]` `think` setting: baseline 33.51 s was measured with the default (thinking on). Confirm the team keeps it; changing it later means redoing every run (`tests/load/LOAD_TEST_PLAYBOOK.md` §12.1, item 4).
- `[OPEN]` gemma4:e4b tag+digest: confirm matches Prediction Record / Candidate Models slide
- `[OPEN]` Not yet validated end to end: the rebuilt `stress-test-plan.jmx` has not been executed. Review it and do a short dry run (for example `-Jstep_sec=20` with scaled-up rates against a stub or a fast model) before the real run.
