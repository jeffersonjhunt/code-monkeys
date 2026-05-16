#!/usr/bin/env python3
"""respond.py — Record author responses to review findings.

Marks findings as fixed, disputed, or accepted (accept-risk).

Usage:
    python respond.py --state .review-state.json --resolve F1=fixed F2=disputed F3=accepted
    python respond.py --state .review-state.json --resolve F2=disputed --rationale "F2:Handled at LB layer"
"""

import argparse
import json
import sys

VALID_DISPOSITIONS = {"fixed", "disputed", "accepted"}


def main():
    parser = argparse.ArgumentParser(description="Record responses to review findings.")
    parser.add_argument("--state", default=".review-state.json", help="Path to state file")
    parser.add_argument("--resolve", nargs="+", required=True, help="ID=disposition pairs (e.g., F1=fixed)")
    parser.add_argument("--rationale", nargs="*", default=[], help="ID:rationale pairs for disputed findings")
    args = parser.parse_args()

    try:
        with open(args.state) as fh:
            state = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: cannot read state '{args.state}': {e}", file=sys.stderr)
        sys.exit(1)

    # Parse rationale map
    rationale_map = {}
    for r in args.rationale:
        if ":" not in r:
            print(f"Error: rationale must be 'ID:text', got '{r}'", file=sys.stderr)
            sys.exit(1)
        fid, text = r.split(":", 1)
        rationale_map[fid] = text

    # Collect all known finding IDs
    known_ids = set()
    for rdata in state["rounds"].values():
        for f in rdata.get("findings", []):
            known_ids.add(f["id"])

    # Process resolutions
    resolutions = []
    for item in args.resolve:
        if "=" not in item:
            print(f"Error: --resolve must be 'ID=disposition', got '{item}'", file=sys.stderr)
            sys.exit(1)
        fid, disposition = item.split("=", 1)
        if disposition not in VALID_DISPOSITIONS:
            print(f"Error: invalid disposition '{disposition}' for {fid}. Must be: {', '.join(sorted(VALID_DISPOSITIONS))}", file=sys.stderr)
            sys.exit(1)
        if fid not in known_ids:
            print(f"Error: unknown finding ID '{fid}'", file=sys.stderr)
            sys.exit(1)
        resolutions.append((fid, disposition))

    # Apply resolutions to the round that contains each finding
    for fid, disposition in resolutions:
        entry = {"disposition": disposition}
        if disposition == "disputed" and fid in rationale_map:
            entry["rationale"] = rationale_map[fid]
        for rdata in state["rounds"].values():
            finding_ids = [f["id"] for f in rdata.get("findings", [])]
            if fid in finding_ids:
                rdata.setdefault("responses", {})[fid] = entry
                break

    with open(args.state, "w") as fh:
        json.dump(state, fh, indent=2)

    print(json.dumps({"resolved": len(resolutions), "ids": [r[0] for r in resolutions]}))


if __name__ == "__main__":
    main()
