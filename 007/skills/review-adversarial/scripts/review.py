#!/usr/bin/env python3
"""review.py — Record adversarial review findings into loop state.

Reads findings JSON from stdin or a file and appends them to the current
review round in the state file.

Usage:
    echo '[{"id":"F1",...}]' | python review.py --state .review-state.json
    python review.py --state .review-state.json --file findings.json

Finding schema:
    {
        "id": "F1",
        "severity": "critical|major|minor|nit",
        "category": "security|correctness|performance|clarity|maintainability|edge-case",
        "location": "file.py:42",
        "description": "What is wrong",
        "suggestion": "How to fix it"
    }
"""

import argparse
import json
import sys

VALID_SEVERITIES = {"critical", "major", "minor", "nit"}
VALID_CATEGORIES = {"security", "correctness", "performance", "clarity", "maintainability", "edge-case"}
REQUIRED_FIELDS = {"id", "severity", "category", "location", "description", "suggestion"}


def validate_finding(f):
    missing = REQUIRED_FIELDS - set(f.keys())
    if missing:
        return f"missing fields: {', '.join(sorted(missing))}"
    if f["severity"] not in VALID_SEVERITIES:
        return f"invalid severity '{f['severity']}'"
    if f["category"] not in VALID_CATEGORIES:
        return f"invalid category '{f['category']}'"
    return None


def main():
    parser = argparse.ArgumentParser(description="Record review findings into state.")
    parser.add_argument("--state", default=".review-state.json", help="Path to state file")
    parser.add_argument("--file", help="Read findings from file instead of stdin")
    args = parser.parse_args()

    try:
        with open(args.state) as fh:
            state = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: cannot read state file '{args.state}': {e}", file=sys.stderr)
        sys.exit(1)

    if state.get("status") == "converged":
        print("Error: review has already converged.", file=sys.stderr)
        sys.exit(1)

    source = open(args.file) if args.file else sys.stdin
    try:
        findings = json.load(source)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if args.file:
            source.close()

    if not isinstance(findings, list):
        print("Error: findings must be a JSON array.", file=sys.stderr)
        sys.exit(1)

    for i, f in enumerate(findings):
        err = validate_finding(f)
        if err:
            print(f"Error: finding[{i}]: {err}", file=sys.stderr)
            sys.exit(1)

    current_round = state["current_round"]
    round_key = f"round_{current_round}"
    if round_key not in state["rounds"]:
        state["rounds"][round_key] = {"findings": [], "responses": {}}

    state["rounds"][round_key]["findings"] = findings
    state["total_findings"] += len(findings)

    with open(args.state, "w") as fh:
        json.dump(state, fh, indent=2)

    print(json.dumps({"recorded": len(findings), "round": current_round}))


if __name__ == "__main__":
    main()
