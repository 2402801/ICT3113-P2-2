#!/usr/bin/env python3
"""Overall and per-category accuracy, with confusion matrices, for each model's golden-set accuracy runs."""
import argparse
import json
from collections import Counter, defaultdict

from reconcile import reconcile
from runlib import (
    CATEGORIES, MIN_RUNS, OUTPUT_DIR, fmt_spread, load_exclusions, load_runs, md_table, percentile,
    read_accuracy_rows, spread, write_csv,
)

NO_ANSWER = "(no answer)"  # 502 / no HTTP answer: counted as incorrect


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="*", help="run IDs or folders (default: every finished accuracy run)")
    args = parser.parse_args()

    excluded = load_exclusions()
    groups = defaultdict(list)
    run_rows, matrix_rows, golden_versions = [], [], Counter()
    for run in load_runs({"accuracy"}, args.runs):
        if run.run_id in excluded:
            print(f"-- {run.run_id}: excluded ({excluded[run.run_id]})")
            continue
        csv_path = run.find("*_accuracy.csv")
        if not csv_path:
            print(f"!! {run.run_id}: no *_accuracy.csv in the run folder - skipped")
            continue
        meta_path = csv_path.with_name(csv_path.stem + ".meta.json")
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        if not meta:
            print(f"!! {run.run_id}: no {meta_path.name} - golden-set version cannot be verified")
        golden_versions[meta.get("golden_sha256", "unknown")] += 1
        served = {s.get("health", {}).get("model") for s in meta.get("sessions", [])} - {None}
        if served and served != {run.info.get("model")}:
            print(f"!! {run.run_id}: the service answered as {served}, but the run is for {run.info.get('model')}")

        preds = final_predictions(read_accuracy_rows(csv_path))
        expected = meta.get("golden_rows")
        if expected and len(preds) != expected:
            print(f"!! {run.run_id}: only {len(preds)} of {expected} golden tickets answered - incomplete run")
        unknown = {r["golden_label"] for r in preds.values()} - set(CATEGORIES)
        if unknown:
            print(f"!! {run.run_id}: golden labels outside the service's categories: {sorted(unknown)}")
        verdict = reconcile(run).verdict
        if verdict == "FAIL":
            print(f"!! {run.run_id}: reconciliation FAILED - see reconcile.py; exclude or rerun it")

        sc = score(preds)
        run_rows.append({
            "run_id": run.run_id, "group": run.group, "model": run.info.get("model"), "run": run.number,
            "reconciliation": verdict, "tickets": sc["n"], "correct": sc["correct"], "no_answer": sc["no_answer"],
            "accuracy": sc["accuracy"], "accuracy_answered_only": sc["accuracy_answered"],
            **{f"acc_{c}": sc["per_category"][c]["accuracy"] for c in CATEGORIES},
            **{f"precision_{c}": sc["per_category"][c]["precision"] for c in CATEGORIES},
            "latency_p50_ms": sc["latency_p50_ms"], "latency_p95_ms": sc["latency_p95_ms"],
        })
        columns = CATEGORIES + [NO_ANSWER]
        for g in CATEGORIES:
            matrix_rows.append({"run_id": run.run_id, "golden_label": g, **{p: sc["matrix"][(g, p)] for p in columns}})
        groups[run.group].append((run, preds, sc))

    if not groups:
        print("No accuracy runs with an *_accuracy.csv yet.")
        return
    if len(golden_versions) > 1:
        print(f"!! Runs used DIFFERENT golden-set files (sha256 -> runs): {dict(golden_versions)}")

    columns = CATEGORIES + [NO_ANSWER]
    summary_rows, overview, sections = [], [], []
    for group, entries in groups.items():
        runs = [run for run, _, _ in entries]
        if len(runs) < MIN_RUNS:
            print(f"!! {group}: only {len(runs)} run(s) - a single run is not a measurement ({MIN_RUNS} required)")
        overall = pct([sc["accuracy"] for _, _, sc in entries])
        per_cat = {c: pct([sc["per_category"][c]["accuracy"] for _, _, sc in entries]) for c in CATEGORIES}
        precision = {c: pct([sc["per_category"][c]["precision"] for _, _, sc in entries]) for c in CATEGORIES}
        no_answer = spread([sc["no_answer"] for _, _, sc in entries])
        latency = spread([sc["latency_p50_ms"] for _, _, sc in entries])
        summary_rows.append({"group": group, "metric": "accuracy_overall_pct", "n_runs": len(runs), **overall})
        summary_rows += [{"group": group, "metric": f"accuracy_pct_{c}", "n_runs": len(runs), **per_cat[c]}
                         for c in CATEGORIES]
        summary_rows += [{"group": group, "metric": f"precision_pct_{c}", "n_runs": len(runs), **precision[c]}
                         for c in CATEGORIES]
        summary_rows.append({"group": group, "metric": "no_answer", "n_runs": len(runs), **no_answer})
        summary_rows.append({"group": group, "metric": "latency_p50_ms", "n_runs": len(runs), **latency})

        all_rows = set().union(*(preds.keys() for _, preds, _ in entries))
        same = [row for row in all_rows if len({predicted(p[row]) if row in p else None for _, p, _ in entries}) == 1]
        identical = len(same) == len(all_rows)
        overview.append([f"**{runs[0].info.get('model')}**", len(runs), fmt_spread(overall, 1, "%")]
                        + [fmt_spread(per_cat[c], 0, "%") for c in CATEGORIES]
                        + [fmt_spread(no_answer, 1), fmt_spread({k: v / 1000 if v else v for k, v in latency.items()}, 1)])

        matrix = entries[0][2]["matrix"] if identical else sum((sc["matrix"] for _, _, sc in entries), Counter())
        caption = (f"identical in all {len(runs)} runs" if identical and len(runs) > 1
                   else "single run" if len(runs) == 1 else f"summed over {len(runs)} runs")
        sections += [
            f"## {group}", "",
            f"Runs: {', '.join(r.run_id.rsplit('_', 1)[1] for r in runs)}. "
            + (f"Run-to-run agreement: {len(same)}/{len(all_rows)} tickets got the same answer in every run."
               if len(runs) > 1 else ""),
            "",
            md_table(["Category", "Golden n", "Accuracy (recall)", "Precision"],
                     [[c, entries[0][2]["per_category"][c]["n"], fmt_spread(per_cat[c], 1, "%"),
                       fmt_spread(precision[c], 1, "%")] for c in CATEGORIES]
                     + [["**Overall**", entries[0][2]["n"], fmt_spread(overall, 1, "%"), ""]]),
            "", f"Confusion matrix ({caption}); rows = golden label, columns = model's answer:", "",
            matrix_table(matrix, columns), "",
        ]

    md = ["# Accuracy report", "",
          "Every golden-set ticket sent once per run through `POST /tickets`, one at a time, outside any load run. "
          "Cells: mean ± SD (min–max) across runs. Per-category accuracy = share of that category's golden tickets "
          "answered correctly (recall). A ticket with no category (502 / no answer) counts as incorrect. "
          "p50 latency = client-side time per ticket with nothing else running.", "",
          md_table(["Model", "Runs", "Overall"] + CATEGORIES + ["No answer", "p50 latency (s)"], overview), "",
          *sections]

    predictions = defaultdict(dict)
    for group, entries in groups.items():
        for run, preds, _ in entries:
            for row, r in preds.items():
                predictions[row].setdefault("golden_label", r["golden_label"])
                predictions[row][run.run_id] = predicted(r)
    write_csv(OUTPUT_DIR / "accuracy_runs.csv", run_rows)
    write_csv(OUTPUT_DIR / "accuracy_summary.csv", summary_rows)
    write_csv(OUTPUT_DIR / "confusion_matrices.csv", matrix_rows)
    write_csv(OUTPUT_DIR / "accuracy_predictions.csv",
              [{"row": row, **predictions[row]} for row in sorted(predictions, key=lambda r: int(r) if r.isdigit() else 0)])
    (OUTPUT_DIR / "accuracy_report.md").write_text("\n".join(md), encoding="utf-8")
    print(f"Wrote accuracy_runs.csv, accuracy_summary.csv, confusion_matrices.csv, accuracy_predictions.csv "
          f"and accuracy_report.md to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
