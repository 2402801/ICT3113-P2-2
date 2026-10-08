#!/usr/bin/env python3
"""Sends every golden-set ticket through POST /tickets, one at a time, and records the service's answers."""
import argparse
import csv
import hashlib
import io
import json
import platform
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COLUMNS = ["row", "golden_label", "predicted", "correct", "status", "error", "req_id", "ticket_id",
           "start_ms", "elapsed_ms", "classification_latency_ms"]
# Bypass any system HTTP proxy: the SUT is on the LAN.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(method: str, url: str, body: dict | None = None, headers: dict | None = None, timeout: float = 10):
    """One HTTP request -> (status, response headers, JSON body, error text); status 0 = no HTTP answer."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with OPENER.open(request, timeout=timeout) as response:
            return response.status, response.headers, json.loads(response.read()), ""
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        try:
            text = json.loads(text).get("detail", text)
        except (ValueError, AttributeError):
            pass
        return exc.code, exc.headers, None, str(text)[:300]
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return 0, {}, None, f"{type(exc).__name__}: {getattr(exc, 'reason', exc)}"


def read_golden(path: Path) -> list[dict]:
    """Golden-set rows; the frozen file is Windows-1252 (saved from Excel), so fall back to it when not UTF-8."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    return list(csv.DictReader(io.StringIO(text, newline="")))


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    # 127.0.0.1, not localhost: on Windows "localhost" tries IPv6 first and adds ~2 s to every request.
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="SUT base URL, e.g. http://192.168.0.104:8000")
    parser.add_argument("--run-id", required=True, help="run ID printed by prepare_run.ps1 (sent as X-Run-Id)")
    parser.add_argument("--golden", default=str(REPO_ROOT / "datasets" / "golden_test_set.csv"))
    parser.add_argument("--label-column", default="final_agreed_label")
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parent / "results"))
    parser.add_argument("--timeout", type=float, default=900, help="seconds per ticket (service gives Ollama 600 s)")
    parser.add_argument("--limit", type=int, help="only the first N tickets (dry runs only)")
    parser.add_argument("--resume", action="store_true", help="continue an interrupted run; retries no-answer tickets")
    args = parser.parse_args()

    golden_path = Path(args.golden)
    if not golden_path.exists():
        sys.exit(f"Golden set not found: {golden_path}\n"
                 "It is frozen on main: git checkout main -- datasets/golden_test_set.csv")
    golden = [(r["row"], r["narrative"], r[args.label_column].strip()) for r in read_golden(golden_path)]
    if any(not label for _, _, label in golden):
        sys.exit(f"Some golden rows have an empty {args.label_column}")
    golden = golden[:args.limit] if args.limit else golden

    base = args.url.rstrip("/")
    status, _, health, error = call("GET", f"{base}/health")
    if status != 200:
        sys.exit(f"GET {base}/health failed: {error or status}")
    if not args.run_id.startswith(health["model"].replace(":", "-") + "_"):
        sys.exit(f"The service is running {health['model']}, but run ID {args.run_id} is for another model.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.run_id}_accuracy.csv"
    meta_path = out_dir / f"{args.run_id}_accuracy.meta.json"
    done = set()
    # An empty file is a run that died before writing anything (not even the header): start it afresh.
    new_file = not out_path.exists() or out_path.stat().st_size == 0
    if not new_file:
        if not args.resume:
            sys.exit(f"{out_path} exists. Never overwrite evidence: --resume it, or use a new run ID.")
        with open(out_path, newline="", encoding="utf-8") as f:
            done = {r["row"] for r in csv.DictReader(f) if r["status"] != "0"}

    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {
        "run_id": args.run_id,
        "sut_url": base,
        "golden_file": golden_path.resolve().relative_to(REPO_ROOT).as_posix()
        if golden_path.resolve().is_relative_to(REPO_ROOT) else str(golden_path),
        "golden_sha256": hashlib.sha256(golden_path.read_bytes()).hexdigest(),
        "golden_rows": len(golden),
        "label_column": args.label_column,
        "limit": args.limit,
        "timeout_s": args.timeout,
        "sessions": [],
    }
    session = {"started_at_utc": utc_now(), "finished_at_utc": None, "health": health,
               "client_host": socket.gethostname(), "python": platform.python_version()}
    meta["sessions"].append(session)

    def save_meta() -> None:
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    save_meta()
    todo = [g for g in golden if g[0] not in done]
    print(f"{health['model']} (prompt {health['prompt_version']}, think={health['think']}) at {base}: "
          f"{len(todo)} of {len(golden)} golden tickets to send -> {out_path}")

    correct = 0
    try:
        with open(out_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            if new_file:
                writer.writeheader()
                f.flush()
            for i, (row, narrative, label) in enumerate(todo, 1):
                start_ms = int(time.time() * 1000)
                t0 = time.perf_counter()
                status, headers, body, error = call("POST", f"{base}/tickets", {"narrative": narrative},
                                                    {"X-Run-Id": args.run_id}, args.timeout)
                elapsed_ms = (time.perf_counter() - t0) * 1000
                body = body if status == 200 and isinstance(body, dict) else {}
                answer = body.get("category", "")
                correct += answer == label
                writer.writerow({
                    "row": row, "golden_label": label, "predicted": answer, "correct": int(answer == label),
                    "status": status, "error": error, "req_id": headers.get("X-Request-ID", "") if headers else "",
                    "ticket_id": body.get("id", ""), "start_ms": start_ms, "elapsed_ms": round(elapsed_ms, 1),
                    "classification_latency_ms": body.get("classification_latency_ms", ""),
                })
                f.flush()
                outcome = "OK   " if answer == label else "WRONG" if answer else f"ERROR {status}"
                print(f"[{len(done) + i:>3}/{len(golden)}] row {row} {outcome} {label} -> {answer or error} "
                      f"({elapsed_ms / 1000:.1f} s, {correct}/{i} correct this session)")
    except KeyboardInterrupt:
        save_meta()
        sys.exit(f"\nInterrupted. Continue within the same READY window with --resume --run-id {args.run_id}")

    session["finished_at_utc"] = utc_now()
    save_meta()
    with open(out_path, newline="", encoding="utf-8") as f:
        final = {r["row"]: r for r in csv.DictReader(f)}
    right = sum(r["correct"] == "1" for r in final.values())
    missing = len(golden) - sum(r["status"] != "0" for r in final.values())
    print(f"\nDone: {right}/{len(final)} correct ({right / len(final):.1%})"
          + (f"; {missing} ticket(s) got no HTTP answer - rerun with --resume" if missing else ""))
    print(f"Copy {out_path.name} and {meta_path.name} into runs/{args.run_id}/ after finish_run.ps1.")


if __name__ == "__main__":
    main()
