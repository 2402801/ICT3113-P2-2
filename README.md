# ICT3113-P2-2 — Ticket Triage Service

Assignment 1 baseline: a synchronous ticket triage web service plus a separate load generator that
plays the role of the complaint intake. The repository also holds the test plans, playbooks, run evidence and
analysis for the Assignment 1 load, stress and accuracy tests.

## Layout

```
server/              the ticket triage service (system under test)
docker-compose.yml   MySQL + Ollama + server
datasets/            golden test set, labelling files, Prediction Record
docs/                load, stress and accuracy test playbooks
tests/
  load/              load test plan
  stress/            stress test plans, data and baseline
  accuracy/          accuracy test client, scoring and figures
  environment/       test environment records and model pins
load-generator/      JMeter input preparation and search terms
scripts/             SUT run tooling and environment recorders
runs/                evidence from every recorded run
analysis/            reconciliation, requirement verdicts, load statistics
```

- `server/` — FastAPI web service. `POST /tickets`, `GET /search`, `GET /stats`, `GET /health`.
  Classifies each ticket with one blocking call to Ollama (`classifier.py`, fixed prompt in
  `prompt.py`), stores the ticket + assigned category in MySQL, and records per-request latency in a
  `request_metrics` table and in `server/logs/access.log` (with Ollama's timing breakdown).
  Classification is synchronous — the response to `POST /tickets` doesn't return until classification
  is done. No caching, queuing or batching.
- `docker-compose.yml` — brings up MySQL, Ollama (CPU only, pinned version) and the server together.
- `datasets/` — `golden_test_set.csv` (the 175 labelled tickets the accuracy test uses), each annotator's
  `combined_175_tickets_*` files, `labelling_protocol_v3.md` and `PredictionRecord.pdf`. The course dataset
  extract (rows 2000–2999) that the load generator reads is not stored here. Tickets never reach the service
  directly from a dataset; a load generator or test client submits them one at a time, as a real intake would.
- `docs/` — the test playbooks. [`LOAD_TEST_PLAYBOOK.md`](docs/LOAD_TEST_PLAYBOOK.md): how the 36 official load
  runs were done, and how to operate the SUT laptop for every test type.
  [`stress-test-playbook.md`](docs/stress-test-playbook.md) and [`ACCURACY_PLAYBOOK.md`](docs/ACCURACY_PLAYBOOK.md):
  the stress and accuracy tests.
- `tests/load/` — `load_test.jmx`, the open-loop JMeter plan (see [Workload model](#workload-model-open-loop)).
- `tests/stress/` — `stress-test-plan.jmx` (gemma4:e4b ramp), `5-single-request-latency-test-plan.jmx` and its
  result `baseline.jtl`, and the 100 request bodies in `data/tickets.jsonl`.
- `tests/accuracy/` — `accuracy_test.py` sends the golden set to the service, `accuracy_report.py` scores the runs,
  `accuracy_figures.py` draws the slide figures.
- `tests/environment/` — SUT and load-generator environment records for Slide 7 (`p1_sut_environment.md`,
  `loadgen_environment*.md`) and the pinned model digests (`model_pins.json`).
- `load-generator/` — `prepare_data.py` converts the dataset CSV into JMeter's input file (`data/tickets.jsonl`,
  generated, not committed); `data/search_terms.csv` holds the 17 search terms. The `Dockerfile` builds a JMeter
  image; it was never used for official runs, because JMeter must not run on the SUT.
- `scripts/` — `p1/` operates the official SUT laptop: preflight checks, model switching, per-run warm-up/reset
  (`prepare_run.ps1`) and log/database archiving into `runs/` (`finish_run.ps1`), environment evidence.
  `record_loadgen_environment.ps1` records the load-generator laptop; `run_accuracy_suite.ps1` runs the accuracy
  test unattended.
- `runs/` — one folder per run, named `<model>_<test-type>_<config>_run<n>`: the client record (`.jtl` or accuracy
  CSV), server log, database export, Ollama log and `run_info.json`. `run_register.csv` indexes every run.
- `analysis/` — `reconcile.py` checks each run's client record against the server log and database export,
  `requirements_matrix.py` gives the requirement verdicts, `load_summary.py` the per-run and per-configuration
  load statistics. `excluded_runs.csv` lists invalidated runs with the reason. Results go to `analysis/output/`.

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

Official runs follow [`docs/LOAD_TEST_PLAYBOOK.md`](docs/LOAD_TEST_PLAYBOOK.md), with JMeter on a
separate laptop from the service. The basic steps:

1. Convert dataset rows into JMeter's input format (one JSON request body per line):

   ```bash
   cd load-generator
   python prepare_data.py --csv <path>/ict3113_tickets_2000_2999.csv --output data/tickets.jsonl
   ```

2. Run the test plan from `tests/load/`, pointing it at the input files in `load-generator/data/`:

   ```bash
   cd tests/load
   jmeter -n -t load_test.jmx \
     -Jhost=<SUT-IP> -Jport=8000 \
     -Jrun_id=my-run-01 -Jsample_variables=req_id \
     -Jdata_file=../../load-generator/data/tickets.jsonl \
     -Jsearch_file=../../load-generator/data/search_terms.csv
   ```

`-Jhost`/`-Jport`/`-Jprotocol` point at the server. `-Jsample_variables=req_id` saves each response's
`X-Request-ID` in the `.jtl`, so `analysis/reconcile.py` can pair it with the server log line.
Both `tickets.jsonl` and `search_terms.csv` are read on a loop (`recycle=true`), so a phase
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

The official load runs override some of these (90 s / 120 s / 90 s phases at one steady rate, 295 s timeout); the
exact flags per configuration are in the load test playbook, section 4, step 2.

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
file; copy it into `runs/<run-id>/` for a recorded run. Server-side request latency is in the `request_metrics`
table in MySQL, and per-ticket classification latency is stored on each row in `tickets`.
