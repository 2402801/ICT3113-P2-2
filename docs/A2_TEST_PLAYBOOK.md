# A2 Speed Test — Method, as Run

Record of how Team 2 ran the Assignment 2 cascade speed tests, for the report's method /
reproducibility section. Companion to `docs/LOAD_TEST_PLAYBOOK.md` and `docs/ACCURACY_PLAYBOOK.md`
(A1); covers only the A2 speed test (assignment brief, Step 4, "Speed test"). Test-set accuracy
scoring is P3's `analysis/a2_accuracy.py` / `a2_limits.py` and is not duplicated here.

- **SUT laptop, operated by P1.** Ran the service, MySQL and Ollama; switched configuration before
  each run.
- **Load-generator laptop, operated by P2.** Ran JMeter (`speed_test.jmx`), a separate machine from
  the SUT.
- **All 9 official runs are complete** — gemmaAlone, cascadeS1, cascadeS2, 3 runs each. Figures in
  `A2_SPEED_RUNS_SUMMARY.md` (P2); this document covers the method behind them.

---

## 1. What was tested

Per the brief (Step 4), every configuration that passed both A2 accuracy limits was speed-tested,
plus the cascade regardless of outcome:

| Configuration | What it is | Accuracy gate |
|---|---|---|
| `gemma4:e4b` alone | Top A1 model (reference) | Always speed-tested — it sets the accuracy limit |
| cascade **S1** | `phi3:3.8b` first, escalate Bank account / Credit reporting / Mortgage to `gemma4:e4b` | Always speed-tested |
| cascade **S2** | as S1, also accepts Mortgage from phi3 (escalates less) | Always speed-tested |
| mistral-7b / phi3-3.8b / llama3.2-1b alone | Other A1 candidates | **None qualified** — all three failed the test-set accuracy limits (`A2_SPEED_RUNS_SUMMARY.md` accuracy table), so no 4th configuration was speed-tested, per the brief ("single models that fail accuracy do not need a speed test") |

S1/S2 are frozen in `datasets/a2/escalation_rule.md` and implemented in `server/classifier.py` via
`CASCADE_SETTING=s1`/`s2`, `CASCADE_LARGE_MODEL=gemma4:e4b`. The memory check required before any
cascade test was done and passed: `tests/environment/a2_memcheck/memcheck.json`, verdict `PASS` —
phi3:3.8b and gemma4:e4b both stayed resident (`OLLAMA_MAX_LOADED_MODELS=2` in `docker-compose.yml`),
no reload between calls.

3 runs per configuration, same arrival rate and run length across all three, same fixed workload
ticket list and order every time.

Reported per run: p50 (mean + spread across the 3 runs), p95 pooled across all 3 runs (n ≈ 90),
throughput, error rate, and — for every cascade run — the escalation fraction from the service log.
No p99 (brief: sample too small).

---

## 2. Setting S (the arrival rate)

The rule, per the brief: restart Ollama, warm up, send three different typical-length tickets to the
top model (`gemma4:e4b`) one at a time, never repeating a ticket (Ollama caches the processed prompt
prefix, so a repeat understates real latency); take the median of the three timings as **S**, in
seconds. Arrival rate = one ticket every 2×S seconds (model idle about half the time, no queue
builds). Run length = S minutes, minimum 5. HTTP response timeout = max(10×S, 5 min). Schedule pause
= timeout + at least 1 minute.

**As measured:**

| Row | Timing |
|---|---|
| 35 | 48.7 s |
| 85 | 31.08 s |
| 27 | 29.2 s |

**S = median = 31.08 s.** Rate = 1 ticket / 2×S = 62.1 s → **58 tickets/hour**. Run length = S
minutes ≈ **1865 s window**. HTTP response timeout = 10×S ≈ **311 s**. Schedule pause = **401 s**
(> timeout + 60 s). All runs landed at 30 tickets, as the rule predicts.

**Against the A1 client peak workload** (3,936 tickets/h, `docs/LOAD_TEST_PLAYBOOK.md` section 1):
the A2 test rate (58/h) is far below it — about 1.5%. State this on the limitations slide: the speed
results compare configurations against each other but do not show the recommended configuration can
handle the client's actual peak load.

---

## 3. Workload: the fixed ticket set used

P2's `scripts/a2/build_speed_workload.py` (seed `20261117`, source `tests/stress/data/tickets.jsonl`,
golden tickets excluded) generated and committed **`datasets/a2/speed/workload_rows.csv`** — 45 fixed
non-golden tickets (order, source row, length, typical/long), of which the runs drew 30 per the rate
set in section 2 — plus **`datasets/a2/speed/warmup_tickets.jsonl`**, 3 fixed warm-up tickets chosen
by `scripts/a2/setup_speed.ps1` specifically because they **escalate under both S1 and S2** (so both
models are proven loaded before every cascade run starts). Manifest and file hashes recorded in
`datasets/a2/speed/workload_manifest.json`. Same set, same order, for every configuration and every
run.

---

## 4. `speed_test.jmx`, as built

Committed at **`tests/load/speed_test.jmx`**, adapting `tests/load/load_test.jmx`'s Open Model
Thread Group approach (no closed-loop timers) to:

- a single open model at the rate from section 2 (one steady rate per run, no ramp/mix phases);
- HTTP sampler response timeout = 10×S s (≥ 5 min), set before the schedule pause;
- schedule duration = the run length from section 2, followed by a pause ≥ timeout + 60 s;
- reads the fixed ticket list (section 3) in file order, one per arrival, no repeats within a run;
- `-Jrun_id` → `X-Run-Id` header, `-Jsample_variables=req_id`, matching `load_test.jmx`, so
  client/server records pair the way `analysis/reconcile.py` expects.

Driven by `scripts/a2/p2_run_loop.ps1`, coordinated with P1's side via `scripts/a2/control_server.py`
(a small local HTTP state machine: `IDLE` → `READY` → `DONE`) rather than the manual "P1 says READY
over chat" handoff used in A1 — the whole A2 speed matrix was run as one largely automated pipeline.

---

## 5. Per-configuration, per-run procedure (as run)

All 9 runs (gemmaAlone ×3, cascadeS1 ×3, cascadeS2 ×3, plus the excluded cascadeS1 run 99 rehearsal)
ran through `scripts/a2/p1_speed_run.ps1` (P1 side) + `scripts/a2/p2_run_loop.ps1` (P2 side) — a
purpose-built A2 pipeline, not an extension of A1's `switch_model.ps1` (which only ever loads one
model and would unload the second model the cascade needs). Per run:

**Configuration switch.** `Set-A2Config` (`scripts/a2/_a2common.ps1`) sets `OLLAMA_MODEL`,
`CASCADE_SETTING`, `CASCADE_LARGE_MODEL=gemma4:e4b`, `OLLAMA_THINK` in `.env`; restarts the Ollama
container (clears the prompt cache, confirms nothing stays resident); recreates the server; confirms
via `GET /health` that `model`/`cascade`/`think` match the requested configuration before continuing.

**Warm-up & residency check.** `prepare_run.ps1 -TestType speed` sends the 3 fixed warm-up tickets
(section 3) and, for cascade configs, requires `gemma4:e4b` to be resident (`-RequireModels`) — the
run does not proceed otherwise.

**Before/after counts.** `GET /stats` taken before and after each run; the delta is requests
completed and stored (`stats_before.json` / `stats_after.json` in each run folder).

**Run ID convention.** `<model>_<test-type>_<config>_run<n>`, model = `GET /health`'s `model` field
(the small model even in cascade mode) — e.g. `phi3-3.8b_speed_cascadeS1_run1`,
`gemma4-e4b_speed_gemmaAlone_run1`, confirmed in `runs/run_register.csv`.

**Coordination.** P1 posts `READY` with run parameters to `control_server.py`'s local state endpoint;
P2's loop picks it up, runs `speed_test.jmx`, posts `DONE` with its result; P1 polls for that instead
of a manual chat handoff.

**Finish.** `finish_run.ps1` archives `server_access.log`, DB export, Ollama log, `ollama ps` output,
`run_info.json`; `scripts/a2/run_summary.py` writes `sut_summary.json` (escalation fraction from the
service log, stats delta) per run.

**Save and reconcile (P4).** `.jtl` placed in `runs/<run-id>/`; `analysis/reconcile.py runs/<run-id>`
pairs `.jtl` samples with server log lines by `req_id`; evidence committed; `runs/run_register.csv`
updated (all 9 rows present, status `DONE`). Run 99 (cascadeS1 trial) is logged but excluded via
`analysis/excluded_runs.csv` ("trial run: pipeline check before the official A2 speed matrix... not
an official run").

---

## 6. What was reported per run (P4)

From each run's `.jtl` plus `server_access.log`:

- Requests sent, completed, errored, unfinished.
- p50 of successful requests' elapsed time, per run; mean and spread of the 3 p50s across a
  configuration; p95 pooled over all 3 runs' successful samples (≈ 90 tickets), n stated.
- Achieved throughput (completed/s) and error rate, per run.
- Cascade configs: escalation fraction (`escalated=1` lines ÷ answered `POST /tickets` lines) from
  the service log, compared against the accuracy-test escalation fraction, with any large gap
  explained (brief, Step 4) — see `A2_SPEED_RUNS_SUMMARY.md` and `P4_slide_content_draft.md` for that
  explanation.
- No-reload evidence for cascade runs: `ollama ps` snapshot at run start showing both models resident.

This feeds the trade-off chart (Slide 6) and the A2 speed section of the results analysis.
