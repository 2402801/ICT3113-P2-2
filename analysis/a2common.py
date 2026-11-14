"""Shared A2 accuracy helpers: load a test-set accuracy run, check it, score it, and analyse its confusion matrix.

Used by a2_limits.py (Step 1: limits from the top model) and a2_accuracy.py (Step 4: every configuration).
Scoring reuses tests/accuracy/accuracy_report.py's score(), so A1 and A2 numbers are computed the same way.
"""
import csv
import hashlib
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from runlib import CATEGORIES, OUTPUT_DIR, REPO_ROOT, RUNS_DIR, Run, md_table, read_accuracy_rows, read_server_log

sys.path.insert(0, str(REPO_ROOT / "tests" / "accuracy"))
from accuracy_report import NO_ANSWER, final_predictions, predicted, read_meta, score  # noqa: E402

TEST_SET = REPO_ROOT / "datasets" / "a2" / "test_set.csv"
LIMITS_JSON = OUTPUT_DIR / "a2_limits.json"
FIG_DIR = OUTPUT_DIR / "figures"
SMALL_N = 10  # categories with fewer test tickets are flagged as too small for the per-category limit to be fair
SHORT = {"Bank account or service": "Bank account", "Money transfer or service": "Money transfer"}


def short(category: str) -> str:
    return SHORT.get(category, category)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_test_set(label_column: str = "final_agreed_label") -> dict[str, str]:
    """row -> golden label for the 88 test tickets (even golden rows)."""
    raw = TEST_SET.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    rows = list(csv.DictReader(text.splitlines()))
    labels = {r["row"]: r[label_column].strip() for r in rows}
    odd = [row for row in labels if int(row) % 2]
    if odd:
        sys.exit(f"{TEST_SET} contains odd (tuning) rows: {odd[:5]} - the split is wrong")
    return labels


@dataclass
class TestRun:
    run_id: str
    path: Path
    meta: dict
    preds: dict[str, dict]
    model: str
    cascade: str = "off"
    large_model: str | None = None
    route: dict[str, dict] = field(default_factory=dict)  # golden row -> server-log fields (final_model, escalated..)

    @property
    def label(self) -> str:
        if self.cascade in ("", "off", None):
            return self.model
        return f"{self.model} -> {self.large_model} ({self.cascade})"

    @property
    def is_cascade(self) -> bool:
        return self.cascade not in ("", "off", None)


def load_test_run(run_id: str, test_labels: dict[str, str]) -> TestRun:
    """Loads runs/<run_id>/*_accuracy.csv and checks it is a complete run on the committed test set."""
    path = RUNS_DIR / Path(run_id).name
    if not path.is_dir():
        sys.exit(f"No run folder {path}")
    csvs = sorted(path.glob("*_accuracy.csv"))
    if len(csvs) != 1:
        sys.exit(f"{path.name}: expected one *_accuracy.csv, found {[c.name for c in csvs]}")
    meta = read_meta(csvs[0])
    problems = []
    if meta.get("golden_sha256") != sha256(TEST_SET):
        problems.append(f"golden_sha256 {meta.get('golden_sha256', '?')[:12]}.. is not test_set.csv "
                        f"({sha256(TEST_SET)[:12]}..) - this run did not use the committed test set")
    healths = [s.get("health", {}) for s in meta.get("sessions", [])]
    models = {h.get("model") for h in healths} - {None}
    cascades = {str(h.get("cascade", "off")) for h in healths}
    if len(models) != 1 or len(cascades) != 1:
        problems.append(f"service configuration changed during the run: models {models}, cascade {cascades}")
    preds = final_predictions(read_accuracy_rows(csvs[0]))
    missing = sorted(set(test_labels) - set(preds), key=int)
    extra = sorted(set(preds) - set(test_labels), key=int)
    if missing:
        problems.append(f"{len(missing)} test rows have no answer recorded: {missing[:8]}")
    if extra:
        problems.append(f"{len(extra)} rows are not in the test set: {extra[:8]}")
    wrong_label = [r for r, p in preds.items() if r in test_labels and p["golden_label"] != test_labels[r]]
    if wrong_label:
        problems.append(f"golden labels differ from test_set.csv on rows {wrong_label[:8]}")
    if problems:
        sys.exit(f"{path.name} is not a usable test-set run:\n  - " + "\n  - ".join(problems))

    health = healths[0] if healths else {}
    run = TestRun(run_id=path.name, path=path, meta=meta, preds=preds,
                  model=next(iter(models)) if models else "?", cascade=str(health.get("cascade", "off")),
                  large_model=health.get("large_model"))
    run.route = read_routes(path, preds)
    return run


def read_routes(path: Path, preds: dict[str, dict]) -> dict[str, dict]:
    """golden row -> the server-log fields of the request that answered it (joined on req_id)."""
    log = path / "server_access.log"
    if not log.exists():
        return {}
    by_req = {line.req_id: line.fields for line in read_server_log(log)
              if line.method == "POST" and line.path == "/tickets" and line.req_id}
    return {row: by_req[p["req_id"]] for row, p in preds.items() if p.get("req_id") in by_req}


def reconcile_verdict(run: TestRun) -> str:
    """reconcile.py's verdict for the run folder (client CSV vs server log vs DB), or why it could not run."""
    import json
    from reconcile import reconcile
    info = run.path / "run_info.json"
    if not info.exists():
        return "not checked (no run_info.json)"
    try:
        return reconcile(Run(run.path, json.loads(info.read_text(encoding="utf-8-sig")))).verdict
    except Exception as exc:  # reconciliation is evidence, not a reason to stop scoring
        return f"not checked ({type(exc).__name__}: {exc})"


# ---------- confusion analysis ----------

def columns_for(matrix: Counter) -> list[str]:
    return CATEGORIES + ([NO_ANSWER] if any(p == NO_ANSWER for _, p in matrix) else [])


def macro_accuracy(s: dict) -> float:
    """Balanced accuracy: mean of per-category recall (each category weighs the same, whatever its size)."""
    vals = [v["accuracy"] for v in s["per_category"].values() if v["accuracy"] is not None]
    return sum(vals) / len(vals)


def matrix_tables(matrix: Counter) -> str:
    """Counts and row-normalised (% of each true category) confusion matrices, side by side in one table."""
    cols = columns_for(matrix)
    rows = []
    for g in CATEGORIES:
        n = sum(matrix[(g, p)] for p in cols)
        cells = []
        for p in cols:
            k = matrix[(g, p)]
            if not k and p != g:
                cells.append("·")
                continue
            text = f"{k} ({100 * k / n:.0f}%)" if n else str(k)
            cells.append(f"**{text}**" if p == g else text)
        flag = " ⚠" if n < SMALL_N else ""
        rows.append([f"{g} (n={n}){flag}"] + cells)
    totals = ["**Predicted total**"] + [str(sum(matrix[(g, p)] for g in CATEGORIES)) for p in cols]
    return md_table(["True \\ Predicted"] + [short(c) for c in cols], rows + [totals])


def top_pairs(matrix: Counter, k: int = 5) -> list[dict]:
    """Biggest off-diagonal true -> predicted flows, ranked by count, then by share of the true category."""
    n_true = Counter()
    for (g, _), v in matrix.items():
        n_true[g] += v
    pairs = [{"true": g, "predicted": p, "count": v, "n_true": n_true[g], "share": v / n_true[g]}
             for (g, p), v in matrix.items() if g != p and v]
    pairs.sort(key=lambda d: (-d["count"], -d["share"], d["true"], d["predicted"]))
    return pairs[:k]


def sinks(matrix: Counter) -> list[dict]:
    """Per predicted category: how many wrong answers it absorbed, and its precision."""
    out = []
    for p in columns_for(matrix):
        chosen = sum(v for (_, q), v in matrix.items() if q == p)
        right = matrix[(p, p)]
        wrong = Counter({g: v for (g, q), v in matrix.items() if q == p and g != p and v})
        out.append({"predicted": p, "chosen": chosen, "wrong": chosen - right,
                    "precision": right / chosen if chosen and p != NO_ANSWER else None,
                    "from": ", ".join(f"{short(g)} {v}" for g, v in wrong.most_common())})
    return sorted(out, key=lambda d: -d["wrong"])


def confusion_sections(s: dict, title_level: str = "###") -> list[str]:
    m = s["matrix"]
    lines = [f"{title_level} Confusion matrix (counts, % of each true category)", "",
             "Rows are the true (golden) category; bold is correct. ⚠ = fewer than "
             f"{SMALL_N} test tickets, so each ticket moves that row by more than 10 points.", "",
             matrix_tables(m), "",
             f"{title_level} Most common mistakes (true -> predicted)", ""]
    pairs = top_pairs(m)
    if pairs:
        lines.append(md_table(["True", "Predicted as", "Tickets", "Share of true category", "Note"],
                              [[p["true"], p["predicted"], p["count"], f"{p['count']}/{p['n_true']} "
                                f"({100 * p['share']:.0f}%)", "small category" if p["n_true"] < SMALL_N else ""]
                               for p in pairs]))
    else:
        lines.append("No mistakes.")
    lines += ["", f"{title_level} Which predicted categories absorb wrong answers", "",
              md_table(["Predicted", "Times chosen", "Wrong", "Precision", "Wrong ones are really"],
                       [[d["predicted"], d["chosen"], d["wrong"],
                         "-" if d["precision"] is None else f"{100 * d['precision']:.0f}%", d["from"] or "-"]
                        for d in sinks(m) if d["chosen"]]), ""]
    return lines


def confusion_rows(label: str, run_id: str, matrix: Counter) -> list[dict]:
    """Long-format rows for a2_confusion.csv."""
    return [{"config": label, "run_id": run_id, "true": g, "predicted": p, "count": matrix[(g, p)]}
            for g in CATEGORIES for p in columns_for(matrix)]


def heatmap(label: str, s: dict, out: Path) -> None:
    """Row-normalised confusion heatmap with counts, in the A1 figure style (accuracy_figures.py)."""
    from accuracy_figures import BLUES, INK, INK_2, ORANGES, SURFACE, plt  # also applies the A1 rcParams
    m = s["matrix"]
    cols = columns_for(m)
    fig, ax = plt.subplots(figsize=(8.5, 7), dpi=200)
    for i, g in enumerate(CATEGORIES):
        n = sum(m[(g, p)] for p in cols) or 1
        for j, p in enumerate(cols):
            k = m[(g, p)]
            pct = 100 * k / n
            cmap = BLUES if g == p else ORANGES
            ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, edgecolor=SURFACE, linewidth=2,
                                       facecolor=cmap(pct / 100 if g == p else min(pct / 50, 1.0))))
            if k or g == p:
                dark = (g == p and pct >= 60) or (g != p and pct >= 30)
                ax.text(j, i, f"{k}\n{pct:.0f}%", ha="center", va="center", fontsize=8.5,
                        color="#ffffff" if dark else INK)
    ax.set_xlim(-0.5, len(cols) - 0.5)
    ax.set_ylim(len(CATEGORIES) - 0.5, -0.5)
    ax.set_xticks(range(len(cols)), [short(c) for c in cols], rotation=35, ha="right", fontsize=9)
    ax.set_yticks(range(len(CATEGORIES)),
                  [f"{short(g)} (n={s['per_category'][g]['n']})" for g in CATEGORIES], fontsize=9)
    ax.tick_params(length=0, labelcolor=INK)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.set_xlabel("Predicted category")
    ax.set_ylabel("True (golden) category")
    ax.set_title(f"{label}  ·  {s['correct']}/{s['n']} ({100 * s['accuracy']:.1f}%) on the A2 test set",
                 loc="left", fontsize=12, fontweight="bold")
    fig.text(0.01, 0.01, "Cell: tickets and % of the true category (rows sum to 100%). Blue = correct, "
             "orange = mistakes.\nImbalanced test set: 4-20 tickets per category, so small rows move in big steps.",
             fontsize=8, color=INK_2)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    plt.close(fig)


def file_slug(label: str) -> str:
    return "".join(c if c.isalnum() or c in ".-" else "_" for c in label).strip("_")


def pct(k, n) -> str:
    return f"{100 * k / n:.1f}%" if n else "-"
