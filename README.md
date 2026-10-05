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
     -Jrun_id=my-run-01 \
     -Jdata_file=data/tickets.jsonl
   ```

   Or via the bundled Docker image (build once with `docker build -t triage-jmeter .`), joined to the
   same compose network so it can resolve the `server` service by name:

   ```bash
   docker run --rm --network ict3113-p2-2_default \
     -v "$(pwd)/results:/load-generator/results" \
     -v "$(pwd)/data:/load-generator/data" \
     triage-jmeter -t load_test.jmx -Jhost=server -Jport=8000 -Jrun_id=my-run-01 -Jdata_file=data/tickets.jsonl
   ```

   On Windows/Git Bash, prefix `docker run` with `MSYS_NO_PATHCONV=1` so the `-v` paths aren't mangled.

`-Jhost`/`-Jport`/`-Jprotocol` point at the server.
Both `data/tickets.jsonl` and `data/search_terms.csv` are read on a loop (`recycle=true`), so a phase
keeps sending at its target rate for its full duration regardless of file length.

### Workload model (open-loop)

The plan is open-loop: it uses Open Model Thread Groups, so requests arrive at a fixed (Poisson) rate whether or
not earlier requests have finished. A slow server builds a backlog instead of slowing the load. Three phases run in
sequence (off-peak, peak, off-peak), with `POST /tickets` and `GET /search` running side by side in each:

| Property | Default | Meaning |
| --- | --- | --- |
| `tickets_per_hour_tr1` | `1312` | Step 4 TR-1 ticket rate (off-peak phases), real tickets/hour |
| `tickets_per_hour_tr2` | `3936` | Step 4 TR-2 ticket rate (peak phase), real tickets/hour |
| `search_k` | `2` | Staff searches per ticket |
| `offpeak_duration_sec` | `120` | Length of each off-peak phase |
| `peak_duration_sec` | `180` | Length of the peak phase |
| `response_timeout_ms` | `630000` | Client wait per request: the service's 600 s limit on its Ollama call, plus 30 s |
| `run_id` | `norun` | Sent as the `X-Run-Id` header on every request; always pass it |

Rates are real per-hour rates (no time compression), so short phases send few requests: 1,312/hour is about 0.36
per second. Lengthen the phases for a meaningful sample. Threads are not a setting: the Open Model group starts one
per arrival, so a 600 s ticket keeps its thread for the whole wait.

The 630 s timeout lets JMeter see every answer the service gives itself (200, or 502 when its 600 s Ollama limit
fires). It does not cap total server time: the 600 s starts only once a request gets one of the service's 40 threads,
so under a backlog a request can queue for a thread first and pass 630 s. JMeter records that as a timeout error while
the service still finishes and stores the ticket; `analysis/reconcile.py` pairs these by start time. The cap is
deliberate: without it an overloaded run could keep draining for hours after the last arrival.

Every schedule ends with a drain pause of connect + response timeout (635 s). JMeter interrupts a group's
in-flight requests the moment its schedule ends, which would record every ticket still waiting on the model as a
"Socket closed" error. So a run always lasts the three phases plus 635 s (about 17.6 minutes with the defaults), even
if the service answers everything early.

Each run writes `results/<run_id>-<yyyyMMdd-HHmmss>.jtl` (override with `-Jjtl=`), so runs never append to one
file. Server-side request latency is in the `request_metrics` table in MySQL, and per-ticket classification latency
is stored on each row in `tickets`.
