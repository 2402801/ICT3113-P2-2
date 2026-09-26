# ICT3113-P2-2 — Ticket Triage Service

Assignment 1 baseline: a synchronous ticket triage web service plus a separate load generator that
plays the role of the complaint intake.

## Layout

- `server/` — FastAPI web service. `POST /tickets`, `GET /search`, `GET /stats`, `GET /health`.
  Classifies each ticket with one blocking call to Ollama (`classifier.py`, fixed prompt in
  `prompt.py`), stores the ticket + assigned category in MySQL, and records per-request latency in a
  `request_metrics` table and in `server/logs/access.log` (with Ollama's timing breakdown).
  Classification is synchronous — the response to `POST /tickets` doesn't return until classification
  is done. No caching, queuing or batching.
- `load-generator/` — Apache JMeter test plan (`load_test.jmx`) modelling the Tier A workload: ticket
  intake (`POST /tickets`, thread count simulating one or more "load machines") and staff ticket lookups
  (`GET /search?q=...`), each cycling through an off-peak → peak → off-peak phase sequence. `prepare_data.py`
  converts the dataset CSV into a JMeter-friendly input file first.
- `Dataset/` — the raw dataset CSV. This is never loaded into the service directly; it's only read by
  the load generator, which submits tickets one at a time exactly as a real intake would.
- `docker-compose.yml` — brings up MySQL, Ollama (CPU only, pinned version) and the server together.
- `scripts/p1/` + `docs/P1_SUT_RUNBOOK.md` — operating the official SUT laptop: model switching,
  per-run warm-up/reset/log archiving into `runs/`, preflight checks, environment evidence.

## Running the service

```bash
docker compose up -d --build
```

This starts:
- `mysql` on 127.0.0.1:3306 (db `triage`, user/pass `triage`/`triage`)
- `ollama` on 127.0.0.1:11434 (CPU only)
- `server` (the Ticket Triage Service) on port 8000

The model is chosen by `OLLAMA_MODEL` (default `llama3.2:1b`; set it in `.env`, or use
`scripts/p1/switch_model.ps1`). Pull the candidate models once with
`powershell -ExecutionPolicy Bypass -File scripts\p1\pin_models.ps1 -Pull`.

Health check (also shows which model is live):

```bash
curl http://localhost:8000/health
```

## API

- `POST /tickets` — body `{"narrative": "..."}`, returns `{id, category, narrative, classification_latency_ms}`
- `GET /search?q=...` — returns tickets whose narrative contains `q`
- `GET /stats` — returns ticket counts per category
- `GET /health` — returns `{status, model, prompt_version, think}`

## Running the load generator (JMeter)

1. Convert dataset rows into JMeter's input format (one JSON request body per line):

   ```bash
   cd load-generator
   python prepare_data.py --csv ../Dataset/ict3113_tickets_2000_2999.csv --output data/tickets.jsonl
   ```

2. Run the test plan. Locally with JMeter installed:

   ```bash
   jmeter -n -t load_test.jmx \
     -Jhost=localhost -Jport=8000 \
     -Jthreads=4 \
     -Jdata_file=data/tickets.jsonl
   ```

   Or via the bundled Docker image (build once with `docker build -t triage-jmeter .`), joined to the
   same compose network so it can resolve the `server` service by name:

   ```bash
   docker run --rm --network ict3113-p2-2_default \
     -v "$(pwd)/results:/load-generator/results" \
     -v "$(pwd)/data:/load-generator/data" \
     triage-jmeter -t load_test.jmx -Jhost=server -Jport=8000 -Jthreads=4 -Jdata_file=data/tickets.jsonl
   ```

   On Windows/Git Bash, prefix `docker run` with `MSYS_NO_PATHCONV=1` so the `-v` paths aren't mangled.

`-Jthreads` sets how many concurrent workers post tickets (simulating multiple load machines);
`-Jsearch_threads` sets concurrent staff searchers; `-Jhost`/`-Jport`/`-Jprotocol` point at the server.
Both `data/tickets.jsonl` and `data/search_terms.csv` are read on a loop (`recycle=true`), so a phase
keeps sending at its target rate for its full duration regardless of file length.

### Workload model (Tier A)

The test plan is built from Step 3's Tier A ticket-volume model (~5.5 tickets/hour off-peak, ~2.5x
during a peak/billing window, ~2 staff searches per ticket) rather than firing requests as fast as
possible. It runs three phases in sequence — off-peak → peak → off-peak — with `POST /tickets` and
`GET /search` traffic running concurrently within each phase, paced by a Constant Throughput Timer:

| Property | Default | Meaning |
| --- | --- | --- |
| `tickets_per_hour_offpeak` | `5.5` | Tier A off-peak ticket intake rate |
| `peak_multiplier` | `2.5` | Peak-to-average ratio (billing-cycle window) |
| `search_k` | `2` | Staff searches per ticket (duplicate checks, audits, re-routing) |
| `time_unit_seconds` | `60` | Real seconds per simulated hour — `60` compresses the model to minutes for testing; set to `3600` to run at real wall-clock pace |
| `offpeak_duration_sec` | `120` | Length of each off-peak phase (real test seconds) |
| `peak_duration_sec` | `180` | Length of the peak phase (real test seconds) |

With the defaults, the full off-peak/peak/off-peak cycle takes 7 minutes and sends tickets at ~5.5/min
off-peak and ~13.75/min at peak (with staff search running in parallel at 2x those rates). To validate
against the real per-hour numbers from the workload model doc, rerun with `-Jtime_unit_seconds=3600`.

Results land in `results/results.jtl` (per-request timestamp, latency, status, label — `POST /tickets`
vs `GET /search`). Server-side request latency for the same traffic is available in the
`request_metrics` table in MySQL, and per-ticket classification latency is stored on each row in
`tickets`.
