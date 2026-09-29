#!/usr/bin/env python3
"""Per-run JMeter latency, throughput and error stats, and their mean and spread across each configuration's runs."""
import argparse
from collections import defaultdict

from reconcile import reconcile
from runlib import (
    MIN_RUNS, OUTPUT_DIR, fmt_spread, latency_stats, load_exclusions, load_runs, md_table, read_jtl, spread,
    write_csv,
)

TEST_TYPES = {"load", "stress"}
METRICS = ["samples", "ok", "error_pct", "ok_per_hour", "mean_ms", "p50_ms", "p90_ms", "p95_ms", "p99_ms", "max_ms"]
REPORT_COLUMNS = [  # (metric, heading, decimals) shown in the markdown report
    ("ok_per_hour", "OK req/hour", 0), ("error_pct", "Error %", 1), ("mean_ms", "Mean ms", 0),
    ("p50_ms", "p50 ms", 0), ("p95_ms", "p95 ms", 0), ("p99_ms", "p99 ms", 0),
]


def run_stats(samples) -> tuple[float, dict[str, dict]]:
    """Run duration and per-label stats; latency covers successful samples, failures count toward error_pct."""
    start = min(s.start_ms for s in samples)
    end = max(s.start_ms + s.elapsed_ms for s in samples)
    hours = (end - start) / 3_600_000
    by_label = defaultdict(list)
    for s in samples:
        by_label[s.label].append(s)
    stats = {}
    for label, group in sorted(by_label.items()):
        ok = [s.elapsed_ms for s in group if s.success]
        stats[label] = {
            "samples": len(group),
            "ok": len(ok),
            "error_pct": 100 * (len(group) - len(ok)) / len(group),
            "ok_per_hour": len(ok) / hours if hours else None,
            **latency_stats(ok),
        }
    return (end - start) / 1000, stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="*", help="run IDs or folders (default: every finished load/stress run)")
    args = parser.parse_args()

    excluded = load_exclusions()
    run_rows, groups = [], defaultdict(list)
    for run in load_runs(TEST_TYPES, args.runs):
        if run.run_id in excluded:
            print(f"-- {run.run_id}: excluded ({excluded[run.run_id]})")
            continue
        jtl = run.find("*.jtl")
        if not jtl:
            print(f"!! {run.run_id}: no .jtl in the run folder - skipped")
            continue
        samples, _ = read_jtl(jtl)
        if not samples:
            print(f"!! {run.run_id}: {jtl.name} has no samples - skipped")
            continue
        verdict = reconcile(run).verdict
        if verdict == "FAIL":
            print(f"!! {run.run_id}: reconciliation FAILED - see reconcile.py; exclude or rerun it")
        duration_s, stats = run_stats(samples)
        for label, m in stats.items():
            run_rows.append({"run_id": run.run_id, "group": run.group, "model": run.info.get("model"),
                             "test_type": run.info.get("test_type"), "config": run.info.get("config"),
                             "run": run.number, "reconciliation": verdict, "duration_s": duration_s,
                             "label": label, **m})
        groups[run.group].append((run, stats))

    if not groups:
        print("No load/stress runs with a .jtl yet.")
        return

    summary_rows = []
    md = ["# Load test summary", "",
          f"Each cell: mean ± SD (min–max) across the configuration's runs; SD is the sample SD (n-1). "
          f"Latency is JMeter `elapsed` of successful samples; failed samples count toward Error %. "
          f"Percentiles interpolate linearly (Excel PERCENTILE.INC). OK req/hour = successful samples / run duration.",
          ""]
    for group, entries in groups.items():
        runs = [run for run, _ in entries]
        md += [f"## {group}", "",
               f"Runs: {', '.join(r.run_id.rsplit('_', 1)[1] for r in runs)}"
               + ("" if len(runs) >= MIN_RUNS else f" - **only {len(runs)} run(s); {MIN_RUNS} required**"), ""]
        if len(runs) < MIN_RUNS:
            print(f"!! {group}: only {len(runs)} run(s) - a single run is not a measurement ({MIN_RUNS} required)")
        labels = sorted({label for _, stats in entries for label in stats})
        table = []
        for label in labels:
            spreads = {}
            for metric in METRICS:
                values = [stats.get(label, {}).get(metric) for _, stats in entries]
                spreads[metric] = spread(values)
                summary_rows.append({"group": group, "label": label, "metric": metric, "n_runs": len(runs),
                                     **{f"run{r.number}": v for r, v in zip(runs, values)}, **spreads[metric]})
            table.append([label] + [fmt_spread(spreads[m], digits) for m, _, digits in REPORT_COLUMNS])
        md += [md_table(["Request"] + [h for _, h, _ in REPORT_COLUMNS], table), ""]

    write_csv(OUTPUT_DIR / "load_runs.csv", run_rows)
    write_csv(OUTPUT_DIR / "load_summary.csv", summary_rows)
    (OUTPUT_DIR / "load_summary.md").write_text("\n".join(md), encoding="utf-8")
    print(f"Wrote load_runs.csv, load_summary.csv and load_summary.md to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
