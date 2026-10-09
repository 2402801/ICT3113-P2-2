# Accuracy Test Playbook

Measures each candidate model's overall and per-category classification accuracy on the frozen golden test set,
with a confusion matrix, and checks the results against the accuracy requirements. Everything below runs on
Windows PowerShell 5.1 from the repository root.

## 1. What is tested

| Item | Value |
| --- | --- |
| Golden set | `datasets/golden_test_set.csv`: 175 tickets with final team labels, frozen at commit `0630ef5` (2026-09-16), before any model saw them |
| Models | llama3.2:1b, phi3:3.8b, mistral:7b, gemma4:e4b, each pinned by digest in `docs/environment/model_pins.json` |
| Service settings (identical for every model) | prompt v1 (`server/prompt.py`), `temperature 0`, `seed 42`, JSON-schema output restricted to the 7 categories, `think` left at the model default |
| Requirements checked | AR-3: overall accuracy >= 85%. `[add the per-category requirement from Slide 4]` |
| Runs | 3 complete runs per model |

## 2. Files

| File | Role |
| --- | --- |
| `scripts/run_accuracy_suite.ps1` | Runs the whole test unattended (sections 4-5) |
| `accuracy/accuracy_test.py` | Client: sends each golden ticket to `POST /tickets` and records the answer |
| `accuracy/accuracy_report.py` | Scores the runs: overall and per-category accuracy, precision, confusion matrices |
| `analysis/reconcile.py` | Checks each run's client record against the service's own logs |
| `analysis/excluded_runs.csv` | Runs that were invalidated, with the reason |

## 3. Preconditions

1. Docker Desktop running; the stack up: `docker compose up -d`.
2. The **Windows** Ollama app is **not** running (it takes port 11434 from the Docker Ollama). Quit it from the tray
   and disable it under Task Manager > Startup apps.
3. The model under test is pulled into the **Docker** Ollama and matches its pin:
   `docker compose exec ollama ollama list` shows the pinned ID (for example gemma4:e4b = `c6eb396dbd59`).
   A tag can be re-pushed upstream with a different build: if the ID differs, do not run; obtain the pinned build.
4. `git` is on PATH and the working tree is clean outside `runs/`, `docs/environment/` and `analysis/output/`.
5. `powershell -ExecutionPolicy Bypass -File scripts\p1\preflight.ps1` shows no FAIL for the model under test
   (missing *other* candidates can be ignored).
6. AC power, Windows power mode **Best performance**, sleep disabled. One run (175 tickets) takes roughly
   8 min (llama3.2:1b), 20 min (phi3:3.8b), 35 min (mistral:7b) and 1 h 45 min (gemma4:e4b) on our hardware.
7. Optional: block inbound port 8000 so no other machine can add requests to the run (admin PowerShell):
   `New-NetFirewallRule -DisplayName 'Block API 8000 (accuracy runs)' -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Block`

## 4. Procedure

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_accuracy_suite.ps1 -Tester <P1..P5> -Models <model-tag>
```

For each model, the suite runs these steps; nothing needs to be typed between them:

1. **Switch model** (`scripts/p1/switch_model.ps1`): sets the model, unloads all others, restarts the service and
   checks `GET /health` reports the model.
2. **For each of runs 1, 2, 3:**
   1. **Prepare** (`scripts/p1/prepare_run.ps1 -TestType accuracy -Config golden175`): checks the digest pin and
      clean git; sends one fixed, unmeasured warm-up ticket; checks the model is resident with `size_vram = 0`
      (CPU only); restarts the service with an empty access log; empties the database; writes
      `runs/<run-id>/run_info.json` and marks the run READY in `runs/run_register.csv`.
   2. **Send the golden set** (`accuracy/accuracy_test.py`): posts all 175 golden tickets to
      `http://127.0.0.1:8000/tickets`, **one at a time** (the next ticket is sent only after the previous answer
      arrives), with a 900 s client timeout and the header `X-Run-Id: <run-id>`. For every ticket it records the
      golden label, returned category, HTTP status and the service's `req_id` in
      `runs/<run-id>/<run-id>_accuracy.csv`. Tickets that get no HTTP answer are retried once automatically.
   3. **Finish** (`scripts/p1/finish_run.ps1`): archives `server_access.log`, `ollama.log`, the database rows
      (`tickets.tsv`, `request_metrics.tsv`) and `ollama ps` into `runs/<run-id>/`; marks the run DONE.
3. **Reconcile and report** for the runs just completed.

Run IDs follow `<model>_accuracy_golden175_run<n>`, with `:` written as `-` (for example
`gemma4-e4b_accuracy_golden175_run1`). A run ID is never reused.

## 5. Interruptions and invalid runs

- If the suite stops (crash, Ctrl+C, reboot), re-run the same command. Finished runs are skipped; an unfinished run
  resumes from the next unanswered ticket.
- **Do not pull, switch branches or restore stashes while a run is in progress.** Git tools can move or replace the
  run's files mid-run.
- A run counts only if it ran **uninterrupted from prepare to finish** and reconciliation (section 6) passes.
  An interrupted or failed run is **never deleted**: add it to `analysis/excluded_runs.csv` with the reason, commit,
  and run a replacement with the next number, e.g. `-Runs 4`.
  Example: `gemma4-e4b_accuracy_golden175_run2` was interrupted and resumed, leaving 8 logged requests with no
  matching client row; it is excluded and replaced by run 4.

## 6. Reconciliation

```powershell
cd analysis
python reconcile.py        # no arguments = every finished run; writes analysis/output/reconciliation.csv
```

For each run it matches every `POST /tickets` in `server_access.log` to a client row by `req_id`, and checks that
HTTP status and category agree and that `tickets.tsv` matches the log. Any request in the log without a client row
(or the reverse) is a FAIL. Runs listed in `excluded_runs.csv` are reported but do not count as failures.

## 7. Scoring and reporting

```powershell
python ..\accuracy\accuracy_report.py <run IDs of every counted accuracy run>
```

Writes `analysis/output/accuracy_report.md` plus CSVs (`confusion_matrices.csv`, `accuracy_summary.csv`, ...).

- A ticket is **correct** when the returned category equals its golden label. A ticket with no category
  (5xx / timeout) is **incorrect**.
- **Per-category accuracy** = correct / golden tickets in that category (recall). Precision is also reported.
- Each model's figures are the **mean +- SD across its 3 runs**, with a 95% bootstrap confidence interval over the
  golden tickets (2000 resamples, fixed seed 2113, so the report is reproducible).
- **Confusion matrix**: rows = golden label, columns = model's answer, summed over the model's runs.
- **Run-to-run agreement** = tickets that got the same answer in all 3 runs.

## 8. Why three runs

With `temperature 0` and a fixed seed we expected identical answers on every run, which would make a single pass
sufficient. That held for llama3.2:1b, phi3:3.8b and mistral:7b (175/175 tickets identical across 3 runs).
**gemma4:e4b gave the same answer in all 3 runs for only 161/175 tickets (8.0% varied).**

Potentential Cause: gemma4:e4b generates hundreds of reasoning tokens before its answer, while the other models emit only the
short JSON answer. Multi-threaded CPU inference sums floating-point values in a non-fixed order, so results can differ
in the last bits. Over a long reasoning chain one different token changes the rest of the reasoning and sometimes the
category. A single run is therefore one sample, so every model is measured with 3 runs and reported as mean +- SD.

## 9. Limitations

- The client ran on the same machine as the service. This does not affect which category a model returns, but the
  per-ticket times in these runs are **not** used as latency results Latency should come from the JMeter load tests.
- The golden set has 21-35 tickets per category, so per-category confidence intervals are wide.

## 10. Baseline results (runs counted: llama3.2:1b 1-3, mistral:7b 1-3, phi3:3.8b 4-6, gemma4:e4b 1, 3, 4)

| Model | Overall (mean +- SD) | 95% CI | Run-to-run agreement | AR-3 (>= 85%) |
| --- | --- | --- | --- | --- |
| gemma4:e4b | 84.4% +- 0.3 | 79.0-89.3% | 161/175 | **Not met** |
| mistral:7b | 73.1% | 66.9-79.4% | 175/175 | **Not met** |
| phi3:3.8b | 73.1% | 66.9-80.0% | 175/175 | **Not met** |
| llama3.2:1b | 34.9% | 28.0-41.7% | 175/175 | **Not met** |

**No candidate meets AR-3.** Per-category results and confusion matrices are in `analysis/output/accuracy_report.md`.
Weakest categories: gemma4:e4b credit card (64%) and money transfer (71%), mostly misrouted to Bank account or
service; mistral:7b money transfer (33%); phi3:3.8b debt collection and money transfer (50%); llama3.2:1b credit card
and money transfer (0%), mostly answered as Credit reporting or Debt collection.
