#!/usr/bin/env python3
"""loop.py — Review loop orchestration and state management.

Commands:
    init     Create a new review state file
    next     Advance to next round (prints: continue, converged, max_rounds)
    status   Show current loop status
    summary  Produce final review summary

Usage:
    python loop.py init [--max-rounds N] [--state PATH]
    python loop.py next --state PATH
    python loop.py status --state PATH
    python loop.py summary --state PATH
"""

import argparse
import json
import sys
from datetime import datetime, timezone


def cmd_init(args):
    state = {
        "version": 1,
        "created": datetime.now(timezone.utc).isoformat(),
        "max_rounds": args.max_rounds,
        "current_round": 1,
        "status": "active",
        "total_findings": 0,
        "rounds": {}
    }
    with open(args.state, "w") as fh:
        json.dump(state, fh, indent=2)
    print(json.dumps({"initialized": args.state, "max_rounds": args.max_rounds}))


def load_state(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: cannot read state '{path}': {e}", file=sys.stderr)
        sys.exit(1)


def save_state(path, state):
    with open(path, "w") as fh:
        json.dump(state, fh, indent=2)


def get_unresolved(state):
    unresolved = []
    for rkey, rdata in state["rounds"].items():
        responses = rdata.get("responses", {})
        for f in rdata.get("findings", []):
            if f["id"] not in responses:
                unresolved.append(f)
    return unresolved


def cmd_next(args):
    state = load_state(args.state)

    if state["status"] != "active":
        print(json.dumps({"result": state["status"]}))
        return

    unresolved = get_unresolved(state)

    if not unresolved:
        state["status"] = "converged"
        save_state(args.state, state)
        print(json.dumps({"result": "converged", "rounds_used": state["current_round"]}))
        return

    if state["current_round"] >= state["max_rounds"]:
        state["status"] = "max_rounds"
        save_state(args.state, state)
        print(json.dumps({"result": "max_rounds", "unresolved": len(unresolved)}))
        return

    state["current_round"] += 1
    save_state(args.state, state)
    print(json.dumps({"result": "continue", "round": state["current_round"], "unresolved": len(unresolved)}))


def cmd_status(args):
    state = load_state(args.state)
    unresolved = get_unresolved(state)

    resolved_count = 0
    for rdata in state["rounds"].values():
        resolved_count += len(rdata.get("responses", {}))

    print(json.dumps({
        "status": state["status"],
        "current_round": state["current_round"],
        "max_rounds": state["max_rounds"],
        "total_findings": state["total_findings"],
        "resolved": resolved_count,
        "unresolved": len(unresolved)
    }))


def cmd_summary(args):
    state = load_state(args.state)
    summary = {
        "status": state["status"],
        "rounds_used": state["current_round"],
        "total_findings": state["total_findings"],
        "by_disposition": {"fixed": 0, "disputed": 0, "accepted": 0, "unresolved": 0},
        "by_severity": {},
        "findings": []
    }

    for rdata in state["rounds"].values():
        responses = rdata.get("responses", {})
        for f in rdata.get("findings", []):
            disposition = responses.get(f["id"], {}).get("disposition", "unresolved")
            summary["by_disposition"][disposition] = summary["by_disposition"].get(disposition, 0) + 1
            sev = f["severity"]
            summary["by_severity"][sev] = summary["by_severity"].get(sev, 0) + 1
            summary["findings"].append({**f, "disposition": disposition})

    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Review loop orchestration.")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Initialize review state")
    p_init.add_argument("--max-rounds", type=int, default=3, help="Max review rounds (default: 3)")
    p_init.add_argument("--state", default=".review-state.json", help="State file path")

    p_next = sub.add_parser("next", help="Advance to next round")
    p_next.add_argument("--state", default=".review-state.json", help="State file path")

    p_status = sub.add_parser("status", help="Show loop status")
    p_status.add_argument("--state", default=".review-state.json", help="State file path")

    p_summary = sub.add_parser("summary", help="Produce final summary")
    p_summary.add_argument("--state", default=".review-state.json", help="State file path")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    {"init": cmd_init, "next": cmd_next, "status": cmd_status, "summary": cmd_summary}[args.command](args)


if __name__ == "__main__":
    main()
