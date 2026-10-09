#!/usr/bin/env python3
"""Overall and per-category accuracy, with confusion matrices, for each model's golden-set accuracy runs."""
import argparse
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))  # shared run/log helpers live there
from reconcile import reconcile  # noqa: E402
from runlib import (  # noqa: E402
    CATEGORIES, MIN_RUNS, OUTPUT_DIR, fmt_spread, load_exclusions, load_runs, md_table, percentile,
    read_accuracy_rows, spread, write_csv,
)

NO_ANSWER = "(no answer)"  # 502 / no HTTP answer: counted as incorrect
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 2113  # fixed so the intervals are reproducible; each interval restarts from this seed


@dataclass
class Source:
    """One accuracy run: a run folder, or (with --files) a bare *_accuracy.csv."""
    run_id: str
    group: str
    model: str | None
    number: int
    verdict: str  # reconciliation verdict, or "not checked" for --files


def final_predictions(rows: list[dict]) -> dict[str, dict]:
    """Last attempt per golden row (--resume retries tickets that got no HTTP answer)."""
    return {r["row"]: r for r in rows}


def predicted(r: dict) -> str:
    return r["predicted"] if r["status"] == "200" and r["predicted"] else NO_ANSWER


def score(preds: dict[str, dict]) -> dict:
    matrix = Counter((r["golden_label"], predicted(r)) for r in preds.values())
    n = len(preds)
    correct = sum(v for (g, p), v in matrix.items() if g == p)
    no_answer = sum(v for (_, p), v in matrix.items() if p == NO_ANSWER)
    per_category = {}
    for c in CATEGORIES:
        total = sum(v for (g, _), v in matrix.items() if g == c)
        chosen = sum(v for (_, p), v in matrix.items() if p == c)
        per_category[c] = {"n": total, "correct": matrix[(c, c)],
                           "accuracy": matrix[(c, c)] / total if total else None,
                           "precision": matrix[(c, c)] / chosen if chosen else None}
    latencies = sorted(float(r["elapsed_ms"]) for r in preds.values() if r["status"] == "200")
    return {"n": n, "correct": correct, "no_answer": no_answer,
            "accuracy": correct / n if n else None,
            "accuracy_answered": correct / (n - no_answer) if n > no_answer else None,
            "per_category": per_category, "matrix": matrix,
            "latency_p50_ms": percentile(latencies, 50), "latency_p95_ms": percentile(latencies, 95)}


def ticket_scores(entries: list) -> dict[str, tuple[str, float]]:
    """golden row -> (golden label, share of runs that answered it correctly)."""
    hits = defaultdict(list)
    labels = {}
    for _, preds, _ in entries:
        for row, r in preds.items():
            labels[row] = r["golden_label"]
            hits[row].append(predicted(r) == r["golden_label"])
    return {row: (labels[row], statistics.fmean(h)) for row, h in hits.items()}


def bootstrap_ci(values: list[float]) -> tuple[float | None, float | None]:
    """95% percentile-bootstrap interval for the mean of per-ticket scores (resampling golden tickets)."""
    if not values:
        return None, None
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(values)
    means = sorted(sum(rng.choices(values, k=n)) / n for _ in range(BOOTSTRAP_RESAMPLES))
    return percentile(means, 2.5), percentile(means, 97.5)


def accuracy_cis(tickets: dict[str, tuple[str, float]]) -> dict:
    """'overall' and each category -> (low, high) in percent; categories resample within their own tickets."""
    cis = {"overall": bootstrap_ci([s for _, s in tickets.values()])}
    for c in CATEGORIES:
        cis[c] = bootstrap_ci([s for g, s in tickets.values() if g == c])
    return {k: (lo * 100 if lo is not None else None, hi * 100 if hi is not None else None)
            for k, (lo, hi) in cis.items()}


def fmt_p(p: float) -> str:
    return "<0.0001" if p < 0.0001 else f"{p:.4f}"


def fmt_ci(ci: tuple) -> str:
    lo, hi = ci
    return "-" if lo is None else f"{lo:.1f}–{hi:.1f}%"


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value: binomial test of the b discordant wins against b + c at p = 0.5."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def holm(pvalues: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, in the input order."""
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    adjusted, running = [0.0] * len(pvalues), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(pvalues) - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def pairwise_tests(groups: dict) -> list[dict]:
    """Exact McNemar test for every pair of groups, on the golden tickets both answered.

    With repeat runs a ticket counts as correct for a model when it was right in more than half of the runs."""
    majority = {g: {row: s > 0.5 for row, (_, s) in ticket_scores(e).items()} for g, e in groups.items()}
    split = {g: sum(1 for _, s in ticket_scores(e).values() if 0 < s < 1) for g, e in groups.items()}
    rows = []
    for a, b in combinations(groups, 2):
        common = majority[a].keys() & majority[b].keys()
        a_only = sum(majority[a][r] and not majority[b][r] for r in common)
        b_only = sum(majority[b][r] and not majority[a][r] for r in common)
        both = sum(majority[a][r] and majority[b][r] for r in common)
        rows.append({
            "group_a": a, "group_b": b, "tickets": len(common),
            "accuracy_a_pct": sum(majority[a][r] for r in common) / len(common) * 100 if common else None,
            "accuracy_b_pct": sum(majority[b][r] for r in common) / len(common) * 100 if common else None,
            "both_correct": both, "a_only_correct": a_only, "b_only_correct": b_only,
            "both_wrong": len(common) - both - a_only - b_only,
            "split_tickets_a": split[a], "split_tickets_b": split[b],
            "p_exact": mcnemar_exact(a_only, b_only),
        })
    for r, p in zip(rows, holm([r["p_exact"] for r in rows])):
        r["p_holm"] = p
    return rows


def matrix_table(matrix: Counter, columns: list[str]) -> str:
    rows = []
    for g in CATEGORIES:
        counts = [matrix[(g, p)] for p in columns]
        total = sum(counts)
        rows.append([f"**{g}**"] + [f"**{v}**" if p == g else (v or "·") for p, v in zip(columns, counts)]
                    + [total, f"{matrix[(g, g)] / total:.0%}" if total else "-"])
    return md_table(["Golden \\ Predicted"] + columns + ["Total", "Accuracy"], rows)


def pct(values: list) -> dict:
    return spread([v * 100 if v is not None else None for v in values])


def check_predictions(run_id: str, preds: dict, meta: dict) -> None:
    expected = meta.get("golden_rows")
    if expected and len(preds) != expected:
        print(f"!! {run_id}: only {len(preds)} of {expected} golden tickets answered - incomplete run")
    unknown = {r["golden_label"] for r in preds.values()} - set(CATEGORIES)
    if unknown:
        print(f"!! {run_id}: golden labels outside the service's categories: {sorted(unknown)}")


def read_meta(csv_path: Path) -> dict:
    meta_path = csv_path.with_name(csv_path.stem + ".meta.json")
    return json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}


def served_models(meta: dict) -> set[str]:
    return {s.get("health", {}).get("model") for s in meta.get("sessions", [])} - {None}


def collect_runs(selected: list[str], golden_versions: Counter) -> list[tuple[Source, dict]]:
    """Accuracy runs from the run folders under runs/, each checked by reconcile.py."""
    excluded = load_exclusions()
    found = []
    for run in load_runs({"accuracy"}, selected):
        if run.run_id in excluded:
            print(f"-- {run.run_id}: excluded ({excluded[run.run_id]})")
            continue
        csv_path = run.find("*_accuracy.csv")
        if not csv_path:
            print(f"!! {run.run_id}: no *_accuracy.csv in the run folder - skipped")
            continue
        meta = read_meta(csv_path)
        if not meta:
            print(f"!! {run.run_id}: no {csv_path.stem}.meta.json - golden-set version cannot be verified")
        golden_versions[meta.get("golden_sha256", "unknown")] += 1
        served = served_models(meta)
        if served and served != {run.info.get("model")}:
            print(f"!! {run.run_id}: the service answered as {served}, but the run is for {run.info.get('model')}")

        preds = final_predictions(read_accuracy_rows(csv_path))
        if not preds:
            print(f"!! {run.run_id}: {csv_path.name} has no rows - skipped")
            continue
        check_predictions(run.run_id, preds, meta)
        verdict = reconcile(run).verdict
        if verdict == "FAIL":
            print(f"!! {run.run_id}: reconciliation FAILED - see reconcile.py; exclude or rerun it")
        found.append((Source(run.run_id, run.group, run.info.get("model"), run.number, verdict), preds))
    return found


def collect_files(paths: list[str], golden_versions: Counter) -> list[tuple[Source, dict]]:
    """Standalone accuracy CSVs (no run folder, no reconciliation); the model comes from the /health check."""
    found = []
    for name in paths:
        csv_path = Path(name)
        if not csv_path.is_file():
            raise SystemExit(f"No such file: {csv_path}")
        run_id = csv_path.stem.removesuffix("_accuracy")
        meta = read_meta(csv_path)
        served = served_models(meta)
        if len(served) != 1:
            print(f"!! {csv_path.name}: " + (f"answered by several models {sorted(served)}" if served else
                  f"no {csv_path.stem}.meta.json with a /health check - model unknown") + " - skipped")
            continue
        model = served.pop()
        golden_versions[meta.get("golden_sha256", "unknown")] += 1
        preds = final_predictions(read_accuracy_rows(csv_path))
        if not preds:
            print(f"!! {csv_path.name}: no rows - skipped")
            continue
        check_predictions(run_id, preds, meta)
        number = int(run_id.rsplit("_run", 1)[1]) if run_id.rsplit("_run", 1)[-1].isdigit() else 0
        found.append((Source(run_id, model, model, number, "not checked"), preds))
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="*", help="run IDs or folders (default: every finished accuracy run)")
    parser.add_argument("--files", nargs="+", metavar="CSV",
                        help="report directly on *_accuracy.csv files from a standalone accuracy test "
                             "(no run folders, no reconciliation); files of the same model are repeat runs")
    args = parser.parse_args()
    if args.files and args.runs:
        parser.error("give run IDs or --files, not both")

    golden_versions = Counter()
    found = collect_files(args.files, golden_versions) if args.files else collect_runs(args.runs, golden_versions)

    groups = defaultdict(list)
    run_rows, matrix_rows = [], []
    columns = CATEGORIES + [NO_ANSWER]
    for src, preds in sorted(found, key=lambda f: (f[0].group, f[0].number, f[0].run_id)):
        sc = score(preds)
        run_rows.append({
            "run_id": src.run_id, "group": src.group, "model": src.model, "run": src.number,
            "reconciliation": src.verdict, "tickets": sc["n"], "correct": sc["correct"], "no_answer": sc["no_answer"],
            "accuracy": sc["accuracy"], "accuracy_answered_only": sc["accuracy_answered"],
            **{f"acc_{c}": sc["per_category"][c]["accuracy"] for c in CATEGORIES},
            **{f"precision_{c}": sc["per_category"][c]["precision"] for c in CATEGORIES},
            "latency_p50_ms": sc["latency_p50_ms"], "latency_p95_ms": sc["latency_p95_ms"],
        })
        for g in CATEGORIES:
            matrix_rows.append({"run_id": src.run_id, "golden_label": g, **{p: sc["matrix"][(g, p)] for p in columns}})
        groups[src.group].append((src, preds, sc))

    if not groups:
        print("No accuracy runs with an *_accuracy.csv yet.")
        return
    if len(golden_versions) > 1:
        print(f"!! Runs used DIFFERENT golden-set files (sha256 -> runs): {dict(golden_versions)}")

    summary_rows, overview, sections = [], [], []
    for group, entries in groups.items():
        runs = [src for src, _, _ in entries]
        overall = pct([sc["accuracy"] for _, _, sc in entries])
        per_cat = {c: pct([sc["per_category"][c]["accuracy"] for _, _, sc in entries]) for c in CATEGORIES}
        precision = {c: pct([sc["per_category"][c]["precision"] for _, _, sc in entries]) for c in CATEGORIES}
        no_answer = spread([sc["no_answer"] for _, _, sc in entries])
        latency = spread([sc["latency_p50_ms"] for _, _, sc in entries])
        cis = accuracy_cis(ticket_scores(entries))

        def ci_cols(key: str) -> dict:
            return {"ci95_low": cis[key][0], "ci95_high": cis[key][1]}

        summary_rows.append({"group": group, "metric": "accuracy_overall_pct", "n_runs": len(runs), **overall,
                             **ci_cols("overall")})
        summary_rows += [{"group": group, "metric": f"accuracy_pct_{c}", "n_runs": len(runs), **per_cat[c],
                          **ci_cols(c)} for c in CATEGORIES]
        summary_rows += [{"group": group, "metric": f"precision_pct_{c}", "n_runs": len(runs), **precision[c]}
                         for c in CATEGORIES]
        summary_rows.append({"group": group, "metric": "no_answer", "n_runs": len(runs), **no_answer})
        summary_rows.append({"group": group, "metric": "latency_p50_ms", "n_runs": len(runs), **latency})

        all_rows = set().union(*(preds.keys() for _, preds, _ in entries))
        same = [row for row in all_rows if len({predicted(p[row]) if row in p else None for _, p, _ in entries}) == 1]
        identical = len(same) == len(all_rows)
        overview.append([f"**{runs[0].model}**", len(runs), fmt_spread(overall, 1, "%"), fmt_ci(cis["overall"])]
                        + [fmt_spread(per_cat[c], 0, "%") for c in CATEGORIES]
                        + [fmt_spread(no_answer, 1), fmt_spread({k: v / 1000 if v else v for k, v in latency.items()}, 1)])

        matrix = entries[0][2]["matrix"] if identical else sum((sc["matrix"] for _, _, sc in entries), Counter())
        caption = (f"identical in all {len(runs)} runs" if identical and len(runs) > 1
                   else "single run" if len(runs) == 1 else f"summed over {len(runs)} runs")
        sections += [
            f"## {group}", "",
            f"Runs: {', '.join(r.run_id.rsplit('_', 1)[-1] for r in runs)}. "
            + (f"Run-to-run agreement: {len(same)}/{len(all_rows)} tickets got the same answer in every run."
               if len(runs) > 1 else ""),
            "",
            md_table(["Category", "Golden n", "Accuracy (recall)", "95% CI", "Precision"],
                     [[c, entries[0][2]["per_category"][c]["n"], fmt_spread(per_cat[c], 1, "%"), fmt_ci(cis[c]),
                       fmt_spread(precision[c], 1, "%")] for c in CATEGORIES]
                     + [["**Overall**", entries[0][2]["n"], fmt_spread(overall, 1, "%"), fmt_ci(cis["overall"]), ""]]),
            "", f"Confusion matrix ({caption}); rows = golden label, columns = model's answer:", "",
            matrix_table(matrix, columns), "",
        ]

    pairwise = pairwise_tests(groups)
    pairwise_md = []
    if pairwise:
        pairwise_md = [
            "## Pairwise comparison (exact McNemar)", "",
            "Each pair is compared on the golden tickets both answered. A ticket counts as correct for a model when "
            "it was right in more than half of that model's runs. Only the discordant tickets (one model right, the "
            "other wrong) carry information; p is the two-sided exact binomial test of those against 50/50. "
            "Holm-adjusted p corrects for testing every pair.", "",
            md_table(["A", "B", "Tickets", "A acc", "B acc", "Only A right", "Only B right", "p (exact)", "p (Holm)"],
                     [[r["group_a"], r["group_b"], r["tickets"],
                       *("-" if v is None else f"{v:.1f}%" for v in (r["accuracy_a_pct"], r["accuracy_b_pct"])),
                       r["a_only_correct"], r["b_only_correct"],
                       fmt_p(r["p_exact"]), fmt_p(r["p_holm"])] for r in pairwise]), "",
        ]

    source_note = ("Source: standalone accuracy CSVs (`--files`); these were not reconciled against server logs. "
                   if args.files else "")
    md = ["# Accuracy report", "",
          source_note
          + "Every golden-set ticket sent once per run through `POST /tickets`, one at a time, outside any load run. "
          "Cells: mean ± SD (min–max) across runs. Per-category accuracy = share of that category's golden tickets "
          "answered correctly (recall). A ticket with no category (502 / no answer) counts as incorrect. "
          "p50 latency = client-side time per ticket with nothing else running.", "",
          f"95% CI: percentile bootstrap over golden tickets ({BOOTSTRAP_RESAMPLES} resamples, seed {BOOTSTRAP_SEED}); "
          "each ticket's score is its share of correct runs. Per-category intervals resample within that category, "
          "so they are wide where the category has few golden tickets. The interval reflects which tickets happen "
          "to be in the golden set, not run-to-run variation (that is the ± SD).", "",
          md_table(["Model", "Runs", "Overall", "Overall 95% CI"] + CATEGORIES + ["No answer", "p50 latency (s)"],
                   overview), "",
          *pairwise_md,
          *sections]

    predictions = defaultdict(dict)
    for group, entries in groups.items():
        for src, preds, _ in entries:
            for row, r in preds.items():
                predictions[row].setdefault("golden_label", r["golden_label"])
                predictions[row][src.run_id] = predicted(r)
    write_csv(OUTPUT_DIR / "accuracy_runs.csv", run_rows)
    write_csv(OUTPUT_DIR / "accuracy_summary.csv", summary_rows)
    write_csv(OUTPUT_DIR / "accuracy_pairwise.csv", pairwise)
    write_csv(OUTPUT_DIR / "confusion_matrices.csv", matrix_rows)
    write_csv(OUTPUT_DIR / "accuracy_predictions.csv",
              [{"row": row, **predictions[row]} for row in sorted(predictions, key=lambda r: int(r) if r.isdigit() else 0)])
    (OUTPUT_DIR / "accuracy_report.md").write_text("\n".join(md), encoding="utf-8")
    print(f"Wrote accuracy_runs.csv, accuracy_summary.csv, accuracy_pairwise.csv, confusion_matrices.csv, "
          f"accuracy_predictions.csv and accuracy_report.md to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
