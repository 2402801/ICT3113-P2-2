#!/usr/bin/env python3
"""Checks that each run's client record (.jtl or accuracy CSV) reconciles with its server log and DB export."""
import argparse
import sys
from collections import Counter
from dataclasses import dataclass, field

from runlib import (
    OUTPUT_DIR, ClientSample, Run, accuracy_samples, load_exclusions, load_runs, percentile,
    read_accuracy_rows, read_jtl, read_mysql_tsv, read_server_log, write_csv,
)

TEST_TYPES = {"load", "stress", "accuracy"}
TIME_MATCH_TOLERANCE_MS = 2000  # start-time distance allowed when pairing a no-response client sample
HANDLER_STATUSES = {200, 502}  # statuses for which the endpoint itself writes a request_metrics row


@dataclass
class Result:
    run_id: str
    source: str = ""
    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def verdict(self) -> str:
        return "FAIL" if self.fails else "WARN" if self.warns else "PASS"


def client_record(run: Run) -> tuple[str, list[ClientSample], bool]:
    """The tester's raw output: a JMeter .jtl or the accuracy runner's CSV."""
    jtl, acc = run.find("*.jtl"), run.find("*_accuracy.csv")
    if jtl and acc:
        raise ValueError(f"both {jtl.name} and {acc.name} present - one client record per run")
    if jtl:
        samples, has_req_id = read_jtl(jtl)
        return jtl.name, samples, has_req_id
    if acc:
        return acc.name, accuracy_samples(read_accuracy_rows(acc)), True
    return "", [], False


def summarize(counter: Counter, limit: int = 5) -> str:
    return ", ".join(f"{k} x{v}" for k, v in counter.most_common(limit))


def reconcile(run: Run) -> Result:
    res = Result(run.run_id)
    try:
        res.source, client, has_req_id = client_record(run)
        server = read_server_log(run.path / "server_access.log")
    except ValueError as exc:
        res.fails.append(str(exc))
        return res
    if not res.source:
        res.fails.append("no client record: copy the tester's .jtl or *_accuracy.csv into the run folder")
        return res
    res.stats.update(client_samples=len(client), server_lines=len(server))

    foreign = Counter(s.run for s in server if s.run not in ("-", run.run_id))
    if foreign:
        res.fails.append(f"server log has traffic tagged for other runs: {summarize(foreign)}")
    untagged = sum(1 for s in server if s.run == "-" and s.label != "GET /health")
    if untagged:
        res.warns.append(f"{untagged} requests arrived without X-Run-Id (run JMeter with -Jrun_id=<run-id>)")

    if has_req_id:
        match_by_req_id(res, client, server)
    else:
        res.warns.append("no req_id column in the .jtl (run JMeter with -Jsample_variables=req_id): compared counts only")
        compare_counts(res, client, server)

    check_database(res, run, server)
    return res


def match_by_req_id(res: Result, client: list[ClientSample], server: list) -> None:
    """Pairs each client sample with its server line via X-Request-ID, then pairs no-response samples by time."""
    unpaired_server = {s.req_id: s for s in server}
    pairs, unpaired_client = [], []
    for c in client:
        s = unpaired_server.pop(c.req_id, None) if c.req_id else None
        if s is None:
            unpaired_client.append(c)
        else:
            pairs.append((c, s))

    status_mismatch = [(c, s) for c, s in pairs if c.status != str(s.status)]
    if status_mismatch:
        res.fails.append(f"{len(status_mismatch)} paired requests disagree on HTTP status "
                         f"(client/server: {summarize(Counter(f'{c.status}/{s.status}' for c, s in status_mismatch))})")
    category_mismatch = [c for c, s in pairs if c.category and c.category != s.fields.get("category")]
    if category_mismatch:
        res.fails.append(f"{len(category_mismatch)} tickets recorded with a different category than the server logged")

    label_map = {}
    for (client_label, server_label), _ in Counter((c.label, s.label) for c, s in pairs).most_common():
        label_map.setdefault(client_label, server_label)
    # Positive offset = server clock ahead of the load generator (plus one-way network time).
    offset = percentile(sorted(s.start_ms - c.start_ms for c, s in pairs), 50) or 0.0
    gaps = sorted(c.elapsed_ms - s.latency_ms for c, s in pairs)
    res.stats.update(paired_req_id=len(pairs), clock_offset_ms=offset,
                     gap_p50_ms=percentile(gaps, 50), gap_p95_ms=percentile(gaps, 95))
    negative = sum(1 for g in gaps if g < -5)
    if negative:
        res.warns.append(f"{negative} paired requests took less time at the client than at the server")

    # A client that gave up (timeout) or got a bare 500 has no X-Request-ID: pair it with the nearest start time.
    late = []
    for c in sorted((c for c in unpaired_client if not c.req_id), key=lambda c: c.start_ms):
        want = label_map.get(c.label, c.label)
        candidates = [s for s in unpaired_server.values()
                      if s.label == want and abs(s.start_ms - offset - c.start_ms) <= TIME_MATCH_TOLERANCE_MS]
        if candidates:
            s = min(candidates, key=lambda s: abs(s.start_ms - offset - c.start_ms))
            del unpaired_server[s.req_id]
            late.append((c, s))
    late_ids = {id(c) for c, _ in late}
    res.stats["paired_time"] = len(late)
    if late:
        worst = max(s.latency_ms for _, s in late) / 1000
        res.warns.append(f"{len(late)} requests failed at the client but were completed by the service "
                         f"({summarize(Counter(f'{c.label}: {c.status} -> {s.status}' for c, s in late))}; "
                         f"slowest server time {worst:.1f} s) - client timeout shorter than the service's")

    lost_with_id = [c for c in unpaired_client if c.req_id]
    if lost_with_id:
        res.fails.append(f"{len(lost_with_id)} client samples carry a req_id that is not in the server log")
    lost = [c for c in unpaired_client if not c.req_id and id(c) not in late_ids]
    if lost:
        res.warns.append(f"{len(lost)} client errors never reached the service log: "
                         f"{summarize(Counter(c.message or c.status for c in lost))}")
    res.stats["client_unpaired"] = len(lost_with_id) + len(lost)

    health = [s for s in unpaired_server.values() if s.label == "GET /health"]
    other = [s for s in unpaired_server.values() if s.label != "GET /health"]
    if health:
        res.notes.append(f"{len(health)} GET /health not in the client record (P1 readiness / manual checks)")
    if other:
        res.fails.append(f"{len(other)} server requests are not in the client record: "
                         f"{summarize(Counter(f'{s.label} {s.status}' for s in other))}")
    res.stats["server_unpaired"] = len(other)


def compare_counts(res: Result, client: list[ClientSample], server: list) -> None:
    """Fallback without req_id: every client sample must have one server line with the same label."""
    client_counts = Counter(c.label for c in client)
    server_counts = Counter(s.label for s in server if s.label != "GET /health" or s.label in client_counts)
    if client_counts != server_counts:
        labels = sorted(set(client_counts) | set(server_counts))
        res.fails.append("request counts differ (label: client/server): "
                         + ", ".join(f"{k}: {client_counts[k]}/{server_counts[k]}" for k in labels))


def check_database(res: Result, run: Run, server: list) -> None:
    """Stored tickets and metric rows must match what the server log says it handled."""
    tickets_path = run.path / "tickets.tsv"
    if not tickets_path.exists():
        res.warns.append("no tickets.tsv (finish_run.ps1 exports it)")
    else:
        stored = {r["id"]: r["category"] for r in read_mysql_tsv(tickets_path)}
        logged = {s.fields.get("ticket_id"): s.fields.get("category")
                  for s in server if s.label == "POST /tickets" and s.status == 200}
        res.stats["tickets_db"] = len(stored)
        if stored.keys() != logged.keys():
            diff = sorted(stored.keys() ^ logged.keys(), key=lambda i: int(i) if str(i).isdigit() else 0)
            res.fails.append(f"tickets.tsv holds {len(stored)} tickets, the server log stored {len(logged)} "
                             f"(ids in only one: {diff[:10]})")
        elif any(stored[i] != logged[i] for i in stored):
            res.fails.append("tickets.tsv and the server log disagree on some tickets' categories")

    metrics_path = run.path / "request_metrics.tsv"
    if metrics_path.exists():
        db = Counter((r["endpoint"], int(r["status_code"])) for r in read_mysql_tsv(metrics_path))
        log = Counter((s.path, s.status) for s in server if s.path != "/health" and s.status in HANDLER_STATUSES)
        if db != log:
            res.warns.append(f"request_metrics.tsv differs from the server log: db {dict(db)} vs log {dict(log)}")


def print_result(res: Result, excluded_reason: str | None) -> None:
    tag = f"  (excluded: {excluded_reason})" if excluded_reason else ""
    print(f"\n== {res.run_id}  [{res.verdict}]  {res.source}{tag}")
    st = res.stats
    if "paired_req_id" in st:
        print(f"   client {st['client_samples']} samples | server {st['server_lines']} lines | "
              f"{st['paired_req_id']} paired by req_id, {st['paired_time']} by time | "
              f"clock offset {st['clock_offset_ms']:+.0f} ms | client-server gap p50 "
              f"{st['gap_p50_ms'] or 0:.0f} ms, p95 {st['gap_p95_ms'] or 0:.0f} ms")
    for label, items in (("FAIL", res.fails), ("WARN", res.warns), ("note", res.notes)):
        for item in items:
            print(f"   {label}: {item}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="*", help="run IDs or folders (default: every finished load/stress/accuracy run)")
    args = parser.parse_args()

    excluded = load_exclusions()
    results = []
    for run in load_runs(TEST_TYPES, args.runs):
        res = reconcile(run)
        print_result(res, excluded.get(run.run_id))
        results.append(res)
    if not results:
        sys.exit("No finished runs to reconcile.")

    write_csv(OUTPUT_DIR / "reconciliation.csv", [
        {"run_id": r.run_id, "verdict": r.verdict, "excluded": excluded.get(r.run_id, ""), "client_record": r.source,
         **r.stats, "fails": " | ".join(r.fails), "warns": " | ".join(r.warns)}
        for r in results
    ])
    failed = [r.run_id for r in results if r.verdict == "FAIL" and r.run_id not in excluded]
    print(f"\n{len(results)} run(s) checked, {len(failed)} failed. Wrote {OUTPUT_DIR / 'reconciliation.csv'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
