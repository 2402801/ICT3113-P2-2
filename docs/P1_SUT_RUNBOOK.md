# P1 — Official SUT Runbook

Owner: P1 (Environment & Infrastructure). Readers: whoever operates the SUT laptop, and the testers
(P2–P5) who send traffic to it. Everything here is Windows PowerShell 5.1 and runs from the repo root.

> Run scripts as `powershell -ExecutionPolicy Bypass -File scripts\p1\<name>.ps1 ...`

## 1. What the SUT is

```
 Load generator / accuracy / stress laptop            OFFICIAL SUT LAPTOP (P1)
 ┌───────────────────────┐   HTTP over LAN   ┌──────────────────────────────────────────────┐
 │ JMeter or test script │ ───────────────▶  │ :8000  triage service (FastAPI, synchronous) │
 └───────────────────────┘                   │          │ 1 blocking call per ticket        │
                                             │          ▼                                   │
                                             │ Ollama 0.34.4, CPU only (127.0.0.1:11434)    │
                                             │ MySQL 8.0.46 (127.0.0.1:3306)                │
                                             └──────────────────────────────────────────────┘
```

Only port 8000 is reachable from other laptops. MySQL and Ollama are bound to localhost.

## 2. Settings frozen for every official run

Only the model changes between official comparisons. Everything below stays identical.

| Setting | Value | Why |
| --- | --- | --- |
| Ollama image | `ollama/ollama:0.34.4` (digest in `docs/environment/p1_sut_environment.md`) | same inference engine for every run |
| MySQL image | `mysql:8.0.46` | same storage engine |
| Models | the 4 Step 4 candidates, full digests in `docs/environment/model_pins.json` | a changed digest = a different model |
| GPU | none passed to the container; `size_vram = 0` checked before and after every run | brief forbids GPU inference |
| `OLLAMA_NUM_PARALLEL` | 1 | baseline processes one ticket at a time; others wait in Ollama's queue |
| `OLLAMA_MAX_QUEUE` | 512 (Ollama default) | beyond this Ollama answers 503 → the service answers 502 |
| `OLLAMA_MAX_LOADED_MODELS` | 1 | only the model under test uses RAM |
| `OLLAMA_KEEP_ALIVE` | -1 | a quiet period mid-test must not unload the model and turn the next ticket into a cold start |
| Context window | Ollama default 4096 tokens (longest ticket + prompt ≈ 850 tokens) | no truncation |
| Prompt | `server/prompt.py`, `PROMPT_VERSION = v1`: 7 categories + the protocol §1 definitions, no §2–3 edge-case rules | same instructions for every model |
| Decoding | `temperature 0`, `seed 42`, JSON-schema output restricted to the 7 exact category names | deterministic; the answer is always one valid category |
| `think` | not sent (`OLLAMA_THINK=default`): each model as shipped, so gemma4:e4b reasons before answering and the other three cannot | untuned baseline; matches how the Step 4 predictions were timed; see §9 |
| Service → Ollama timeout | 600 s | failures come from the system limits under test, not an arbitrary short timeout |
| Warm-up | 1 fixed invented ticket (`$WarmupNarrative` in `scripts/p1/_common.ps1`), before each run, not measured | every run starts with the model already in RAM |
| Service | synchronous: `POST /tickets` returns only after classification; no caching, queuing or batching | Assignment 1 baseline |

## 3. One-time setup (already done on the SUT laptop)

```powershell
docker compose up -d --build                                   # mysql + ollama + server
powershell -ExecutionPolicy Bypass -File scripts\p1\pin_models.ps1 -Pull          # pull 4 models, write model_pins.json
powershell -ExecutionPolicy Bypass -File scripts\p1\record_environment.ps1        # Slide 7 evidence
```

Firewall (admin PowerShell, once): lets teammates on the same subnet reach port 8000 on any network type.

```powershell
New-NetFirewallRule -DisplayName 'ICT3113 SUT API (TCP 8000)' -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Any -RemoteAddress LocalSubnet
```

## 4. Before every test session

1. Plug the SUT into AC. Set Windows power mode to **Best performance**. Set the Legion thermal mode to
   **Performance** (Fn+Q). Write the thermal mode in `-Notes` when preparing runs.
2. Close heavy apps (games, VMs, big downloads, browsers with video). Do not run JMeter on the SUT.
3. Start the stack if needed: `docker compose up -d`
4. `powershell -ExecutionPolicy Bypass -File scripts\p1\preflight.ps1` — must end with `PREFLIGHT OK`.
   It also checks that the Docker VM clock matches Windows. After the laptop sleeps, WSL2's clock can drift and
   log timestamps would no longer line up with JMeter's. Restart Docker Desktop if it warns. The load-generator
   laptop should also sync its clock (Settings → Time & language → Sync now).
5. The testers run `scripts\record_loadgen_environment.ps1 -SutHost <SUT-IP>` once per session on their laptop and commit the output to `docs/environment/`.

## 5. The per-run loop

```powershell
# (only when the model changes)
powershell -ExecutionPolicy Bypass -File scripts\p1\switch_model.ps1 -Model phi3:3.8b

# before EACH run: warm-up, CPU-only check, fresh log, DB reset, READY banner
powershell -ExecutionPolicy Bypass -File scripts\p1\prepare_run.ps1 -TestType load -Config 1312tph -Run 1 -Tester P2 -Notes "Legion Performance"

#   ... tester runs the test against http://<SUT-IP>:8000 ...

# after EACH run: archive log + DB rows + Ollama log, restart service, mark DONE
powershell -ExecutionPolicy Bypass -File scripts\p1\finish_run.ps1 -RunId phi3-3.8b_load_1312tph_run1
```

Then the tester copies their raw output (`.jtl`, accuracy CSV, …) into `runs\<run-id>\` and the folder is committed.

**Run ID** = `<model>_<test-type>_<config>_run<n>`, with the `:` in the tag written as `-`. Examples:
`llama3.2-1b_load_1312tph_run1`, `mistral-7b_accuracy_golden175_run1`, `gemma4-e4b_stress_ramp_run1`.
`prepare_run.ps1` refuses to reuse an existing ID, so evidence can never be overwritten.

**What each run folder holds**

| File | From | Content |
| --- | --- | --- |
| `run_info.json` | prepare | model + digest, commit, prompt, think, Ollama version, power state, SUT URL, READY time |
| `warmup_access.log` | prepare | warm-up request(s) and P1 checks before READY (not part of the run) |
| `ollama_ps_before.*` / `ollama_ps_after.*` | prepare / finish | model resident, `size_vram = 0` (CPU-only proof) |
| `server_access.log` | finish | one line per request handled during the run (the first `GET /health` with `run=-` is P1's readiness check) |
| `tickets.tsv`, `request_metrics.tsv` | finish | the database rows written during the run |
| `ollama.log` | finish | Ollama's own log for the run window (one `[GIN]` line per inference) |
| tester's files | tester | raw `.jtl` / accuracy output — **required** |

`runs/run_register.csv` has one row per run (READY → DONE) and is the index for the slides. Rows with
`test_type = smoke` are P1's setup checks (two invented tickets per model, 2026-09-26). They prove the procedure and
CPU-only inference work for all four models. They are not evidence for any requirement; exclude them from analysis.

## 6. For testers (P2–P5)

- Target `http://<SUT-IP>:8000` (P1 prints it in the READY banner). Check `GET /health` first: it
  returns the model under test, e.g. `{"status":"ok","model":"phi3:3.8b","prompt_version":"v1","think":"false"}`.
- Only send traffic between READY and `finish_run`, and only for your run. Anything else lands in that run's evidence.
- Optional header `X-Run-Id: <run-id>`: it is written into every server log line (`run=`) for that request.
- `POST /tickets` → `200 {"id","category","narrative","classification_latency_ms"}`. `502` = classification failed
  (Ollama error, queue full, timeout, or no valid category); the log's `error=` field says which. Count 502s as errors.
- Server log line format (UTC):
  `2026-09-26T13:17:09.317Z POST /tickets 200 3757.89ms client=… req_id=… start_ms=<epoch ms> run=… model=… ticket_id=… category="…" ollama_total_ms=… ollama_load_ms=… prompt_tokens=… prompt_eval_ms=… eval_tokens=… eval_ms=…`
  - `start_ms` is directly comparable with JMeter's `timeStamp` (epoch ms), within the two laptops' clock offset.
  - Every response carries an `X-Request-ID` header equal to `req_id`.
  - Time spent waiting in Ollama's queue ≈ `ollama_total_ms − ollama_load_ms − prompt_eval_ms − eval_ms`.
- `client=` shows the Docker gateway, not your laptop's IP (Docker Desktop port forwarding). Runs are told apart by time window and `run=`.

## 7. Manual fallback commands

```powershell
docker compose ps                                          # all three services running / healthy
Invoke-RestMethod http://localhost:8000/health             # model the service is using
Invoke-RestMethod http://localhost:11434/api/ps            # loaded model; size_vram must be 0
docker compose exec ollama ollama ps                       # PROCESSOR column must say 100% CPU
docker compose exec -T -e MYSQL_PWD=triage mysql mysql -utriage triage -e "TRUNCATE TABLE request_metrics; TRUNCATE TABLE tickets;"
docker compose logs --tail 50 server                       # service errors
docker compose logs --tail 50 ollama                       # Ollama errors
docker compose down                                        # stop everything (volumes/models are kept)
```

Switching models by hand: set `OLLAMA_MODEL=<tag>` in `.env`, then `docker compose up -d --no-deps --force-recreate server`
and confirm `/health`. A leftover `$env:OLLAMA_MODEL` in your shell overrides `.env`. `switch_model.ps1` handles both.

## 8. Evidence for Slide 7

| Evidence | Where |
| --- | --- |
| SUT hardware, OS, Docker/WSL, Ollama settings, model digests, network, CPU-only proof, commit | `docs/environment/p1_sut_environment.md` (re-run `record_environment.ps1` on test day) |
| Full model pins | `docs/environment/model_pins.json` |
| Load-generator hardware, JMeter/Java, separate-machine proof, network round trip | `docs/environment/loadgen_environment.md` (tester runs `scripts/record_loadgen_environment.ps1`) |
| Per-run conditions | `runs/<run-id>/run_info.json`, `runs/run_register.csv` |

## 9. Open items P1 flagged (owners must decide before the first official run)

1. **JMeter is still closed-loop** (Thread Group + Constant Throughput Timer). The brief rejects closed-loop
   evidence. P2 must switch to the Open Model Thread Group or Precise Throughput Timer.
2. **JMeter/README rates are the old Tier A figures** (5.5 tickets/hour). Step 4 requirements use
   1,312 tickets/h (TR-1), 3,936 tickets/h (TR-2) and the search mix in RR-2. P2/P4 must align them.
3. **Which laptop is the official load generator?** The team table says P2's laptop, the P1 handoff says P4's.
   Pick one, keep it for every run, and record it with `record_loadgen_environment.ps1`. The README's
   "run JMeter in Docker on the compose network" option puts JMeter on the SUT itself. Never use it for official runs.
4. **Prompt v1, the `think` setting and JSON-schema output are P1 defaults, not yet team decisions.** P3 and the
   team should confirm them before the first official run. Changing any of them afterwards means redoing every run.
   The `think` setting only matters for gemma4:e4b. Setup check, one sample each on the invented warm-up ticket,
   not official:
   thinking on (baseline) → 22.1 s, 295 generated tokens; `think=false` → 0.6 s warm, 8 tokens; same answer both times.
   Thinking on matches the Step 4 prediction basis (35–45 s). Turning it off is an obvious Assignment 2
   optimisation. To change it: `OLLAMA_THINK=false` in `.env`, then `switch_model.ps1`.
5. **How the accuracy score counts 502s** (no category) must be decided by P3 in advance.
6. **Wi-Fi.** University Wi-Fi often blocks laptop-to-laptop traffic. Test `Test-NetConnection <SUT-IP> -Port 8000`
   early. A phone hotspot or a small router is the fallback. Record whichever network is used.
7. **Code location.** This baseline is on branch `p1/sut-infra` (from `dev`); the frozen golden set and prediction
   record are on `main`. Merge without touching `datasets/`.
8. **For Slide 5 (FYI).** All four pulled digests match the Step 4 short IDs. The default tags use different
   quantisations: llama3.2:1b Q8_0, phi3:3.8b Q4_0, mistral:7b Q4_K_M, gemma4:e4b Q4_K_M (8.0B, 8.95 GB).
   This affects speed and accuracy, so mention it next to the digests.

Observations for P5's bottleneck analysis. These are not fixes; the baseline stays unoptimised.

- `POST /tickets` is a sync endpoint: FastAPI runs it on a ~40-thread pool. Under load, up to ~40 requests
  wait inside the service while Ollama (NUM_PARALLEL=1) serves one at a time. The rest queue in Ollama (max 512).
- `GET /search` shares that thread pool, so heavy ticket load can delay searches even though search never calls the model.
- `GET /search` scans the whole `tickets` table (`LIKE '%q%'`) and returns every full narrative. It slows down as a run stores more tickets.
- Ollama (llama.cpp) reuses the processed instruction prefix of the previous prompt. The service caches
  nothing, but Ollama itself processes only the new ticket text. Example from the setup smoke test
  (llama3.2:1b): the first ticket's prompt took 1,482 ms, the next one 179 ms for a similar-length prompt.
  `prompt_tokens` in the log still counts the whole prompt; `prompt_eval_ms` shows the real work. The warm-up
  pays the one-off cost, so every run starts in the same state. Disclose this on the architecture slide.
