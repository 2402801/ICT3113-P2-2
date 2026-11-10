"""A2 memory check: can phi3:3.8b and gemma4:e4b (thinking on, as in A1) stay resident together in Docker Ollama?

Alternates non-golden tickets between the two models using the service's v1 prompt and JSON format.
A model that was evicted and reloaded shows a load_duration of seconds instead of milliseconds.
Usage: python scripts/a2_memcheck.py <repo root> tests/environment/a2_memcheck
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(sys.argv[1])
OUT = Path(sys.argv[2])
sys.path.insert(0, str(REPO / "server"))
from categories import CATEGORIES  # noqa: E402
from prompt import build_prompt  # noqa: E402

API = "http://127.0.0.1:11434"
CONTAINER = "ict3113-p2-2-ollama-1"
# Mirrors server/classifier.py RESPONSE_FORMAT and OPTIONS.
FORMAT = {"type": "object", "properties": {"category": {"type": "string", "enum": CATEGORIES}}, "required": ["category"]}
OPTIONS = {"temperature": 0, "seed": 42}
PLAN = [("phi3:3.8b", None), ("gemma4:e4b", None)] * 3  # think not sent: gemma4 thinks, as in A1


def sh(*args):
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


def api(path, body=None, timeout=900):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def resident():
    return [(m["name"], round(m["size"] / 2**30, 2), m["size_vram"]) for m in api("/api/ps")["models"]]


def mem_available_gib():
    for line in sh("docker", "exec", CONTAINER, "cat", "/proc/meminfo").splitlines():
        if line.startswith("MemAvailable"):
            return round(int(line.split()[1]) / 2**20, 2)


def norm(text):
    return " ".join(text.split())[:150].lower()


def pick_tickets(n):
    import csv
    with open(REPO / "datasets/golden_test_set.csv", encoding="cp1252", newline="") as f:
        golden = {norm(r["narrative"]) for r in csv.DictReader(f)}
    picked = []
    for line in open(REPO / "tests/stress/data/tickets.jsonl", encoding="utf-8"):
        text = json.loads(line)["narrative"]
        if norm(text) not in golden and 100 <= len(text.split()) <= 250:
            picked.append(text)
        if len(picked) == n:
            return picked
    raise SystemExit(f"only found {len(picked)} non-golden tickets of typical length")


if sh("docker", "inspect", "-f", "{{.State.Running}}", CONTAINER) != "true":
    raise SystemExit(f"{CONTAINER} is not running, so port 11434 is not Docker's Ollama; stop native Ollama first")

OUT.mkdir(parents=True, exist_ok=True)
settings = sh("docker", "exec", CONTAINER, "sh", "-c", "env | grep ^OLLAMA_ | sort")
print(settings)
print(f"MemAvailable before: {mem_available_gib()} GiB; resident: {resident()}\n")

rows = []
for i, ((model, think), text) in enumerate(zip(PLAN, pick_tickets(len(PLAN))), 1):
    body = {"model": model, "prompt": build_prompt(text), "stream": False, "format": FORMAT, "options": OPTIONS}
    if think is not None:
        body["think"] = think
    t0 = time.perf_counter()
    r = api("/api/generate", body)
    wall = time.perf_counter() - t0
    row = {"call": i, "model": model, "think": think, "words": len(text.split()), "wall_s": round(wall, 2),
           "load_s": round(r.get("load_duration", 0) / 1e9, 2), "eval_tokens": r.get("eval_count"),
           "thinking_chars": len(r.get("thinking") or ""), "answer": r.get("response", "").strip(),
           "resident_after": resident(), "mem_available_gib": mem_available_gib()}
    rows.append(row)
    print(f"#{i} {model:11} think={think!s:5} wall {row['wall_s']:6.2f}s  load {row['load_s']:5.2f}s  "
          f"tokens {row['eval_tokens']:>4}  thinking {row['thinking_chars']:>4} chars  {row['answer']}")
    print(f"    resident: {row['resident_after']}  MemAvailable {row['mem_available_gib']} GiB")

ps_text = sh("docker", "exec", CONTAINER, "ollama", "ps")
names = {name for name, _, _ in rows[-1]["resident_after"]}
reloads = [r["call"] for r in rows[2:] if r["load_s"] > 1]  # calls 1-2 are each model's first load
verdict = "PASS" if {"phi3:3.8b", "gemma4:e4b"} <= names and not reloads else "FAIL"
print(f"\nollama ps:\n{ps_text}\n\nVerdict: {verdict} (both resident at end: {sorted(names)}; "
      f"reloads after first load: {reloads or 'none'})")

(OUT / "memcheck.json").write_text(json.dumps({"settings": settings, "calls": rows, "ollama_ps": ps_text,
                                               "verdict": verdict}, indent=2), encoding="utf-8")
(OUT / "ollama_ps.txt").write_text(ps_text + "\n", encoding="utf-8")
print(f"Evidence written to {OUT}")
