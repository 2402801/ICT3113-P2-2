# Accuracy Test Playbook (Step 5)

How Team 2 measured each candidate model's overall and per-category classification accuracy on the frozen golden
test set, in enough detail to repeat it. 16 runs were made on 7–8 Oct 2026 (4 models, 3 counted runs each, plus
4 excluded runs that are kept as evidence).

- **Operated by P3**, on P3's two machines: `DESKTOP-M4H382A` for gemma4:e4b and `LAPTOP-LVH7E9IH` for the other
  three models. The service, MySQL and Ollama ran in Docker on the same machine as the test client. These are
  **not** the official SUT laptop (see section 9).
- Commands are Windows PowerShell 5.1 and run from the repository root. Paths are relative to the repository root.
  Times are UTC.

Related playbooks: `docs/stress-test-playbook.md` (stress test) and `docs/LOAD_TEST_PLAYBOOK.md` (load tests).

---

## 1. What is tested

| Item | Value |
|---|---|
| Golden set | `datasets/golden_test_set.csv`: 175 tickets with final team labels, 21–35 per category, frozen at commit `0630ef5` (2026-09-16), before any model saw them |
| Models | `llama3.2:1b`, `phi3:3.8b`, `mistral:7b`, `gemma4:e4b`, each pinned by digest in `tests/environment/model_pins.json` |
| Service settings (identical for every model) | prompt v1 (`server/prompt.py`), `temperature 0`, `seed 42`, JSON-schema output restricted to the 7 categories, `think` left at the model default |
| Traffic | Each golden ticket sent once per run to `POST /tickets`, one at a time, outside any load run |
| Runs | 3 complete runs per model (section 8.2 explains why one run is not enough) |

**Requirements checked** (Step 4):

| Requirement | Pass condition |
|---|---|
| AR-1 | Per-category accuracy ≥ 75% for each of Debt collection, Credit reporting, Money transfer or service |
| AR-2 | Per-category accuracy ≥ 90% for each of Mortgage, Consumer loan, Credit card, Bank account or service |
| AR-3 | Overall accuracy ≥ 85% |

**Run ID** = `<model>_accuracy_golden175_run<n>`, with the `:` in the model tag written as `-`. For example,
`gemma4-e4b_accuracy_golden175_run1`. A run ID is never reused.

---

## 2. Environment and files

| | Value |
|---|---|
| Machines | `DESKTOP-M4H382A` (gemma4:e4b) and `LAPTOP-LVH7E9IH` (llama3.2:1b, phi3:3.8b, mistral:7b), recorded per run in `runs/<run-id>/<run-id>_accuracy.meta.json` |
| Software | Docker Desktop: `server`, `mysql`, `ollama/ollama:0.34.4`, started with `docker compose up -d`; Python 3.10+ |
| Inference | CPU only: `ollama_ps_before.*` and `ollama_ps_after.*` in every run folder show `100% CPU`, `size_vram = 0` |
| Client target | `http://127.0.0.1:8000` (client and service on the same machine) |

| File | Role |
|---|---|
| `scripts/run_accuracy_suite.ps1` | Runs the whole test unattended (section 4) |
| `scripts/p1/switch_model.ps1`, `prepare_run.ps1`, `finish_run.ps1` | Per-model and per-run SUT steps, called by the suite |
| `tests/accuracy/accuracy_test.py` | Client: sends each golden ticket to `POST /tickets` and records the answer |
| `analysis/reconcile.py` | Checks each run's client record against the service's own logs (section 6) |
| `tests/accuracy/accuracy_report.py` | Scores the runs: overall and per-category accuracy, precision, confusion matrices (section 7) |
| `tests/accuracy/accuracy_figures.py` | Draws the figures in `analysis/output/figures/` |
| `analysis/requirements_matrix.py` | Turns the scores into AR-1 / AR-2 / AR-3 verdicts |
| `analysis/excluded_runs.csv` | Runs that were invalidated, with the reason (section 5) |

---

## 3. Preconditions

1. Docker Desktop running; the stack up: `docker compose up -d`.
2. The **Windows** Ollama app is **not** running (it takes port 11434 from the Docker Ollama). Quit it from the tray
   and disable it under Task Manager > Startup apps.
3. The model under test is pulled into the **Docker** Ollama and matches its pin:
   `docker compose exec ollama ollama list` shows the pinned ID (for example gemma4:e4b = `c6eb396dbd59`).
   A tag can be re-pushed upstream with a different build: if the ID differs, do not run; obtain the pinned build.
4. `git` is on PATH and the working tree is clean outside `runs/`, `tests/environment/` and `analysis/output/`.
5. `powershell -ExecutionPolicy Bypass -File scripts\p1\preflight.ps1` shows no FAIL for the model under test
   (missing *other* candidates can be ignored).
6. AC power, Windows power mode **Best performance**, sleep disabled.
7. Optional: block inbound port 8000 so no other machine can add requests to the run (admin PowerShell):
   `New-NetFirewallRule -DisplayName 'Block API 8000 (accuracy runs)' -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Block`

Time needed for one run (175 tickets), measured from READY to DONE in `runs/run_register.csv`:

| Model | One run |
|---|---|
| llama3.2:1b | 9–10 min |
| phi3:3.8b | 21–24 min |
| mistral:7b | 37–40 min |
| gemma4:e4b | 1 h 44 min – 1 h 46 min |

---

## 4. Procedure

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_accuracy_suite.ps1 -Tester P3 -Models <model-tag>
```

Without `-Models` the suite runs all four models; without `-Runs` it runs 1, 2, 3. For each model, the suite runs
these steps; nothing needs to be typed between them:

1. **Switch model** (`scripts/p1/switch_model.ps1`): sets the model, unloads all others, restarts the service and
   checks `GET /health` reports the model.
2. **For each of runs 1, 2, 3:**
   1. **Prepare** (`scripts/p1/prepare_run.ps1 -TestType accuracy -Config golden175`): checks the digest pin and
      clean git; sends one fixed, unmeasured warm-up ticket; checks the model is resident with `size_vram = 0`
      (CPU only); restarts the service with an empty access log; empties the database; writes
      `runs/<run-id>/run_info.json` and marks the run READY in `runs/run_register.csv`.
   2. **Send the golden set** (`tests/accuracy/accuracy_test.py`): posts all 175 golden tickets to
      `http://127.0.0.1:8000/tickets`, **one at a time** (the next ticket is sent only after the previous answer
      arrives), with a 900 s client timeout and the header `X-Run-Id: <run-id>`. For every ticket it records the
      golden label, returned category, HTTP status and the service's `req_id` in
      `runs/<run-id>/<run-id>_accuracy.csv`. Tickets that get no HTTP answer are retried once automatically.
   3. **Finish** (`scripts/p1/finish_run.ps1`): archives `server_access.log`, `ollama.log`, the database rows
      (`tickets.tsv`, `request_metrics.tsv`) and `ollama ps` into `runs/<run-id>/`; marks the run DONE.
3. **Reconcile and report** for the runs just completed (sections 6 and 7).

Then commit the `runs/` folders, so every reported number stays traceable.

---

## 5. Invalid runs and exclusions

- If the suite stops (crash, Ctrl+C, reboot), re-run the same command. Finished runs are skipped; an unfinished run
  resumes from the next unanswered ticket.
- **Do not pull, switch branches or restore stashes while a run is in progress.** Git tools can move or replace the
  run's files mid-run.
- A run counts only if it ran **uninterrupted from prepare to finish**, every ticket was answered by the model
  (no failure of the environment), and reconciliation (section 6) passes.
- An invalid run is **never deleted**: add it to `analysis/excluded_runs.csv` with the reason, commit, and run a
  replacement with the next free number, e.g. `-Runs 4`.

Runs excluded from the results. All four folders are kept in `runs/`:

| Excluded run | Reason | Replaced by |
|---|---|---|
| `gemma4-e4b_accuracy_golden175_run2` | Interrupted and resumed (4 client sessions); the result CSV was overwritten during a GitHub Desktop stash restore, so 8 logged requests (server ticket IDs 85–91, 94) have no matching client row. Reconciliation FAIL | `..._run4` |
| `phi3-3.8b_accuracy_golden175_run1` | Environment failure: 1 of 175 requests returned 502 (Ollama HTTP 500, "model runner has unexpectedly stopped") | `..._run4` |
| `phi3-3.8b_accuracy_golden175_run2` | Same failure, 1 of 175 requests | `..._run5` |
| `phi3-3.8b_accuracy_golden175_run3` | Same failure, 2 of 175 requests | `..._run6` |

The phi3 runs 1–3 were replaced, not scored, because the 502s came from the Ollama runner crashing and not from
the model's answer. On every ticket they did answer (174, 174 and 173 of 175), they gave the same category as
runs 4–6. Scored as they stand they would be 72.6%, 73.1% and 72.0%.

---

## 6. Reconciliation

```powershell
cd analysis
python reconcile.py        # no arguments = every finished run; writes analysis/output/reconciliation.csv
```

For each run it matches every `POST /tickets` in `server_access.log` to a client row by `req_id`, and checks that
HTTP status and category agree and that `tickets.tsv` matches the log. Any request in the log without a client row
(or the reverse) is a FAIL. Runs listed in `excluded_runs.csv` are reported but do not count as failures.

**Result:** all 12 counted runs are PASS: 175 client rows pair with 175 logged `POST /tickets`, and 175 tickets are
stored. Of the excluded runs, gemma4 run 2 is FAIL (8 server requests with no client row), phi3 run 1 is WARN and
phi3 runs 2–3 are PASS.

---

## 7. Analysis

```powershell
cd analysis
python ..\tests\accuracy\accuracy_report.py <run IDs of every counted accuracy run>
python requirements_matrix.py
```

`accuracy_report.py` writes `analysis/output/accuracy_report.md` plus CSVs (`accuracy_runs.csv`,
`accuracy_summary.csv`, `accuracy_pairwise.csv`, `confusion_matrices.csv`, `accuracy_predictions.csv`).
`requirements_matrix.py` reads `accuracy_runs.csv` and writes the AR verdicts to
`analysis/output/requirements_matrix.md`.

- A ticket is **correct** when the returned category equals its golden label. A ticket with no category
  (5xx / timeout) is **incorrect**.
- **Per-category accuracy** = correct / golden tickets in that category (recall). Precision is also reported.
- Each model's figures are the **mean ± SD across its 3 runs**, with a 95% bootstrap confidence interval over the
  golden tickets (2000 resamples, fixed seed 2113, so the report is reproducible).
- **Confusion matrix**: rows = golden label, columns = model's answer, summed over the model's runs.
- **Run-to-run agreement** = tickets that got the same answer in all 3 runs.
- **Pairwise comparison**: exact McNemar test on the tickets where two models disagree, Holm-adjusted.
- **Verdicts** are judged strictly on the mean of the counted runs, as the requirements are written.

---

## 8. Results

Runs counted: llama3.2:1b 1–3, mistral:7b 1–3, phi3:3.8b 4–6, gemma4:e4b 1, 3, 4.

### 8.1 Overall accuracy and verdicts

| Model | Overall (mean ± SD) | 95% CI | Run-to-run agreement | AR-1 | AR-2 | AR-3 (≥ 85%) |
|---|---|---|---|---|---|---|
| gemma4:e4b | 84.4% ± 0.3 | 79.0–89.3% | 161/175 | **Not met** | **Not met** | **Not met** |
| mistral:7b | 73.1% ± 0.0 | 66.9–79.4% | 175/175 | **Not met** | **Not met** | **Not met** |
| phi3:3.8b | 73.1% ± 0.0 | 66.9–80.0% | 175/175 | **Not met** | **Not met** | **Not met** |
| llama3.2:1b | 34.9% ± 0.0 | 28.0–41.7% | 175/175 | **Not met** | **Not met** | **Not met** |

**No candidate meets AR-1, AR-2 or AR-3.** gemma4:e4b's 84.4% is a fail against 85% even though its confidence
interval reaches 85%.

Per-category accuracy (mean of the counted runs). **Bold** = below the bar:

| Category (golden n) | Bar | llama3.2:1b | phi3:3.8b | mistral:7b | gemma4:e4b |
|---|---|---|---|---|---|
| Debt collection (22) | 75% (AR-1) | 81.8% | **50.0%** | 86.4% | 77.3% |
| Credit reporting (35) | 75% (AR-1) | **71.4%** | 85.7% | 82.9% | 87.6% |
| Money transfer or service (24) | 75% (AR-1) | **0.0%** | **50.0%** | **33.3%** | **70.8%** |
| Mortgage (21) | 90% (AR-2) | **42.9%** | 100.0% | 100.0% | 100.0% |
| Consumer loan (23) | 90% (AR-2) | **8.7%** | **73.9%** | **65.2%** | 92.8% |
| Credit card (24) | 90% (AR-2) | **0.0%** | **58.3%** | **75.0%** | **63.9%** |
| Bank account or service (26) | 90% (AR-2) | **26.9%** | **88.5%** | **69.2%** | 97.4% |

Weakest categories: gemma4:e4b credit card (64%) and money transfer (71%), mostly misrouted to Bank account or
service; mistral:7b money transfer (33%); phi3:3.8b debt collection and money transfer (50%); llama3.2:1b credit card
and money transfer (0%), mostly answered as Credit reporting or Debt collection.

gemma4:e4b is significantly more accurate than each other model (Holm-adjusted p ≤ 0.0016). mistral:7b and
phi3:3.8b cannot be told apart (p = 1.00).

Confusion matrices, precision and the full pairwise table are in `analysis/output/accuracy_report.md`.

### 8.2 Run-to-run variation (why three runs)

With `temperature 0` and a fixed seed we expected identical answers on every run, which would make a single pass
sufficient. That held for llama3.2:1b, phi3:3.8b and mistral:7b (175/175 tickets identical across 3 runs).
**gemma4:e4b gave the same answer in all 3 runs for only 161/175 tickets (8.0% varied).**

Likely cause (not verified): gemma4:e4b generates hundreds of reasoning tokens before its answer, while the other
models emit only the short JSON answer. Multi-threaded CPU inference sums floating-point values in a non-fixed
order, so results can differ in the last bits. Over a long reasoning chain one different token changes the rest of
the reasoning and sometimes the category. A single run is therefore one sample, so every model is measured with
3 runs and reported as mean ± SD.

---

## 9. Limitations

- **Not run on the official SUT.** The runs were made on P3's two machines, with the client on the same machine as
  the service. This does not affect which category a model returns: 50 golden tickets were also classified on the
  official SUT during load, stress and smoke runs (310 answers), and every answer matched the category from the
  counted accuracy runs (`analysis/output/requirements_matrix.md`).
- **Latency from these runs is not a result.** The per-ticket times are **not** used as latency results. Latency
  comes from the JMeter load tests.
- **No environment record for P3's machines.** Their hardware is not recorded in `tests/environment/`, and
  `runs/run_register.csv` shows power mode `unknown` for every accuracy run (AC power: yes).
- **Small categories.** The golden set has 21–35 tickets per category, so per-category confidence intervals are
  wide.
- **gemma4:e4b varies between runs** (section 8.2), so its figures are a mean of 3 samples.

---

## 10. Evidence

| What | Where |
|---|---|
| Client record per run: golden label, answer, status, `req_id` | `runs/<run-id>/<run-id>_accuracy.csv` |
| Client machine, golden-set SHA-256, sessions | `runs/<run-id>/<run-id>_accuracy.meta.json` |
| Server side per run | `runs/<run-id>/server_access.log`, `tickets.tsv`, `request_metrics.tsv`, `ollama.log` |
| Model, digest, commit, READY time; CPU-only proof | `runs/<run-id>/run_info.json`; `ollama_ps_before.*`, `ollama_ps_after.*` |
| Index of all runs | `runs/run_register.csv` |
| Excluded runs and reasons | `analysis/excluded_runs.csv` |
| Reconciliation result | `analysis/output/reconciliation.csv` |
| Scores, confusion matrices, CIs, McNemar | `analysis/output/accuracy_report.md` and the CSVs beside it |
| Figures | `analysis/output/figures/` |
| Requirement verdicts | `analysis/output/requirements_matrix.md` |
