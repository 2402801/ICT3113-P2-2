#!/usr/bin/env python3
"""Converts the dataset CSV into one JSON request body per line for JMeter to read."""
import argparse
import csv
import json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--narrative-column", default="narrative")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", default="data/tickets.jsonl")
    args = parser.parse_args()

    count = 0
    with open(args.csv, encoding="utf-8") as src, open(args.output, "w", encoding="utf-8") as dst:
        for row in csv.DictReader(src):
            narrative = row.get(args.narrative_column, "").strip()
            if not narrative:
                continue
            dst.write(json.dumps({"narrative": narrative}) + "\n")
            count += 1
            if args.limit and count >= args.limit:
                break

    print(f"Wrote {count} request bodies to {args.output}")


if __name__ == "__main__":
    main()
