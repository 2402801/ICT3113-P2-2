#!/usr/bin/env python3
"""Step 6 evidence: each requirement (RR-1, RR-2, TR-1, TR-2, AR-1, AR-2, AR-3) evaluated per candidate model.

Load metrics come from the kept .jtl files of every load run not listed in excluded_runs.csv. By default only
requests sent after the first 120 s of each run are counted (the warm-up exclusion in RR-1's measurement text);
the same metrics over all samples are written alongside so the effect of the exclusion is visible.
Accuracy comes from analysis/output/accuracy_runs.csv, i.e. the runs chosen by accuracy/accuracy_report.py.

Writes analysis/output/requirements_matrix.md and requirements_matrix_load.csv.
"""
import argparse
import csv
import io
import statistics
from collections import Counter, defaultdict

from runlib import (
    OUTPUT_DIR, REPO_ROOT, latency_stats, load_exclusions, load_runs, md_table, percentile, read_jtl,
    read_mysql_tsv, read_server_log, spread, write_csv,
)

CLIENT_TIMEOUT_MS = 295_000  # -Jresponse_timeout_ms used in every official load run
DRIFT_LIMIT = 1.5  # second-half median / first-half median at or above this = latency still growing
MODELS = ["llama3.2:1b", "phi3:3.8b", "mistral:7b", "gemma4:e4b"]
AR = {  # requirement -> (minimum recall, categories); AR-3 is overall accuracy
    "AR-1": (0.75, ["Debt collection", "Credit reporting", "Money transfer or service"]),
    "AR-2": (0.90, ["Mortgage", "Consumer loan", "Credit card", "Bank account or service"]),
}
AR3_MIN = 0.85


def window_stats(samples, start_ms):
    """Load metrics for samples sent at or after start_ms; latency percentiles use successful samples only."""
    kept = [s for s in samples if s.start_ms >= start_ms]
    if not kept:
        return None
    ok = sorted(s.elapsed_ms for s in kept if s.success)
    # p95 over every request: a failure (error or timeout) counts as slower than any success
    all_sorted = sorted(s.elapsed_ms if s.success else float(10**15) for s in kept)
    first, last_send = min(s.start_ms for s in kept), max(s.start_ms for s in kept)
    last_end = max(s.start_ms + s.elapsed_ms for s in kept)
    mid = first + (last_send - first) / 2
    early = [s.elapsed_ms for s in kept if s.success and s.start_ms < mid]
    late = [s.elapsed_ms for s in kept if s.success and s.start_ms >= mid]
    return {
        "sent": len(kept),
        "ok": len(ok),
        "error_pct": 100 * (len(kept) - len(ok)) / len(kept),
        "sent_per_hour": len(kept) / ((last_send - first) / 3_600_000) if last_send > first else None,
        "ok_per_hour": len(ok) / ((last_end - first) / 3_600_000),
        **latency_stats(ok),
        "p95_all_ms": percentile(all_sorted, 95),
        "drift": statistics.median(late) / statistics.median(early) if early and late else None,
    }


def ms(v, digits=1):
    if v is None:
        return "-"
    if v >= CLIENT_TIMEOUT_MS:
        return "> 295 s"
    return f"{v / 1000:,.{digits}f} s" if v >= 1000 else f"{v:,.0f} ms"


def golden_counts():
    raw = (REPO_ROOT / "datasets" / "golden_test_set.csv").read_bytes().decode("cp1252", errors="replace")
    return Counter(r["final_agreed_label"] for r in csv.DictReader(io.StringIO(raw.lstrip("﻿"))))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warmup-sec", type=int, default=120, help="seconds excluded at the start of each run")
    args = parser.parse_args()
    excluded = load_exclusions()

    # ---- load runs -> per (model, config, label) list of per-run stats, for both windows
    per = defaultdict(lambda: {"window": [], "all": [], "runs": []})
    server = defaultdict(list)  # (model, config) -> per-run server-side counts
    csv_rows = []
    for run in load_runs({"load"}):
        if run.run_id in excluded:
            continue
        samples, _ = read_jtl(run.find("*.jtl"))
        t0 = min(s.start_ms for s in samples)
        model, config = run.info["model"], run.info["config"]
        for label in sorted({s.label for s in samples}):
            mine = [s for s in samples if s.label == label]
            w, a = window_stats(mine, t0 + args.warmup_sec * 1000), window_stats(mine, t0)
            per[(model, config, label)]["window"].append(w)
            per[(model, config, label)]["all"].append(a)
            per[(model, config, label)]["runs"].append(run.run_id)
            for name, st in (("after_warmup", w), ("all_samples", a)):
                csv_rows.append({"run_id": run.run_id, "model": model, "config": config, "label": label,
                                 "window": name, **st})
        log = read_server_log(run.path / "server_access.log")
        tickets = read_mysql_tsv(run.path / "tickets.tsv")
        logged_ok = sum(1 for line in log if line.path == "/tickets" and line.status == 200)
        server[(model, config)].append({
            "run_id": run.run_id,
            "http500": sum(1 for line in log if line.status == 500),
            "http502": sum(1 for line in log if line.status == 502),
            "stored_not_logged": len(tickets) - logged_ok,
        })

    def runs_of(model, config, label, window="window"):
        return [s for s in per[(model, config, label)][window] if s]

    def mean_of(stats, key):
        return spread([s[key] for s in stats])["mean"]

    def worst(stats, key):
        vals = [s[key] for s in stats if s[key] is not None]
        return max(vals) if vals else None

    # ---- requirement verdicts
    verdict, detail = defaultdict(dict), defaultdict(dict)
    for model in MODELS:
        peak = runs_of(model, "tkt-peak", "POST /tickets")
        normal = runs_of(model, "tkt-normal", "POST /tickets")
        search = runs_of(model, "mix-peak", "GET /search")

        ok = all(s["error_pct"] < 1 and s["p95_all_ms"] <= 30_000 for s in peak)
        verdict[model]["RR-1"] = ok
        detail[model]["RR-1"] = (f"p95 {ms(mean_of(peak, 'p95_all_ms'))} (worst run {ms(worst(peak, 'p95_all_ms'))}), "
                                 f"errors {mean_of(peak, 'error_pct'):.1f}%")
        ok = all(s["error_pct"] < 1 and s["p95_all_ms"] <= 500 for s in search)
        verdict[model]["RR-2"] = ok
        detail[model]["RR-2"] = (f"p95 {ms(mean_of(search, 'p95_all_ms'))} (worst run {ms(worst(search, 'p95_all_ms'))}), "
                                 f"errors {mean_of(search, 'error_pct'):.1f}%")
        for req, stats in (("TR-1", normal), ("TR-2", peak)):
            drifts = [s["drift"] for s in stats if s["drift"] is not None]
            drift = max(drifts) if len(drifts) == len(stats) else None
            ok = all(s["error_pct"] < 1 for s in stats) and drift is not None and drift < DRIFT_LIMIT
            verdict[model][req] = ok
            served = sum(s["ok"] for s in stats)
            sent = sum(s["sent"] for s in stats)
            detail[model][req] = (f"{served}/{sent} answered OK, errors {mean_of(stats, 'error_pct'):.1f}%"
                                  + (f", drift x{min(drifts):.2f}-{max(drifts):.2f}" if drift is not None else ""))

    # ---- accuracy (committed accuracy report runs)
    golden = golden_counts()
    acc_rows = list(csv.DictReader(open(OUTPUT_DIR / "accuracy_runs.csv", encoding="utf-8")))
    acc = defaultdict(list)
    for r in acc_rows:
        acc[r["model"]].append(r)
    acc_detail = {}
    for model in MODELS:
        rows = acc[model]
        # accuracy_runs.csv rounds to 3 decimals; go back to whole-ticket counts so means match the report
        overall = [round(float(r["accuracy"]) * int(r["tickets"])) / int(r["tickets"]) for r in rows]
        verdict[model]["AR-3"] = statistics.fmean(overall) >= AR3_MIN
        detail[model]["AR-3"] = (f"{statistics.fmean(overall) * 100:.1f}% "
                                 f"(runs {', '.join(r['run'] for r in rows)}; {min(overall) * 100:.1f}-{max(overall) * 100:.1f}%)")
        acc_detail[model] = {}
        for req, (minimum, cats) in AR.items():
            fails = []
            for c in cats:
                vals = [round(float(r[f"acc_{c}"]) * golden[c]) / golden[c] for r in rows]
                m = statistics.fmean(vals)
                acc_detail[model][c] = (m, min(vals), max(vals))
                if m < minimum:
                    count = m * golden[c]
                    count_txt = f"{count:.0f}" if abs(count - round(count)) < 0.05 else f"{count:.1f}"
                    fails.append(f"{c} {m * 100:.1f}% ({count_txt}/{golden[c]})")
            verdict[model][req] = not fails
            detail[model][req] = "all categories met" if not fails else "below: " + "; ".join(fails)

    # ---- do the accuracy runs (P3's machines) answer like the official SUT? Golden tickets also sent in SUT runs.
    def norm(text):
        return " ".join(text.split())[:200]

    raw = (REPO_ROOT / "datasets" / "golden_test_set.csv").read_bytes().decode("cp1252", errors="replace")
    row_by_text = {norm(r["narrative"]): r["row"] for r in csv.DictReader(io.StringIO(raw.lstrip("﻿")))}
    acc_answers = defaultdict(lambda: defaultdict(set))  # model -> golden row -> categories over the counted runs
    for r in acc_rows:
        run_dir = REPO_ROOT / "runs" / r["run_id"]
        for a in csv.DictReader(open(next(run_dir.glob("*_accuracy.csv")), encoding="utf-8")):
            if a["status"] == "200":
                acc_answers[r["model"]][a["row"]].add(a["predicted"])
    sut_answers = defaultdict(lambda: defaultdict(Counter))  # model -> golden row -> SUT categories
    for run in load_runs({"load", "stress"}):
        if run.run_id in excluded or not (run.path / "tickets.tsv").exists():
            continue
        for t in read_mysql_tsv(run.path / "tickets.tsv"):
            row = row_by_text.get(norm(t.get("narrative", "")))
            if row and t.get("category"):
                sut_answers[run.info["model"]][row][t["category"]] += 1
    agreement = []
    for model in MODELS:
        rows_seen = sut_answers[model]
        same = sum(1 for row, cats in rows_seen.items() if set(cats) == acc_answers[model].get(row, set()))
        agreement.append([model, len(rows_seen), sum(sum(c.values()) for c in rows_seen.values()),
                          f"{same}/{len(rows_seen)}"])

    # ---- single-request latency evidence
    single = {}
    stress = [r for r in load_runs({"stress"}) if r.run_id not in excluded]
    for run in stress:
        samples, _ = read_jtl(run.find("*.jtl"))
        step1 = sorted(s.elapsed_ms for s in samples if s.label.startswith("Step 1") and s.success)
        if step1:
            single["gemma4:e4b stress step 1"] = (len(step1), percentile(step1, 50), percentile(step1, 95))
    baseline = REPO_ROOT / "stress-test" / "baseline.jtl"
    if baseline.exists():
        b, _ = read_jtl(baseline)
        v = sorted(s.elapsed_ms for s in b if s.success)
        single["gemma4:e4b P5 baseline"] = (len(v), statistics.fmean(v), max(v))

    light = runs_of("llama3.2:1b", "tkt-normal", "POST /tickets", "all")
    if light:
        single["llama3.2:1b normal load (1,312/h), all samples"] = (
            sum(x["ok"] for x in light), mean_of(light, "p50_ms"), mean_of(light, "p95_ms"))
    for model in MODELS:
        rows = acc[model]
        single[f"{model} accuracy runs on P3's machines (not the SUT)"] = (
            sum(int(r["tickets"]) for r in rows), statistics.fmean(float(r["latency_p50_ms"]) for r in rows),
            statistics.fmean(float(r["latency_p95_ms"]) for r in rows))

    # ---- markdown
    req_order = ["RR-1", "RR-2", "TR-1", "TR-2", "AR-1", "AR-2", "AR-3"]
    md = ["# Requirements matrix (generated)", "",
          f"Generated by `python analysis/requirements_matrix.py --warmup-sec {args.warmup_sec}`. "
          f"Load metrics count only requests sent after the first {args.warmup_sec} s of each 300 s run "
          f"(about 3 minutes of traffic per run, 3 runs per configuration); excluded runs are skipped. "
          f"p95 counts every request, and an error or timeout counts as slower than any answer, so it shows "
          f"'> 295 s' once more than 5% of requests failed. "
          f"TR verdicts: every run below 1% errors and no latency drift (median latency of the second half of "
          f"the window under {DRIFT_LIMIT}x the first half). Accuracy: mean of the runs in accuracy_runs.csv.", "",
          "## Verdicts", ""]
    md.append(md_table(["Requirement"] + MODELS,
                       [[req] + [("PASS" if verdict[m][req] else "FAIL") for m in MODELS] for req in req_order]))
    md += ["", "## Evidence per verdict", ""]
    md.append(md_table(["Requirement"] + MODELS, [[req] + [detail[m][req] for m in MODELS] for req in req_order]))

    md += ["", f"## Load metrics per configuration (after the first {args.warmup_sec} s; all samples in brackets)", "",
           "Mean across 3 runs. Latency percentiles of successful requests; 'p95 all' counts failures as slowest.", ""]
    table = []
    for (model, config, label), d in sorted(per.items(), key=lambda kv: (MODELS.index(kv[0][0]), kv[0][1], kv[0][2])):
        w, a = [s for s in d["window"] if s], d["all"]
        table.append([model, config, label, f"{mean_of(w, 'sent'):.0f} ({mean_of(a, 'sent'):.0f})",
                      f"{mean_of(w, 'error_pct'):.1f}% ({mean_of(a, 'error_pct'):.1f}%)",
                      f"{ms(mean_of(w, 'p50_ms'))} ({ms(mean_of(a, 'p50_ms'))})",
                      f"{ms(mean_of(w, 'p95_ms'))} ({ms(mean_of(a, 'p95_ms'))})",
                      f"{ms(mean_of(w, 'p99_ms'))} ({ms(mean_of(a, 'p99_ms'))})",
                      f"{ms(mean_of(w, 'p95_all_ms'))} ({ms(mean_of(a, 'p95_all_ms'))})",
                      f"{mean_of(w, 'ok_per_hour'):,.0f} ({mean_of(a, 'ok_per_hour'):,.0f})"])
    md.append(md_table(["Model", "Config", "Request", "Sent/run", "Errors", "p50 OK", "p95 OK", "p99 OK",
                        "p95 all", "OK/hour"], table))

    md += ["", "## Server side per configuration (all samples)", "",
           "HTTP 500 = sqlalchemy QueuePool timeout per the register notes; 502 = classification backend error "
           "(all gemma4 502s took 600-630 s: the service's 600 s limit on one Ollama call); "
           "'stored, not logged' = tickets in the database minus POST /tickets 200 lines in the service log.", ""]
    table = []
    for (model, config), runs in sorted(server.items(), key=lambda kv: (MODELS.index(kv[0][0]), kv[0][1])):
        table.append([model, config, ", ".join(str(r["http500"]) for r in runs),
                      ", ".join(str(r["http502"]) for r in runs), ", ".join(str(r["stored_not_logged"]) for r in runs)])
    md.append(md_table(["Model", "Config", "HTTP 500 per run", "HTTP 502 per run", "Stored, not logged per run"], table))

    md += ["", "## Accuracy per category (mean recall, run range in brackets)", ""]
    cats = AR["AR-1"][1] + AR["AR-2"][1]
    md.append(md_table(["Category (golden n)", "Needed"] + MODELS,
                       [[f"{c} ({golden[c]})", f">= {int((AR['AR-1'][0] if c in AR['AR-1'][1] else AR['AR-2'][0]) * 100)}%"]
                        + [f"{acc_detail[m][c][0] * 100:.1f}%" + ("" if acc_detail[m][c][1] == acc_detail[m][c][2] else
                              f" ({acc_detail[m][c][1] * 100:.1f}-{acc_detail[m][c][2] * 100:.1f})")
                           for m in MODELS] for c in cats]))

    md += ["", "## Accuracy runs vs the official SUT (same golden ticket)", "",
           "Golden-set tickets that were also sent during load or stress runs on the official SUT, compared "
           "with the categories the counted accuracy runs gave the same ticket.", ""]
    md.append(md_table(["Model", "Golden tickets seen on the SUT", "SUT answers", "Same category"], agreement))

    md += ["", "## Single-request latency evidence", ""]
    md.append(md_table(["Source", "Requests", "Centre", "Upper"],
                       [[k, n, f"{c / 1000:.1f} s", f"{u / 1000:.1f} s"] for k, (n, c, u) in single.items()]))
    md.append("")
    md.append("Centre/upper: stress step 1 = median and p95 at 64 tickets/h; P5 baseline = mean and max of 5 "
              "sequential requests (29 Sep, http://172.20.10.3:8000, no service log kept); llama normal load = mean "
              "of the runs' p50 and p95 (some queueing included); accuracy runs = mean of the runs' p50 and p95 "
              "over the 175 golden tickets, one request at a time, client on the same machine.")

    out = OUTPUT_DIR / "requirements_matrix.md"
    out.write_text("\n".join(md) + "\n", encoding="utf-8")
    write_csv(OUTPUT_DIR / "requirements_matrix_load.csv", csv_rows)
    print("\n".join(md))
    print(f"\nWrote {out} and requirements_matrix_load.csv")


if __name__ == "__main__":
    main()
