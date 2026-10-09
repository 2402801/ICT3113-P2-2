#!/usr/bin/env python3
"""Slide figures (PNG) from accuracy_report.py's output: overall accuracy, per-category accuracy, confusion matrices."""
import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "analysis"))  # shared run/log helpers live there
from runlib import CATEGORIES, OUTPUT_DIR  # noqa: E402

FIG_DIR = OUTPUT_DIR / "figures"
SHORT = {"Bank account or service": "Bank account", "Money transfer or service": "Money transfer"}
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE = "#2a78d6"
BLUES = LinearSegmentedColormap.from_list("blues", ["#f0f5fc", "#9ec5f4", "#3987e5", "#1c5cab", "#0d366b"])
ORANGES = LinearSegmentedColormap.from_list("oranges", ["#fdf1ec", "#f6b89c", "#eb6834", "#b8461c"])

plt.rcParams.update({
    "font.family": "sans-serif", "font.size": 11, "text.color": INK, "axes.labelcolor": INK_2,
    "xtick.color": INK_2, "ytick.color": INK_2, "axes.edgecolor": GRID, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})


def short(category: str) -> str:
    return SHORT.get(category, category)


def read_csv(name: str) -> list[dict]:
    with open(OUTPUT_DIR / name, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def model_of(group: str) -> str:
    """'mistral-7b_accuracy_golden175' -> 'mistral:7b'."""
    name = group.split("_accuracy")[0]
    head, _, size = name.rpartition("-")
    return f"{head}:{size}"


def load_summary() -> dict[str, dict[str, dict]]:
    """model -> metric -> summary row."""
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in read_csv("accuracy_summary.csv"):
        out[model_of(r["group"])][r["metric"]] = r
    return out


def load_confusion() -> dict[str, dict[str, dict[str, int]]]:
    """model -> golden label -> predicted -> count, pooled over the model's included runs."""
    model_by_run = {r["run_id"]: r["model"] for r in read_csv("accuracy_runs.csv")}
    out = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for r in read_csv("confusion_matrices.csv"):
        model = model_by_run.get(r["run_id"])
        if model is None:
            continue
        for predicted in CATEGORIES + ["(no answer)"]:
            out[model][r["golden_label"]][predicted] += int(r.get(predicted) or 0)
    return out


def overall_chart(summary: dict, models: list[str]) -> None:
    rows = sorted(models, key=lambda m: float(summary[m]["accuracy_overall_pct"]["mean"]))
    means = [float(summary[m]["accuracy_overall_pct"]["mean"]) for m in rows]
    lows = [float(summary[m]["accuracy_overall_pct"]["ci95_low"]) for m in rows]
    highs = [float(summary[m]["accuracy_overall_pct"]["ci95_high"]) for m in rows]
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=200)
    ax.barh(rows, means, height=0.5, color=BLUE)
    ax.errorbar(means, rows, xerr=[[m - lo for m, lo in zip(means, lows)], [hi - m for m, hi in zip(means, highs)]],
                fmt="none", ecolor=INK_2, elinewidth=1.2, capsize=4)
    for y, (mean, hi) in enumerate(zip(means, highs)):
        ax.text(hi + 1.5, y, f"{mean:.1f}%", va="center", fontsize=12, fontweight="bold", color=INK)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Overall accuracy on golden set (%)")
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="y", length=0, labelsize=12, labelcolor=INK)
    ax.set_title("Overall accuracy per model", loc="left", fontsize=14, fontweight="bold", pad=12)
    fig.text(0.01, 0.01, "Mean of 3 runs × 175 golden tickets; whiskers = 95% bootstrap CI.",
             fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(FIG_DIR / "accuracy_overall.png")
    plt.close(fig)


def per_category_chart(summary: dict, models: list[str]) -> None:
    rows = sorted(models, key=lambda m: -float(summary[m]["accuracy_overall_pct"]["mean"]))
    grid = [[float(summary[m][f"accuracy_pct_{c}"]["mean"]) for c in CATEGORIES] for m in rows]
    fig, ax = plt.subplots(figsize=(10, 3.8), dpi=200)
    ax.imshow(grid, cmap=BLUES, vmin=0, vmax=100, aspect="auto")
    for i, row in enumerate(grid):
        for j, value in enumerate(row):
            ax.text(j, i, f"{value:.0f}%", ha="center", va="center", fontsize=11,
                    color="#ffffff" if value >= 60 else INK)
    ax.set_xticks(range(len(CATEGORIES)), [short(c) for c in CATEGORIES], fontsize=10)
    ax.set_yticks(range(len(rows)), rows, fontsize=11)
    ax.tick_params(length=0, labelcolor=INK)
    ax.set_xticks([x - 0.5 for x in range(1, len(CATEGORIES))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(rows))], minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=2)
    ax.tick_params(which="minor", length=0)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.set_title("Per-category accuracy (recall): share of each true category classified correctly",
                 loc="left", fontsize=13, fontweight="bold", pad=10)
    fig.text(0.01, 0.01, "Mean of 3 runs. Golden set: 21–35 tickets per category, 175 total.",
             fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(FIG_DIR / "accuracy_per_category.png")
    plt.close(fig)


def confusion_chart(confusion: dict, summary: dict, models: list[str]) -> None:
    order = sorted(models, key=lambda m: -float(summary[m]["accuracy_overall_pct"]["mean"]))
    fig, axes = plt.subplots(2, 2, figsize=(13, 11.5), dpi=200)
    labels = [short(c) for c in CATEGORIES]
    for ax, model in zip(axes.flat, order):
        matrix = confusion[model]
        for i, golden in enumerate(CATEGORIES):
            total = sum(matrix[golden].values()) or 1
            for j, predicted in enumerate(CATEGORIES):
                pct = 100 * matrix[golden][predicted] / total
                cmap = BLUES if i == j else ORANGES
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, facecolor=cmap(pct / 100 if i == j else min(pct / 50, 1.0)),
                                           edgecolor=SURFACE, linewidth=2))
                if pct >= 0.5 or i == j:  # always label the diagonal, so 0% correct is visible
                    dark = (i == j and pct >= 60) or (i != j and pct >= 30)
                    ax.text(j, i, f"{pct:.0f}", ha="center", va="center", fontsize=9.5,
                            color="#ffffff" if dark else INK, fontweight="bold" if i != j and pct >= 15 else "normal")
        ax.set_xlim(-0.5, len(CATEGORIES) - 0.5)
        ax.set_ylim(len(CATEGORIES) - 0.5, -0.5)
        ax.set_xticks(range(len(CATEGORIES)), labels, rotation=35, ha="right", fontsize=9)
        ax.set_yticks(range(len(CATEGORIES)), labels, fontsize=9)
        ax.tick_params(length=0, labelcolor=INK)
        for side in ax.spines.values():
            side.set_visible(False)
        acc = float(summary[model]["accuracy_overall_pct"]["mean"])
        ax.set_title(f"{model}  ·  {acc:.1f}% overall", loc="left", fontsize=12, fontweight="bold")
        ax.set_xlabel("Predicted category")
        ax.set_ylabel("True (golden) category")
    fig.suptitle("Where each model goes wrong: confusion matrices (% of each true category)",
                 x=0.01, ha="left", fontsize=15, fontweight="bold")
    fig.text(0.01, 0.005, "Rows sum to 100%, pooled over 3 runs. Blue diagonal = correct; "
             "orange = misclassified (darker = more). Blank off-diagonal = 0%.", fontsize=10, color=INK_2)
    fig.tight_layout(rect=(0, 0.02, 1, 0.97))
    fig.savefig(FIG_DIR / "confusion_matrices.png")
    plt.close(fig)


def top_confusions(confusion: dict, models: list[str], n: int = 3) -> None:
    """Prints each model's biggest off-diagonal flows, for the slide's highlight bullets."""
    for model in models:
        flows = []
        for golden in CATEGORIES:
            total = sum(confusion[model][golden].values()) or 1
            for predicted, count in confusion[model][golden].items():
                if predicted != golden and count:
                    flows.append((100 * count / total, golden, predicted))
        flows.sort(reverse=True)
        print(f"{model}: " + "; ".join(f"{short(g)} -> {short(p)} {pct:.0f}%" for pct, g, p in flows[:n]))


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    summary = load_summary()
    confusion = load_confusion()
    models = sorted(confusion)
    overall_chart(summary, models)
    per_category_chart(summary, models)
    confusion_chart(confusion, summary, models)
    top_confusions(confusion, models)
    print(f"Wrote accuracy_overall.png, accuracy_per_category.png and confusion_matrices.png to {FIG_DIR}")


if __name__ == "__main__":
    main()
