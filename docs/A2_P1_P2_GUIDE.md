# A2 guide for P1 (Infra Lead) and P2 (Load Lead)

Source: ICT3113 Assignment 2 brief (due 2359, 27 Nov) and the team responsibility table.
Scope: the **speed test** (brief Step 4, "Speed test") and everything the SUT needs for it.
Accuracy runs are P3's job and must finish first: only configurations that pass accuracy get a speed test,
except the cascade, which is always speed-tested.

## Quick start (automated; the manual sections below explain what the scripts do)

How many tests: **9 speed runs minimum** (gemma4 alone, cascade S1, cascade S2, each x 3), **12 if mistral:7b also passes
accuracy** (A1 gave it 61/88 on the test rows, exactly the 61 needed overall, so check P3's per-category result).
phi3:3.8b (58/88) and llama3.2:1b (25/88) fail the overall limit, so no speed test for them.
Plus one-off: the S measurement (3 tickets), one dry run. Each run is about S + pause minutes (about 40 min if S is about 33 s).

| Step | Who | Command (repo root) |
|---|---|---|
| 1. Build the fixed workload, S tickets, warm-up candidates | P2 | `python scripts\a2\build_speed_workload.py` then commit `datasets\a2\speed\` and push |
| 2. Pick 3 warm-ups, measure S, set rate/length/timeout/pause | P1 | `powershell -ExecutionPolicy Bypass -File scripts\a2\setup_speed.ps1`, then commit `datasets\a2\speed\` |
| 3. Commit and push all scripts (`prepare_run.ps1` refuses a dirty tree) | both | `git add scripts tests datasets docs; git commit; git push` |
| 4. Start the whole matrix | P1 | `powershell -ExecutionPolicy Bypass -File scripts\a2\p1_run_all.ps1` (add `-Configs gemmaAlone,cascadeS1,cascadeS2,mistralAlone` for 12 runs; `-PlanOnly` to preview) |
| 5. Drive JMeter on the other laptop | P2 | `powershell -ExecutionPolicy Bypass -File scripts\a2\p2_run_loop.ps1 -ControlUrl http://<P1-IP>:8099` (P1's script prints its IP) |
| 6. Commit the `runs\` folders (P1 and P2 each push theirs) and hand over to P4 | both | |

What the scripts do per run: switch configuration, restart Ollama, recreate the server, send the 3 fixed warm-ups, require the
right models in `ollama ps` (both for a cascade) and CPU only, reset log and DB, GET /stats, tell P2 READY; P2 checks the SUT
/health matches, runs `tests\load\speed_test.jmx`, saves the `.jtl`, reports DONE; P1 then GET /stats, archives everything and
writes `sut_summary.json` (escalation fraction from the log); P2 writes `client_summary.json` (sent, ok, errors, p50).
The same `random_seed` is used for run N in every configuration, so arrival times match across configurations.
If a run fails: delete its partial `runs\<id>` folder on both laptops, restart `p1_run_all.ps1` (finished runs are skipped).
One-off firewall rule on P1's laptop if P2 cannot connect: `New-NetFirewallRule -DisplayName 'A2 control' -Direction Inbound -Protocol TCP -LocalPort 8099 -Action Allow` (admin).

Tested here: workload builder, JMX, P2 loop with real JMeter against a fake SUT, summary parser. **Not tested here** (needs the
real SUT): `setup_speed.ps1`, `p1_speed_run.ps1`, `p1_run_all.ps1`, and the edited `prepare_run.ps1`. Do one short trial first.

## Gemma thinking vs non-thinking (added)

Configurations: `gemmaAlone` (thinking, as in A1: the **reference** that sets the limits) and `gemmaNoThink` (same model and
digest, `think=false`). Optional cascade variants `cascadeS1NoThink` / `cascadeS2NoThink` make only gemma4 non-thinking
(the service sends the flag to gemma4 only). A1's note measured about 22 s thinking vs 0.6 s non-thinking on one ticket.

**Ask the lecturer first.** The brief fixes the models, prompt and "Ollama inference settings (thread count, parallelism,
context length)" and says to ask before measuring if unsure. `think` is not in that list, but it changes how the model runs,
so get a yes in writing and say so on slide 3. Also keep the limits tied to the thinking-on reference, and report both rows.

Order:
1. Team fills in and commits `datasets/a2/A2PredictionAddendum_thinking.md` (it must precede the thinking-off runs).
2. Accuracy first, about 2 minutes for non-thinking:
   `powershell -ExecutionPolicy Bypass -File scripts\a2\accuracy_run.ps1 -Config gemmaNoThink -Run 1`
   (the same script runs the cascades: `-Config cascadeS1`, `-Config cascadeS2`; output `runs\..._accuracy_a2test88-<Config>_run<N>`).
3. If gemmaNoThink passes both limits (>= 61/88 overall and every per-category limit), add it to the speed matrix:
   `p1_run_all.ps1 -Configs gemmaAlone,gemmaNoThink,cascadeS1,cascadeS2` (P2's command is unchanged).
4. Test count becomes 12 speed runs (15 with mistral). The no-think runs use the same rate and run length, so they take as
   long as the others even though gemma answers in about a second.

**Decision (team): the matrix now includes the cascades with gemma thinking off.** Default `p1_run_all.ps1` runs six
configurations x 3 runs = **18 speed runs** (about 12 hours): gemmaAlone, gemmaNoThink, cascadeS1, cascadeS2,
cascadeS1NoThink, cascadeS2NoThink. The brief requires only the first, third and fourth (9 runs). Each thinking-off
configuration is speed-tested only if it passes accuracy (cascades are always speed-tested). Run the accuracy script for every
one first: `accuracy_run.ps1 -Config cascadeS1NoThink` etc. Fill the addendum rows for the two new cascades before running.

## 0. Where the repo already is

| Item | State | Evidence |
|---|---|---|
| Golden split (odd = tuning, even = test) | done, committed | `datasets/a2/split_summary.md` |
| Escalation rule, settings S1 and S2 | written, committed | `datasets/a2/escalation_rule.md` |
| Cascade inside `POST /tickets`, log fields `escalated`, `final_model` | done | `server/classifier.py`, rule doc "What the service log records" |
| Memory check (phi3:3.8b + gemma4:e4b both resident) | PASS | `tests/environment/a2_memcheck/ollama_ps.txt` |
| `OLLAMA_MAX_LOADED_MODELS=2`, `NUM_PARALLEL=1`, `KEEP_ALIVE=-1` | in compose | `docker-compose.yml` |
| Prediction record | committed before any benchmark | commit `10fe162` |
| **Speed workload row list** | **missing** | P2, section 2 |
| **S measurement, rate, run length** | **missing** | P1 + P2, section 3 |
| **`speed_test.jmx`** | **missing** (only `tests/load/load_test.jmx` from A1) | P2, section 4 |
| **3 fixed warm-up tickets** | **missing** (scripts use one invented sentence) | P1 + P2, section 2 |
| Load-generator environment | staged, not committed; it records "TCP connect to SUT: False" | re-record, section 4 |

Models: top model = **gemma4:e4b**, small = **phi3:3.8b**. Cascade S1 = cautious, S2 = faster.
Configurations to speed-test: gemma4 alone, cascade S1, cascade S2, plus any other single model P3 reports as
passing both limits (probably phi3:3.8b alone, maybe mistral:7b). Wait for P3's accuracy table before deciding.

## 1. Order of work

1. P3 commits accuracy results for all four single models and both cascade settings (test set).
2. P2 picks and commits the workload and warm-up row numbers (section 2).
3. P1 and P2 measure S together on gemma4 (section 3). Commit S, the rate and the run length.
4. P2 builds and dry-runs `speed_test.jmx` (section 4). P1 patches the run scripts (section 5).
5. Commit everything above. `prepare_run.ps1` refuses to start if code outside `runs/` and `tests/environment/` is dirty.
6. Run 3 x each configuration (section 6), archive, and hand the `.jtl` files and logs to P4.

Time budget: each run is about S minutes (about 34 if S is about 33 s, per the A1 gemma figure) plus restart, warm-up and
drain. Three configurations x 3 runs is about 9 runs, so roughly 6 to 8 hours of test time. Start early.

## 2. Workload and warm-up tickets (P2 owns, P1 reviews)

- Take tickets from dataset rows **outside the golden set** (A1 load rows 2000 to 2999 are fine). Never use a golden row.
- **Workload:** about 30 fixed tickets, in one fixed order, mix of typical and long. Same list for every configuration.
  Commit the row numbers (for example `datasets/a2/speed_workload_rows.txt`) and the generated `tickets.jsonl`.
  Build the file in that exact order with `load-generator/prepare_data.py` (or a small script that takes the row list).
- **Warm-up:** three fixed tickets, not in the workload, same three every run. For the cascade they must reach gemma4:
  choose tickets whose **phi3 answer is Bank account or service, Credit reporting or Mortgage** (outside S1/S2's accept list),
  so both models load. Check by sending each one and reading `escalated=1` in the log. Under S1 all three escalate if phi3
  says Bank account or Credit reporting; under S2 Mortgage is accepted, so do not rely on a Mortgage ticket.
  At least one warm-up must escalate under **both** settings.
- Reminder from the brief: never send the same ticket three times to measure S, because Ollama caches seen prompts.

## 3. Measuring S, the rate and the run length (P1 and P2, once)

1. P1 restarts the Ollama container and sends the usual warm-up (gemma4 alone, `CASCADE_SETTING=off`).
2. Send **three different typical-length tickets**, one at a time, to gemma4 alone. Note the three times and the three row numbers.
3. **S = the middle time** in seconds.
4. Arrival rate = **1 ticket every 2S seconds**. Run length = **S minutes, minimum 5**. About 30 tickets per run.
5. Response timeout = **max(10 x S seconds, 300 s)**. Schedule pause = timeout + **at least 60 s**.
6. Record S, the three timings, the three rows, the rate, the run length, and compare the rate with the A1 client peak
   (3,936 tickets/hour in the A1 workload model, about 65 per minute). The A2 rate will be far below it, so the limitations slide must say the
   test compares configurations and does **not** show the system handles the client peak. P5 writes that.

Worked example (made-up S = 33): rate 1 per 66 s (about 0.91/min), run 33 min, timeout 330 s, pause 390 s or more.
Use the same values for every configuration, including the single models.

## 4. P2: JMeter plan and load-generator machine

Create `tests/load/speed_test.jmx` (copy `load_test.jmx`, keep the CSV data set, header manager and `X-Run-Id` / `X-Request-ID` capture).

- One **Open Model Thread Group** with POST /tickets only. No searches.
- Schedule, as in the brief: `rate(<N>/min) random_arrivals(<S> min) pause(<pause> sec)`. With a rate below 1/min use
  `/hour` (for example 55/hour) so it stays exact.
- Response timeout `<10xS>` s, at least 300 s. **The pause must be longer than the timeout by at least a minute**, or JMeter
  kills the slow requests, which are the ones you most need.
- Parameterise rate, duration, timeout and pause with `-J` properties so the committed plan is the same for every config.
- CSV data set: the committed workload file, read in order, one cursor, every run starts from line 1.
- Write `<run-id>.jtl` with `req_id` saved, as in the A1 plan.
- Dry-run against a dead port first (the A1 playbook section 3.3 shows how) to confirm about 30 requests, correct order,
  no searches.
- The load generator stays on **its own laptop**, separate from the SUT. Re-run `scripts/record_loadgen_environment.ps1`
  with the SUT up (the staged copy says TCP connect False and /health timed out), then commit the record.

Per run, P2 writes down: GET /stats total before and after (the difference = completed and stored), and from the `.jtl`
requests sent, completed, errored, unfinished. A run with unfinished requests is reported, not discarded.
Do not compute p99. P4 computes p50 per run and pooled p95 from the three `.jtl` files.

## 5. P1: SUT settings, scripts and checks

Before the first run:
- Freeze Ollama settings (already in compose: version 0.34.4, `MAX_LOADED_MODELS=2`, `NUM_PARALLEL=1`, `KEEP_ALIVE=-1`).
  Do not touch them between configurations. Re-run `scripts/p1/record_environment.ps1` and `pin_models.ps1` (already pinned) and
  commit. Before each configuration, check the digests and settings are unchanged.
- Only the server env changes between configurations:

| Configuration | `OLLAMA_MODEL` | `CASCADE_SETTING` | `CASCADE_LARGE_MODEL` |
|---|---|---|---|
| gemma4 alone | gemma4:e4b | off | n/a |
| phi3 alone (if it passes) | phi3:3.8b | off | n/a |
| Cascade S1 | phi3:3.8b | s1 | gemma4:e4b |
| Cascade S2 | phi3:3.8b | s2 | gemma4:e4b |

Script gaps to fix before official runs (I read the scripts but have not run them; verify each):
1. `prepare_run.ps1` sends **one** invented sentence `-WarmupCount` times. The brief wants three fixed, different tickets, and for the
   cascade ones that escalate. Add a `-WarmupFile` option reading the three committed warm-up tickets.
2. It checks only `$health.model` is loaded and warns if more than one model is resident. For the cascade it must **require both**
   models in `ollama ps` and `size_vram = 0`, and stop if either is missing.
3. The run id uses the small model name only, so cascade runs would be named `phi3-3.8b_...`. Put the setting in `-Config`
   (for example `cascadeS1`, `gemmaAlone`) and use the `load` test type, or add a `speed` test type.
4. It does not restart the Ollama container (check; I saw no restart in the script). The brief requires a restart before every run, to clear the prompt cache.
   Do `docker compose restart ollama`, wait for healthy, then run `prepare_run.ps1`.
5. `switch_model.ps1` unloads every model that is not the one requested. For a cascade, do not unload gemma4 afterwards;
   simplest is to restart Ollama, then let warm-up load both.

Every run, in this order (P1 does 1 to 5 and 8 to 10; P2 does 7):
1. Switch configuration (table above), check digests and settings unchanged.
2. Restart the Ollama container, wait for `/health`.
3. Send the 3 warm-up tickets, one at a time. Discard their timings.
4. `ollama ps` in the container: confirm the right models are resident (both, for the cascade), CPU only. Save as `ollama_ps_before`.
5. `GET /stats`, note the total. Tell P2 READY.
6. (Nothing else may hit the SUT until the run ends.)
7. P2 runs JMeter. Wait for the end of the schedule **and** the pause.
8. `GET /stats` again. The increase is the completed count.
9. `finish_run.ps1 -RunId <id>` archives `server_access.log`, `ollama.log`, `ollama_ps_after`, `tickets.tsv`.
10. Copy P2's `.jtl` into the same `runs/<run-id>/` folder. For the cascade, count `escalated=1` lines in `server_access.log`
    to get the escalation fraction under load. Flag it to P4 if it differs a lot from P3's accuracy-run fraction.

Do **not**: restart the laptop or change power mode mid-set (keep AC and Best performance), reuse A1 speed numbers,
cache classifications, or change thread or parallelism settings.

## 6. Run matrix (fill in as you go)

| Configuration | Run 1 | Run 2 | Run 3 | Notes |
|---|---|---|---|---|
| gemma4 alone | | | | the reference, always run |
| Cascade S1 | | | | always run, even if it fails accuracy |
| Cascade S2 | | | | always run, even if it fails accuracy |
| phi3 alone | | | | only if P3 says it passes both limits |
| mistral alone | | | | only if P3 says it passes both limits |

Run order: interleave rather than all of one config at once, for example gemma, S1, S2, then repeat, so a slow drift
in laptop temperature or background load does not bias one configuration. Record any thermal throttling in `-Notes`.

## 7. Hand-off to P4 and P5

- P4 receives: all `.jtl`, server logs, S, rate, run length, the stats before and after for each run.
- P5 receives: the test rate versus the A1 client peak, the environment records, and any deviation from A1 for slide 3 and slide 8.
- Slide 3 content (P1 and P2): machines, rate and why, the workload tickets, warm-up and drain procedure, changes from A1
  (Ollama 0.34.4, `MAX_LOADED_MODELS=2`, gemma4 thinking left as in A1).
