# ICT3113-P2-2 — Ticket Triage Service

Assignment 1 baseline: a synchronous ticket triage web service plus a separate load generator that
plays the role of the complaint intake.

## Layout

- `server/` — FastAPI web service. `POST /tickets`, `GET /search`, `GET /stats`. Classifies each
  ticket (currently via a placeholder classifier — not yet wired to Ollama), stores the ticket +
  assigned category in MySQL, and records per-request latency in a `request_metrics` table.
  Classification is synchronous — the response to `POST /tickets` doesn't return until classification
  is done.
- `load-generator/` — Apache JMeter test plan (`load_test.jmx`) that POSTs ticket narratives to the
  server's `/tickets` endpoint one at a time, with the thread count simulating one or more "load
  machines". `prepare_data.py` converts the dataset CSV into a JMeter-friendly input file first.
- `Dataset/` — the raw dataset CSV. This is never loaded into the service directly; it's only read by
  the load generator, which submits tickets one at a time exactly as a real intake would.
- `docker-compose.yml` — brings up MySQL and the server together. Ollama is defined too but sits behind
  the `llm` profile since the classifier doesn't call it yet — bring it up separately once that's wired.

## Running the service

```bash
docker compose up --build
```

This starts:
- `mysql` on port 3306 (db `triage`, user/pass `triage`/`triage`)
- `server` (the Ticket Triage Service) on port 8000

To also start Ollama (once the classifier is wired up to use it):

```bash
docker compose --profile llm up --build
```

Health check:

```bash
curl http://localhost:8000/health
```

## API

- `POST /tickets` — body `{"narrative": "..."}`, returns `{id, category, narrative, classification_latency_ms}`
- `GET /search?q=...` — returns tickets whose narrative contains `q`
- `GET /stats` — returns ticket counts per category

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
`-Jhost`/`-Jport`/`-Jprotocol` point at the server. Each thread works through `data/tickets.jsonl`
until it runs out, so total requests sent = number of rows in that file, regardless of thread count.

Results land in `results/results.jtl` (per-request timestamp, latency, status). Server-side request
latency for the same traffic is available in the `request_metrics` table in MySQL, and per-ticket
classification latency is stored on each row in `tickets`.
