#!/usr/bin/env python3
"""A2 speed test: pick the fixed workload, the S-measurement tickets and the warm-up candidates (P2 runs this once).

Source: tests/stress/data/tickets.jsonl (committed). Its "row number" is the 1-based line number in that file.
Golden-set tickets are excluded (matched on the first 150 normalised characters), so no workload ticket is a
golden ticket. Selection is deterministic (fixed seed), so anyone can reproduce the same files.

Writes datasets/a2/speed/:
  workload_tickets.jsonl     one JSON body per line, in run order (JMeter reads this)
  workload_rows.csv          order, source line (= row number), characters, kind (typical / long)
  s_probe_tickets.jsonl      3 different typical tickets used once to measure S
  warmup_candidates.jsonl    typical tickets; setup_speed.ps1 picks the 3 fixed warm-ups from these
  workload_manifest.json     sha256 of every file and the counts
"""
import csv
import hashlib
import json
import random
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "tests" / "stress" / "data" / "tickets.jsonl"
GOLDEN = REPO / "datasets" / "golden_test_set.csv"
OUT = REPO / "datasets" / "a2" / "speed"
SEED = 20261117
N_WORKLOAD, N_LONG, N_PROBE, N_WARM = 45, 9, 3, 15  # 45 rows: a Poisson run of about 30 never reaches the end
TYPICAL = (400, 1200)  # characters
LONG_MIN = 1500


def norm(text):
    return " ".join(text.split())[:150].lower()


def main():
    with open(GOLDEN, encoding="cp1252", newline="") as f:
        golden = {norm(r["narrative"]) for r in csv.DictReader(f)}
    tickets = []
    for line_no, line in enumerate(open(SOURCE, encoding="utf-8"), start=1):
        text = json.loads(line)["narrative"]
        if norm(text) in golden:
            continue
        tickets.append((line_no, text))
    seen, unique = set(), []
    for line_no, text in tickets:
        if norm(text) not in seen:
            seen.add(norm(text))
            unique.append((line_no, text))
    typical = [t for t in unique if TYPICAL[0] <= len(t[1]) <= TYPICAL[1]]
    long_ = [t for t in unique if len(t[1]) >= LONG_MIN]
    rng = random.Random(SEED)
    rng.shuffle(typical)
    rng.shuffle(long_)
    n_long = min(N_LONG, len(long_))
    need = N_PROBE + N_WARM + (N_WORKLOAD - n_long)
    if len(typical) < need:
        raise SystemExit(f"Only {len(typical)} typical non-golden tickets, need {need}")
    probe, warm = typical[:N_PROBE], typical[N_PROBE:N_PROBE + N_WARM]
    work_typical = typical[N_PROBE + N_WARM:N_PROBE + N_WARM + (N_WORKLOAD - n_long)]
    workload = [(t, "typical") for t in work_typical] + [(t, "long") for t in long_[:n_long]]
    rng.shuffle(workload)

    OUT.mkdir(parents=True, exist_ok=True)

    def dump(name, items):
        with open(OUT / name, "w", encoding="utf-8", newline="\n") as f:
            for _, text in items:
                f.write(json.dumps({"narrative": text}) + "\n")

    dump("workload_tickets.jsonl", [t for t, _ in workload])
    dump("s_probe_tickets.jsonl", probe)
    dump("warmup_candidates.jsonl", warm)
    with open(OUT / "workload_rows.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["order", "source_file", "row_number", "characters", "kind"])
        for i, ((line_no, text), kind) in enumerate(workload, start=1):
            w.writerow([i, "tests/stress/data/tickets.jsonl", line_no, len(text), kind])
    manifest = {
        "seed": SEED,
        "source": "tests/stress/data/tickets.jsonl",
        "row_number_means": "1-based line number in the source file",
        "golden_tickets_excluded": True,
        "counts": {"workload": len(workload), "long": n_long, "probe": len(probe), "warmup_candidates": len(warm)},
        "probe_rows": [r for r, _ in probe],
        "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.glob("*.jsonl")) + [OUT / "workload_rows.csv"]},
    }
    (OUT / "workload_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"workload {len(workload)} tickets ({n_long} long), probe rows {manifest['probe_rows']}, "
          f"{len(warm)} warm-up candidates -> {OUT}")


if __name__ == "__main__":
    main()
