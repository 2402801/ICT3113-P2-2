#!/usr/bin/env python3
"""Per-run numbers for the A2 speed test, from the raw files only (so every figure traces to a .jtl or a log).

  python scripts/a2/run_summary.py --run-dir runs/<run-id>          # uses every file it finds in the folder
  python scripts/a2/run_summary.py --jtl x.jtl                      # client side only (P2, before the logs exist)

Looks in the run folder for: *.jtl, server_access.log, stats_before.json, stats_after.json.
Writes <run-dir>/speed_summary.json when --run-dir is given. p95 is NOT computed here: it is pooled over three runs
by P4. No p99.
"""
import argparse
import csv
import json
import re
import statistics
from pathlib import Path

KV = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)')
LINE = re.compile(r"^\S+ POST /tickets (\d{3}) ")


def jtl_summary(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8", newline="")))
    ok = [r for r in rows if r["success"].lower() == "true"]
    elapsed = sorted(int(r["elapsed"]) for r in ok)
    out = {"jtl": Path(path).name, "sent": len(rows), "completed_ok": len(ok), "errored": len(rows) - len(ok)}
    if rows:
        start = min(int(r["timeStamp"]) for r in rows)
        end = max(int(r["timeStamp"]) + int(r["elapsed"]) for r in rows)
        out["window_s"] = round((end - start) / 1000, 1)
        out["throughput_per_s"] = round(len(ok) / ((end - start) / 1000), 5) if end > start else None
        out["error_rate"] = round((len(rows) - len(ok)) / len(rows), 4)
    if elapsed:
        out["p50_ms"] = statistics.median(elapsed)
        out["mean_ms"] = round(statistics.mean(elapsed), 1)
        out["min_ms"], out["max_ms"] = elapsed[0], elapsed[-1]
    return out


def log_summary(path):
    total = esc = 0
    finals = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        m = LINE.match(line)
        if not m or m.group(1) != "200":
            continue
        fields = {k: v.strip('"') for k, v in KV.findall(line)}
        total += 1
        if fields.get("escalated") == "1":
            esc += 1
        if "final_model" in fields:
            finals[fields["final_model"]] = finals.get(fields["final_model"], 0) + 1
    out = {"log_post_tickets_200": total, "log_escalated": esc, "final_model_counts": finals}
    out["escalation_fraction"] = round(esc / total, 4) if total else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir")
    ap.add_argument("--jtl")
    ap.add_argument("--out", help="output file (default: <run-dir>/speed_summary.json)")
    args = ap.parse_args()
    summary = {}
    jtl = args.jtl
    if args.run_dir:
        d = Path(args.run_dir)
        summary["run_id"] = d.name
        found = sorted(d.glob("*.jtl"))
        jtl = jtl or (str(found[0]) if found else None)
        if (d / "server_access.log").exists():
            summary.update(log_summary(d / "server_access.log"))
        if (d / "stats_before.json").exists() and (d / "stats_after.json").exists():
            b = json.load(open(d / "stats_before.json"))["total"]
            a = json.load(open(d / "stats_after.json"))["total"]
            summary["stats_before"], summary["stats_after"], summary["completed_and_stored"] = b, a, a - b
    if jtl:
        summary.update(jtl_summary(jtl))
        if "completed_and_stored" in summary:
            summary["unfinished"] = summary["sent"] - summary["completed_and_stored"]
    print(json.dumps(summary, indent=2))
    out = args.out or (str(Path(args.run_dir) / "speed_summary.json") if args.run_dir else None)
    if out:
        Path(out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
