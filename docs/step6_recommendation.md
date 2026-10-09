# Step 6 – Recommendation

Team 2 · ICT3113 A1 · 8 Oct 2026

**Team position: no candidate model is recommended for deployment.**

Every measured number below is generated from files in this repository:

- Requirement verdicts, load metrics, server-side counts, per-category accuracy, single-request latency:
  `python analysis/requirements_matrix.py` → `analysis/output/requirements_matrix.md`
- Accuracy, confusion matrices, confidence intervals, McNemar tests: `accuracy/accuracy_report.py` →
  `analysis/output/accuracy_report.md`
- Stress steps: `python analysis/load_summary.py` → `analysis/output/load_summary.md`

Figures marked *derived* are arithmetic on those numbers; the assumption behind each is stated next to it.

---

## 1. Recommendation

**We do not recommend any of the four candidate models for deployment.**

The client needs two things at the same time, and each failure has a business cost:

- **Correct routing.** A misrouted ticket reaches the wrong team and is handled twice (AR-1). We judge this to be
  **the higher cost**.
- **Triage that keeps up with the volume.** If classification is too slow or cannot handle 1,312 tickets/h on
  average and 3,936/h at peak, tickets queue, fail, or are routed by hand. Once that happens, "the system loses
  its purpose" (RR-1).

**No candidate delivers both.**

- The one model that keeps up with peak volume, llama3.2:1b, routes 65% of tickets wrongly.
- The most accurate model, gemma4:e4b, still misses our accuracy requirements. On one CPU node it handles only
  97–118 tickets/h, with about 34 s per ticket even when idle.
- phi3:3.8b and mistral:7b fall short on both accuracy and peak capacity.

Deploying any of them would trade one business cost for the other.

All requirements are read strictly as written in Step 4. gemma4:e4b's 84.4% overall is a fail against AR-3's
85%, even though its 95% confidence interval (79.0–89.3%) reaches 85%.

---

## 2. Results matrix

Load results use only requests sent after the first 2 minutes of each run (§4). Each cell is the mean of 3 runs.
Accuracy is the mean of 3 runs over the 175-ticket golden set.

| Requirement (Step 4) | llama3.2:1b | phi3:3.8b | mistral:7b | gemma4:e4b |
|---|---|---|---|---|
| **RR-1** POST p95 ≤ 30 s at 3,936/h, < 1% errors | ✅ 20.0 s, 0% | ❌ 98.5% errors | ❌ 100% errors | ❌ 100% errors |
| **RR-2** search p95 ≤ 500 ms, mixed load, < 1% errors | ✅ 134 ms, 0% | ❌ 79.1% errors | ❌ 97.0% errors | ❌ 100% errors |
| **TR-1** 1,312/h sustained, < 1% errors, no drift | ✅ 190/190 OK | ✅ 192/192 OK | ❌ queue grows (×1.70–2.38) | ❌ 0/193 OK |
| **TR-2** 3,936/h sustained, < 1% errors | ✅ 575/575 OK | ❌ 9/589 OK | ❌ 0/583 OK | ❌ 0/585 OK |
| **AR-1** ≥ 75% Debt coll., Credit rep., Money transfer | ❌ | ❌ | ❌ | ❌ Money transfer 70.8% |
| **AR-2** ≥ 90% Mortgage, Consumer loan, Credit card, Bank | ❌ | ❌ | ❌ | ❌ Credit card 63.9% |
| **AR-3** ≥ 85% overall | ❌ 34.9% | ❌ 73.1% | ❌ 73.1% | ❌ 84.4% |
| **Speed and capacity (RR, TR)** | **4 of 4** | 1 of 4 | 0 of 4 | 0 of 4 |
| **Accuracy (AR)** | 0 of 3 | 0 of 3 | 0 of 3 | 0 of 3 |

Per-category accuracy (recall). The bar is 75% for AR-1 categories and 90% for AR-2 categories:

| Category (golden n) | Bar | llama3.2:1b | phi3:3.8b | mistral:7b | gemma4:e4b |
|---|---|---|---|---|---|
| Debt collection (22) | 75% | 81.8% | 50.0% | 86.4% | 77.3% |
| Credit reporting (35) | 75% | 71.4% | 85.7% | 82.9% | 87.6% |
| Money transfer or service (24) | 75% | 0.0% | 50.0% | 33.3% | 70.8% |
| Mortgage (21) | 90% | 42.9% | 100.0% | 100.0% | 100.0% |
| Consumer loan (23) | 90% | 8.7% | 73.9% | 65.2% | 92.8% |
| Credit card (24) | 90% | 0.0% | 58.3% | 75.0% | 63.9% |
| Bank account or service (26) | 90% | 26.9% | 88.5% | 69.2% | 97.4% |

Capacity of one node, from the load and stress tests:

| | llama3.2:1b | phi3:3.8b | mistral:7b | gemma4:e4b |
|---|---|---|---|---|
| Sustainable tickets/h | ≥ 3,936 | between 1,312 and 3,936 | < 1,312 | 97–118 (stress test) |
| p95 at 1,312/h | 2.6 s | 10.3 s | 153.6 s, still rising | every request fails |

---

## 3. Rationale

### 3.1 The business cost of each failure

Step 4 defines both costs:

- **Misrouting.** Each misrouted ticket must be re-handled by staff (AR-1); recall below 75% means more than 1 in
  4 tickets needs manual rework. AR-3 makes overall accuracy a gate: a candidate below 85% "is excluded
  regardless of its latency or throughput results".
- **Slow or failed triage.** Beyond 30 s "staff are likely to route tickets manually and the system loses its
  purpose" (RR-1). If throughput is below the arrival rate (TR-1, TR-2), the backlog grows without limit.

**We judge misrouting to be the higher cost.**
- A slow ticket is delayed once.
- A misrouted ticket costs a wrong hand-off, a re-route and a second handling by staff.
- Each misroute also costs the client's trust in automatic routing. That is the same failure RR-1 warns about:
  staff going back to routing by hand.

A fast model with poor accuracy therefore cannot be justified by its speed.

### 3.2 Misrouting cost per model

*Derived*: misrouted tickets per hour = arrival rate × (1 − measured overall accuracy). This assumes the
golden-set accuracy holds for live traffic.

| | llama3.2:1b | phi3:3.8b | mistral:7b | gemma4:e4b |
|---|---|---|---|---|
| Overall accuracy (95% CI) | 34.9% (28.0–41.7%) | 73.1% (66.9–80.0%) | 73.1% (66.9–79.4%) | 84.4% (79.0–89.3%) |
| Misrouted per hour at 1,312/h | ≈ 855 | ≈ 352 | ≈ 352 | ≈ 205 |
| Misrouted per hour at 3,936/h | ≈ 2,564 | ≈ 1,057 | ≈ 1,057 | ≈ 615 |

### 3.3 Why each model is rejected

| Model | Speed and capacity | Accuracy | Why it is rejected |
|---|---|---|---|
| **llama3.2:1b** | Meets RR-1, RR-2, TR-1, TR-2 on one node | 34.9%; 0/24 on Credit card and on Money transfer | Fastest, but misroutes about 2 tickets in 3. Under our cost position this is the most expensive outcome, so its speed does not compensate |
| **phi3:3.8b** | Meets TR-1 (p95 10.3 s at 1,312/h); fails at peak (98.5% errors) | 73.1%; below the bar in 5 of 7 categories | Fails both sides: about 1 ticket in 4 misrouted, and cannot handle the peak on one node |
| **mistral:7b** | Fails TR-1: at 1,312/h its queue grows in every run | 73.1%, statistically identical to phi3 (exact McNemar p = 1.00) | Same accuracy as phi3 with less capacity; no requirement on which it is better |
| **gemma4:e4b** | Fails every load requirement: 97–118 tickets/h per node; about 34 s per ticket with no queue | 84.4%; fails AR-3 (strict), Money transfer 70.8%, Credit card 63.9% | Most accurate (significantly better than every other model, Holm-adjusted p ≤ 0.0016) but still below our accuracy bar. It cannot meet the client's volume on one node: *derived* 12–14 nodes at 1,312/h and 34–41 at 3,936/h, assuming linear scale-out. It cannot meet RR-1's 30 s at any node count on this CPU class |

**Conclusion:**
- The accuracy requirements, which carry the higher cost, are met by no model.
- The speed and capacity requirements are met only by the model with the worst accuracy.
- No candidate meets both, so none is recommended.

---

## 4. How the requirements were evaluated

### 4.1 Evaluation rules

- **Runs.** 36 load runs: 4 models × 3 configurations × 3 runs, each 5 minutes of open-loop traffic (random
  arrivals) from P2's laptop to the official SUT.
  - `tkt-normal`: tickets at 1,312/h.
  - `tkt-peak`: tickets at 3,936/h.
  - `mix-peak`: tickets at 3,936/h plus searches at 7,872/h.
  - Excluded attempts are listed in `analysis/excluded_runs.csv` with reasons.
- **Window.** The first 120 s of each run are excluded, as RR-1's measurement text specifies. This leaves about
  3 minutes per run, roughly 64, 195 and 390 requests per run for normal tickets, peak tickets and searches.
- **p95.** Counts every request. An error or a 295 s client timeout counts as slower than any answer, so the
  p95 shows "> 295 s" once more than 5% of requests fail. A requirement passes only if **all 3 runs** pass.
- **Drift (TR-1, TR-2).** Measured as the median latency of the second half of the window divided by the first
  half. 1.5 or more counts as a growing queue. The observed values separate cleanly:
  - mistral at 1,312/h: ×1.70–2.38, rising in every run;
  - llama and phi3: ×0.41–1.39, moving both up and down.
- **Accuracy.** Each of the 175 golden tickets is sent once per run, one request at a time. Requirements are
  judged strictly on the mean of the counted runs: llama 1–3, mistral 1–3, phi3 4–6 and gemma4 1, 3, 4. phi3
  runs 1–3 are excluded because the Ollama runner crashed on 1–2 tickets per run on the accuracy machine; on
  every ticket both sets answered, they gave the same answers as runs 4–6.

### 4.2 Effect of excluding the first 2 minutes

| Metric | All samples | After 120 s | Verdict change |
|---|---|---|---|
| llama RR-1 p95 (worst run) | 18.8 s (22.5 s) | 20.0 s (23.7 s) | none, still ≤ 30 s |
| llama RR-2 search p95 (worst run) | 123 ms (145 ms) | 134 ms (155 ms) | none, still ≤ 500 ms |
| phi3 TR-1 errors / p95 | 0% / 10.1 s | 0% / 10.3 s | none |
| mistral TR-1 median latency | 59.9 s | 95.5 s | none, already failing |
| Ticket errors at peak: phi3 / mistral / gemma4 | 75.5% / 89.7% / 99.4% | 98.5% / 100% / 100% | none, already failing |
| Search errors, mixed: phi3 / mistral / gemma4 | 51.2% / 67.2% / 83.0% | 79.1% / 97.0% / 100% | none, already failing |

**The exclusion changes no verdict.** `prepare_run` already warms the model before every run, so the first
2 minutes are not a cold start. In an overloaded run they are the time the queue takes to fill, and including
them makes the overloaded configurations look better than they are. We report the after-120 s figures as
official and keep the all-sample figures (bracketed in `requirements_matrix.md`) as a cross-check.

The cost is sample size. With about 64 requests per normal run, p99 depends on the slowest one or two requests.

---

## 5. Models that can be optimised (Assignment 2)

The gap each model must close, measured against the Step 4 requirements:

| Model | Gap to the accuracy requirements | Gap to the speed and capacity requirements | Where the gap comes from |
|---|---|---|---|
| **gemma4:e4b** | **Smallest.** 1–2 more correct tickets per run for AR-3 (147–148 of the 149 needed); Money transfer +1 ticket (17 of 18); Credit card +5 to +8 tickets (14–17 of 22) | **Largest.** One node sustains 97–118/h against 1,312/h (×11–14) and 3,936/h (×33–41); about 34 s per ticket against RR-1's 30 s | Ollama classifies one ticket at a time (`OLLAMA_NUM_PARALLEL=1`); gemma4 writes reasoning text before answering (Step 4 Appendix A); the service-layer limits in §6. Money transfer and Credit card are mostly answered as Bank account (18 of 72 and 13 of 72 answers over 3 runs) |
| **phi3:3.8b** | 21 more correct tickets per run for AR-3 (128 of 149); short in Debt collection (6), Money transfer (6), Consumer loan (4), Credit card (8), Bank account (1) | **Small.** Meets TR-1 on one node; at peak fails, with capacity between 1,312 and 3,936/h (*derived*: 2–3 nodes for peak) | Money transfer → Bank account (10 of 24); Debt collection → Credit reporting (5 of 22); peak failures come from the §6 service-layer limits |
| mistral:7b | 21 more correct tickets per run (128 of 149) | Fails TR-1 on one node | Same accuracy as phi3 with less capacity, so it offers nothing phi3 does not |
| llama3.2:1b | 88 more correct tickets per run (61 of 149); 0 of 24 on Credit card and on Money transfer; short in 6 of 7 categories | None: meets all four | The gap is the model's classification itself, not the system around it |

**gemma4:e4b and phi3:3.8b can be optimised. They have the smallest gaps, on opposite sides:**
- gemma4 is a few tickets short on accuracy and far short on capacity and latency.
- phi3 is short on accuracy and only moderately short on peak capacity.

mistral:7b is dominated by phi3:3.8b. llama3.2:1b's accuracy gap (88 tickets) is too large for system-level
optimisation to close.

**For any model:** the service-layer bottleneck in §6 causes most HTTP 500s and starves `GET /search`.

---

## 6. Diagnosed bottleneck

1. **Capacity is set by Ollama, which runs one classification at a time** (`OLLAMA_NUM_PARALLEL=1`,
   `docs/environment/p1_sut_environment.md`). The ticket ceiling is therefore about 1 ÷ per-ticket service time.
   - The gemma4 stress test finds the knee between 97/h and 118/h. Mean latency is 35.0 s at 64/h and 37.5 s
     at 97/h, then 78.3 s at 118/h and still rising (124.3 s, 215.5 s, 299.6 s in recovery).
   - That knee matches 3,600 s ÷ 33.5 s ≈ 107/h.
   - mistral's queue grows at 1,312/h; llama keeps up at 3,936/h.
2. **The service layer turns overload into errors.**
   - While Ollama works through its queue, each waiting request holds one of the service's worker threads and a
     database connection. The connection pool allows 15 (5 + 10 overflow) with a 30 s wait.
   - Once those are taken, new requests wait 30 s and fail with HTTP 500 (sqlalchemy QueuePool timeout). That
     includes `GET /search`, which never calls the model.
   - Evidence (`requirements_matrix.md`, server-side table): 90–370 HTTP 500s per overloaded phi3/mistral run,
     and 0 in every llama run.
   - In 15 of the 18 peak/mixed runs of phi3, mistral and gemma4, exactly 15 tickets were stored in the database
     but never answered or logged. 15 is the pool size, which strongly suggests finished requests keep their
     connection while waiting for a thread to release it.
   - This is why RR-2 fails for every model except llama: search is starved by the shared pools, not by the CPU.
3. **The service's 600 s limit on one Ollama call** produces HTTP 502 for gemma4 when a ticket waits more than
   600 s in Ollama's queue. All 95 gemma4 502s took 600–630 s.

As the brief allows for Assignment 1, these are diagnosed and noted, not fixed.

---

## 7. Predictions vs outcomes (Slide 11)

Prediction record committed 24 Sep 2026 (`datasets/PredictionRecord.pdf`), before the first benchmark run.

| Prediction | Outcome | Verdict |
|---|---|---|
| **Bottleneck**: Ollama, "before storage or the service layer become limiting" | Ollama sets capacity, but the service layer (thread pool + 15-connection DB pool) produced the failures and starved search | **Partly wrong** |
| **Ceilings** (3,600 ÷ latency): llama 514/h, phi3 450/h, mistral 180/h, gemma4 80/h; all fail TR-1 | llama ≥ 3,936/h; phi3 1,312–3,936/h; mistral < 1,312/h; gemma4 97–118/h. llama and phi3 pass TR-1 | **Wrong** for llama and phi3; close for gemma4 |
| **Single-request latency** (p95-length ticket): llama 2–7 s, phi3 3–8 s, mistral 15–20 s, gemma4 35–45 s | gemma4 on the SUT: 33.5 s mean (P5 baseline), 34.0 s median and 41.7 s p95 (stress step 1). llama on the SUT: 1.2 s median at 1,312/h. phi3 and mistral: no clean SUT figure yet (P3's machines: 6.6 s and 11.6 s median, 13.0 s and 24.8 s p95) | gemma4 **right** (low end); llama **wrong**, faster; phi3/mistral open item §10 |
| **Accuracy**: llama 60–62%, phi3 75–80%, mistral 80–85%, gemma4 90–95% | 34.9%, 73.1%, 73.1%, 84.4% | **Wrong** for all four, all lower |
| **Implied failures**: llama fails AR-3; gemma4 exceeds RR-1 | llama 34.9%; gemma4 about 34 s per ticket even unloaded | **Right** |
| **Hardest categories**: Debt collection and Credit reporting | Hardest are Money transfer (below 75% for all four models) and Credit card (below 90% for all four). Credit reporting and Debt collection each reach 75% for 3 of 4 models | **Wrong** |

**Why the predictions missed:**

- **Throughput ceilings.** They were built from single-request latencies that were too slow for the small
  models on the official SUT: llama answers in about 1.2 s at light load, against 2–7 s predicted.
- **Hardest categories.** The dominant confusion is Money transfer → Bank account (gemma4 18 of 72 answers over
  3 runs, phi3 10/24, mistral 7/24), followed by Credit card → Bank account (gemma4 13/72, phi3 6/24). Step 1
  had flagged Money transfer vs Bank account only as a secondary disagreement, so the prediction under-weighted
  it.
- **Bottleneck.** The record treated the service as a thin layer. Its default thread and connection pools fail
  long before Ollama's queue limit (`OLLAMA_MAX_QUEUE=512`) is reached.

---

## 8. Requirements no candidate meets

- **AR-1, AR-2 and AR-3 are met by no candidate.** Money transfer (best 70.8%) and Credit card (best 75.0%) are
  below their bars for every model.
- **No candidate meets both the speed and capacity requirements and the accuracy requirements.** RR-1, RR-2 and
  TR-2 are met only by llama3.2:1b, which fails all three accuracy requirements.
- **On a single CPU node, gemma4:e4b meets none of RR-1, RR-2, TR-1 or TR-2.** RR-1 cannot be met by adding
  nodes, because one gemma4 request takes about 34 s on its own.

---

## 9. Limitations and deviations from the Step 4 measurement plan

| Step 4 says | What we did | Effect |
|---|---|---|
| 10-min steady-state window (RR-1, RR-2, TR-2); 30 min for TR-1 | 5-min runs, first 120 s excluded, so about 3 min × 3 runs | Verdicts are clear-cut (0% vs ≥ 79% errors), but long-term drift beyond 5 min is untested |
| Response timeout 120 s | 295 s | No verdict changes: the slowest successful request in any passing configuration was 27.4 s |
| Searches at 3.28/s (11,808/h) | 7,872/h (2 per ticket, the middle of RR-2's 3,936–11,808/h range) | llama's RR-2 pass is shown at 7,872/h only |
| Ticket store pre-loaded before mixed runs | Each run starts with an empty store; tickets enter only through `POST /tickets`, as the brief requires | Searches run against a smaller store than in production |
| `monitor.py` CPU/RAM log | Not run | The bottleneck diagnosis rests on service, Ollama and JMeter logs |
| RR-1 table: "tickets at p95 length 1,722 characters" | Tickets drawn from the team's rows as the RR-1 template describes; 327 distinct narratives across all load runs | Ticket mix follows the dataset, not only long tickets |
| Accuracy on the SUT | Run on P3's machines (DESKTOP-M4H382A for gemma4, LAPTOP-LVH7E9IH for the rest), client on the same machine | 50 golden tickets also classified on the SUT (310 answers) got the same category every time; latency from these runs is not used |

Other limitations:

- **Reconciliation.** 18 of the 36 load runs, plus the stress run, fail `analysis/reconcile.py`. Each failure is
  explained in `runs/run_register.csv`: the 15 stuck tickets above, unpaired HTTP 500s, and the stress run's
  mistyped run tag. Every client sample in the `.jtl` files is kept.
- **Test setup.** One consumer laptop (i9-14900HX, CPU only) over a phone hotspot. Node counts are *derived*
  by linear scaling, which is not tested.

---

## 10. Open items before the slides are final

1. **Single-request latency on the SUT for phi3 and mistral (and ideally all four).**
   - Run `accuracy/accuracy_test.py --limit 25` per model from P2's laptop: about 30–40 min.
   - Until then, Slide 11 must label the phi3/mistral latency as coming from P3's machines.
2. **Exclusions file.** Add phi3 accuracy runs 1–3 to `analysis/excluded_runs.csv` with the runner-crash reason.
3. **Environment records.**
   - Re-record the SUT environment: the current record is from 26 Sep, showing Balanced mode and home Wi-Fi.
   - Add P2's 8 Oct load-generator record and records for P3's two accuracy machines and P5's stress laptop.

---

## 11. Evidence index

| What | Where |
|---|---|
| Requirement verdicts, load metrics (both windows), server-side counts, SUT agreement | `analysis/requirements_matrix.py` → `analysis/output/requirements_matrix.md`, `requirements_matrix_load.csv` |
| Accuracy, confusion matrices, CIs, McNemar | `accuracy/accuracy_report.py` → `analysis/output/accuracy_report.md` |
| Stress steps | `analysis/load_summary.py` → `analysis/output/load_summary.md`; `runs/gemma4-e4b_stress_ramp_run2/` |
| Raw evidence per run | `runs/<run_id>/` (`.jtl`, `server_access.log`, `tickets.tsv`, `request_metrics.tsv`, `ollama.log`) |
| Run notes and explained reconciliation failures | `runs/run_register.csv`, `analysis/excluded_runs.csv` |
| Requirements and predictions | Step 4 document; `datasets/PredictionRecord.pdf` (committed 24 Sep 2026) |
