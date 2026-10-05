"""Shared readers for run evidence (run folders, .jtl, server log, DB exports) and stats helpers."""
import csv
import json
import re
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "runs"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
EXCLUSIONS_FILE = Path(__file__).resolve().parent / "excluded_runs.csv"
MIN_RUNS = 3

csv.field_size_limit(2**31 - 1)

sys.path.insert(0, str(REPO_ROOT / "server"))
from categories import CATEGORIES  # noqa: E402  (the service's category list is the source of truth)


@dataclass
class Run:
    path: Path
    info: dict

    @property
    def run_id(self) -> str:
        return self.path.name

    @property
    def group(self) -> str:
        """Configuration shared by repeat runs: <model>_<test-type>_<config>."""
        return self.run_id.rsplit("_run", 1)[0]

    @property
    def number(self) -> int:
        return int(self.info.get("run", 0))

    @property
    def finished(self) -> bool:
        return (self.path / "server_access.log").exists()

    def find(self, pattern: str) -> Path | None:
        matches = sorted(self.path.glob(pattern))
        if len(matches) > 1:
            raise ValueError(f"expected one {pattern}, found {[m.name for m in matches]}")
        return matches[0] if matches else None


def load_runs(test_types: set[str], selected: list[str] | None = None) -> list[Run]:
    """Finished runs of the given test types; explicitly selected run IDs/folders bypass the type filter."""
    wanted = {Path(s).name for s in selected or []}
    runs = []
    for info_path in sorted(RUNS_DIR.glob("*/run_info.json")):
        run = Run(info_path.parent, json.loads(info_path.read_text(encoding="utf-8-sig")))
        if wanted:
            if run.run_id not in wanted:
                continue
        elif run.info.get("test_type") not in test_types:
            continue
        if not run.finished:
            print(f"!! {run.run_id}: not finished yet (no server_access.log) - skipped")
            continue
        runs.append(run)
    missing = wanted - {r.run_id for r in runs} - {p.parent.name for p in RUNS_DIR.glob("*/run_info.json")}
    if missing:
        sys.exit(f"No such run folder(s) under {RUNS_DIR}: {', '.join(sorted(missing))}")
    return sorted(runs, key=lambda r: (r.group, r.number))


def load_exclusions() -> dict[str, str]:
    """run_id -> reason, from analysis/excluded_runs.csv."""
    if not EXCLUSIONS_FILE.exists():
        return {}
    with open(EXCLUSIONS_FILE, newline="", encoding="utf-8-sig") as f:
        return {r["run_id"].strip(): r["reason"].strip() for r in csv.DictReader(f) if r["run_id"].strip()}


@dataclass
class ClientSample:
    label: str
    start_ms: int
    elapsed_ms: float
    status: str  # HTTP status code, or JMeter's "Non HTTP response code: ..." / "0" when no answer
    success: bool
    req_id: str
    message: str
    category: str = ""


def read_jtl(path: Path) -> tuple[list[ClientSample], bool]:
    """Samples from a CSV .jtl, and whether it has the req_id column (-Jsample_variables=req_id)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        if "timeStamp" not in columns:
            raise ValueError(f"{path.name} is not a CSV .jtl with a header line (columns: {columns[:5]})")
        samples = [
            ClientSample(
                label=r["label"],
                start_ms=int(r["timeStamp"]),
                elapsed_ms=float(r["elapsed"]),
                status=r["responseCode"],
                success=r["success"].strip().lower() == "true",
                req_id=(r.get("req_id") or "").strip(),
                message=r.get("responseMessage") or r.get("failureMessage") or "",
            )
            for r in reader
        ]
    return samples, "req_id" in columns


def read_accuracy_rows(path: Path) -> list[dict]:
    """Every row the accuracy runner wrote, including retried attempts."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def accuracy_samples(rows: list[dict]) -> list[ClientSample]:
    return [
        ClientSample(
            label="POST /tickets",
            start_ms=int(r["start_ms"]),
            elapsed_ms=float(r["elapsed_ms"]),
            status=r["status"],
            success=r["status"] == "200",
            req_id=r["req_id"],
            message=r["error"],
            category=r["predicted"],
        )
        for r in rows
    ]


LOG_LINE = re.compile(
    r"^(?P<ts>\S+) (?P<method>[A-Z]+) (?P<path>\S+) (?P<status>\d{3}) (?P<latency>[\d.]+)ms(?: (?P<fields>.*))?$"
)
LOG_FIELD = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S*)')


@dataclass
class ServerLine:
    method: str
    path: str
    status: int
    latency_ms: float
    fields: dict

    @property
    def label(self) -> str:
        return f"{self.method} {self.path}"

    @property
    def req_id(self) -> str:
        return self.fields.get("req_id", "")

    @property
    def start_ms(self) -> int:
        return int(self.fields.get("start_ms", 0))

    @property
    def run(self) -> str:
        return self.fields.get("run", "-")


def read_server_log(path: Path) -> list[ServerLine]:
    lines = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for number, raw in enumerate(f, 1):
            raw = raw.rstrip("\r\n")
            if not raw:
                continue
            m = LOG_LINE.match(raw)
            if not m:
                raise ValueError(f"{path.name}:{number}: unrecognised log line: {raw[:120]}")
            fields = {k: json.loads(v) if v.startswith('"') else v for k, v in LOG_FIELD.findall(m["fields"] or "")}
            lines.append(ServerLine(m["method"], m["path"], int(m["status"]), float(m["latency"]), fields))
    return lines


def read_mysql_tsv(path: Path) -> list[dict]:
    """Rows of a `mysql --batch` export (tab-separated with a header; empty file when the table was empty)."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        header = next(reader, None)
        return [dict(zip(header, row)) for row in reader] if header else []


def percentile(sorted_values: list[float], p: float) -> float | None:
    """Linear interpolation between closest ranks (same as Excel PERCENTILE.INC and numpy's default)."""
    if not sorted_values:
        return None
    k = (len(sorted_values) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


def latency_stats(values: list[float]) -> dict:
    v = sorted(values)
    return {
        "mean_ms": statistics.fmean(v) if v else None,
        "p50_ms": percentile(v, 50),
        "p90_ms": percentile(v, 90),
        "p95_ms": percentile(v, 95),
        "p99_ms": percentile(v, 99),
        "max_ms": v[-1] if v else None,
    }


def spread(values: list) -> dict:
    """Mean and spread of one metric across repeat runs (sample SD, n-1)."""
    v = [x for x in values if x is not None]
    if not v:
        return {"mean": None, "sd": None, "min": None, "max": None, "cv_pct": None}
    mean = statistics.fmean(v)
    sd = statistics.stdev(v) if len(v) > 1 else None
    return {
        "mean": mean,
        "sd": sd,
        "min": min(v),
        "max": max(v),
        "cv_pct": sd / mean * 100 if sd is not None and mean else None,
    }


def fmt_spread(s: dict, digits: int = 0, suffix: str = "") -> str:
    """'mean ± sd (min–max)' for a markdown cell."""
    if s["mean"] is None:
        return "-"
    f = f"{{:,.{digits}f}}"
    if s["sd"] is None:
        return f"{f.format(s['mean'])}{suffix} (1 run)"
    return f"{f.format(s['mean'])}{suffix} ± {f.format(s['sd'])} ({f.format(s['min'])}–{f.format(s['max'])})"


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: round(v, 3) if isinstance(v, float) else v for k, v in r.items()})


def md_table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join("" if c is None else str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)
