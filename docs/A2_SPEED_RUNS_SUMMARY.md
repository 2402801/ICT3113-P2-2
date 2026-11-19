# A2 speed runs: summary of the 9 official runs

All figures are computed from `runs/<run-id>/*.jtl` (latency, client side), `client_summary.json` (P2) and
`sut_summary.json` / `server_access.log` (P1). Settings: S = 31.08 s (probe timings 48.7, 31.08, 29.2 s; rows 35, 85, 27),
rate 58 tickets/hour (one every 62.1 s), window 1865 s, response timeout 311 s, pause 401 s, 30 tickets per run, same ticket
list and order for every configuration, seed 1000 + run number. Load generator on a separate laptop (P2), SUT on P1's laptop,
CPU only (`size_vram = 0`).

## Per run

| Run id | Sent | OK | Errors | Unfinished | p50 (s) | Mean (s) | Max (s) | Escalated |
|---|---|---|---|---|---|---|---|---|
| gemmaAlone run 1 | 30 | 30 | 0 | 0 | 67.6 | 74.5 | 190.9 | n/a |
| gemmaAlone run 2 | 30 | 30 | 0 | 0 | 39.3 | 42.8 | 77.7 | n/a |
| gemmaAlone run 3 | 30 | 30 | 0 | 0 | 39.7 | 43.4 | 83.8 | n/a |
| cascadeS1 run 1 | 30 | 30 | 0 | 0 | 26.1 | 25.7 | 88.5 | 16/30 = 53.3% |
| cascadeS1 run 2 | 30 | 30 | 0 | 0 | 27.3 | 21.8 | 52.7 | 16/30 = 53.3% |
| cascadeS1 run 3 | 30 | 30 | 0 | 0 | 27.0 | 22.5 | 69.2 | 16/30 = 53.3% |
| cascadeS2 run 1 | 30 | 30 | 0 | 0 | 3.7 | 20.8 | 90.5 | 11/30 = 36.7% |
| cascadeS2 run 2 | 30 | 30 | 0 | 0 | 3.8 | 17.0 | 57.5 | 11/30 = 36.7% |
| cascadeS2 run 3 | 30 | 30 | 0 | 0 | 3.8 | 17.1 | 74.0 | 11/30 = 36.7% |

Unfinished = sent - OK - errors = 0 in every run. `/stats` before/after shows 30 tickets stored in every run.

## Per configuration (3 runs)

| Configuration | p50 per run (s) | Mean of the 3 p50s | Spread (sd, range) | Pooled n | Pooled p50 | Pooled p95 | Escalation under load |
|---|---|---|---|---|---|---|---|
| gemmaAlone | 67.6 / 39.3 / 39.7 | 48.8 | sd 16.2, 39.3-67.6 | 90 | 43.6 | 104.1 | n/a |
| cascadeS1 | 26.1 / 27.3 / 27.0 | 26.8 | sd 0.6, 26.1-27.3 | 90 | 26.7 | 64.9 | 53.3% |
| cascadeS2 | 3.7 / 3.8 / 3.8 | 3.8 | sd 0.1, 3.7-3.8 | 90 | 3.8 | 63.9 | 36.7% |

Throughput per run is in each `client_summary.json` (about 0.017 completed requests/s, i.e. the arrival rate).
p99 is deliberately not reported (the brief forbids it at this sample size).

## Accuracy on the test set (88 tickets), recomputed from `runs/*_accuracy_a2test88*`

Limits: overall >= 61/88 (68.4%); per category = gemma's category accuracy - 15 pp.

| Configuration | Correct | Overall | Per-category fails | Passes both limits? |
|---|---|---|---|---|
| gemma4:e4b alone (reference) | 69/88 | 78.4% | none | yes |
| cascade S1 | 70/88 | 79.5% | none | **yes** |
| cascade S2 | 67/88 | 76.1% | Consumer loan | **no** (overall passes, one category fails) |
| mistral-7b | 61/88 | 69.3% | Consumer loan, Bank account, Money transfer | no |
| phi3-3.8b | 58/88 | 65.9% | Consumer loan, Credit card | no |
| llama3.2-1b | 25/88 | 28.4% | six categories | no |

So no extra single model needs a speed test, and the 9 runs cover everything the brief requires.
(These pass/fail figures are my recomputation. Check them against `analysis/a2_limits.py` before putting them on a slide.)

## What the numbers say

- Fastest qualifying configuration (passes both limits) is **cascade S1**: pooled p50 26.7 s against 43.6 s for gemma alone
  (about 39% lower), p95 64.9 s against 104.1 s.
- Cascade S2 is the fastest overall but **fails the Consumer loan per-category limit**, so by the brief it must be reported
  as "not passing accuracy" and cannot be the recommendation.
- Escalation under load (53.3% and 36.7%) is lower than the tuning-set estimates (about 69% and 46%) and than the accuracy-test
  figures (55/88 = 62.5% and 43/88 = 48.9% in the accuracy logs). The brief asks for any large gap to be explained; the
  different ticket mix (speed workload vs test set) is the likely reason, but this has not been checked.
- The three runs of a cascade have identical escalation counts because the ticket list and order are the same and the model
  is deterministic. That is expected, not a copy error.
- gemmaAlone run 1 (p50 67.6 s) is well above runs 2 and 3 (about 39 s). Gemma's time per ticket is often above the 62 s
  gap between arrivals for longer tickets, so a queue built up in run 1. Report all three runs as they are (the brief says so)
  and say on the limitations slide that gemma alone was not always idle half the time.

## Limitations to state (slide 8)

- Test rate (58/hour) is far below the A1 client peak (3936/hour): the results compare configurations; they do not show the
  recommended one can handle the client's peak.
- 30 tickets per run, one machine, one arrival rate, tickets drawn from rows outside the golden set.
- Hotspot network (median 15 ms round trip to `/health`) adds almost nothing, but it is a mobile hotspot.
- The trial run 99 (`phi3-3.8b_speed_cascadeS1_run99`) is a rehearsal and is excluded from every figure.
