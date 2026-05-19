#!/usr/bin/env python3
"""promote.py — Promote review findings to docs/reviews/ markdown files.

Reads a review-adversarial state file and creates one markdown file per finding
under docs/reviews/{kind}s/, ready for export via the docs-issues skill.

Each finding is classified into a kind:
- security/correctness/edge-case      → bug
- performance/maintainability         → debt (unless severity is critical/major)
- clarity                             → debt
- (no auto-detection)                 → user must --classify

The agent should typically pass --classify ID=kind for each finding it wants
promoted, since classification is a judgement call.

Usage:
    python promote.py --state .review-state.json --output docs/reviews/
    python promote.py --state .review-state.json --output docs/reviews/ \\
        --classify F1=bug F2=feature F3=debt
    python promote.py --state .review-state.json --output docs/reviews/ \\
        --skip nit,disputed
"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path


VALID_KINDS = ["bug", "feature", "debt", "question"]

# Default category → kind mapping (used when no explicit --classify given)
CATEGORY_TO_KIND = {
    "security": "bug",
    "correctness": "bug",
    "edge-case": "bug",
    "performance": "debt",
    "maintainability": "debt",
    "clarity": "debt",
}


def slugify(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:60]


def format_scalar(v):
    if v is None:
        return "null"
    s = str(v)
    if any(c in s for c in [":", "#", "[", "]", "{", "}"]):
        return f'"{s}"'
    return s


def write_markdown(path, metadata, body):
    """Write a docs-issues compatible markdown file."""
    lines = ["---"]
    order = ["id", "kind", "title", "severity", "category", "location",
             "status", "created", "source", "labels", "target"]
    keys = [k for k in order if k in metadata]
    for key in keys:
        val = metadata[key]
        if isinstance(val, dict):
            lines.append(f"{key}:")
            for sub_k, sub_v in val.items():
                lines.append(f"  {sub_k}: {format_scalar(sub_v)}")
        elif isinstance(val, list):
            if not val:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}: [{', '.join(str(v) for v in val)}]")
        else:
            lines.append(f"{key}: {format_scalar(val)}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    path.write_text("\n".join(lines))


def next_id(output_root, kind):
    """Find the next sequential ID for a kind by scanning existing files."""
    kind_dir = output_root / f"{kind}s"
    max_n = 0
    if kind_dir.is_dir():
        prefix = f"{kind}-"
        for f in kind_dir.glob("*.md"):
            text = f.read_text()
            m = re.search(r"^id:\s*(\S+)", text, re.MULTILINE)
            if m and m.group(1).startswith(prefix):
                try:
                    n = int(m.group(1)[len(prefix):])
                    max_n = max(max_n, n)
                except ValueError:
                    pass
    return f"{kind}-{max_n + 1:03d}"


def classify_finding(finding, classify_map):
    """Determine the kind for a finding based on --classify or category."""
    fid = finding["id"]
    if fid in classify_map:
        return classify_map[fid]
    return CATEGORY_TO_KIND.get(finding.get("category", ""), None)


def main():
    parser = argparse.ArgumentParser(description="Promote review findings to docs/reviews markdown files.")
    parser.add_argument("--state", required=True, help="Review state file (from loop.py init)")
    parser.add_argument("--output", default="docs/reviews", help="Output root for markdown files")
    parser.add_argument("--classify", nargs="*", default=[],
                        help="Explicit ID=kind classifications (e.g., F1=bug F2=feature)")
    parser.add_argument("--skip", default="nit,disputed",
                        help="Comma-separated severity/disposition values to skip (default: nit,disputed)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be promoted without writing files")
    args = parser.parse_args()

    try:
        with open(args.state) as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: cannot read state file '{args.state}': {e}", file=sys.stderr)
        sys.exit(1)

    classify_map = {}
    for item in args.classify:
        if "=" not in item:
            print(f"Error: --classify expects ID=kind, got '{item}'", file=sys.stderr)
            sys.exit(1)
        fid, kind = item.split("=", 1)
        if kind not in VALID_KINDS:
            print(f"Error: invalid kind '{kind}' for {fid}. Must be: {', '.join(VALID_KINDS)}", file=sys.stderr)
            sys.exit(1)
        classify_map[fid] = kind

    skip_set = {s.strip() for s in args.skip.split(",") if s.strip()}
    output_root = Path(args.output)

    promoted = []
    skipped = []

    for round_key, round_data in state.get("rounds", {}).items():
        responses = round_data.get("responses", {})
        for finding in round_data.get("findings", []):
            fid = finding["id"]

            # Skip already-promoted
            if finding.get("promoted"):
                skipped.append({"finding": fid, "reason": "already promoted"})
                continue

            # Apply skip rules
            if finding.get("severity") in skip_set:
                skipped.append({"finding": fid, "reason": f"severity={finding['severity']}"})
                continue
            disposition = responses.get(fid, {}).get("disposition")
            if disposition in skip_set:
                skipped.append({"finding": fid, "reason": f"disposition={disposition}"})
                continue

            # Classify
            kind = classify_finding(finding, classify_map)
            if not kind:
                skipped.append({"finding": fid, "reason": "unclassified (use --classify)"})
                continue

            # Build metadata
            today = date.today().isoformat()
            issue_id = next_id(output_root, kind)
            slug = slugify(finding["title"]) if finding.get("title") else slugify(finding["description"][:60])
            filename = f"{today}-{slug}.md"
            kind_dir = output_root / f"{kind}s"
            target_path = kind_dir / filename

            metadata = {
                "id": issue_id,
                "kind": kind,
                "title": finding.get("title") or finding["description"][:80],
                "severity": finding["severity"],
                "category": finding["category"],
                "location": finding.get("location", ""),
                "status": "open",
                "created": today,
                "source": f"review-adversarial:{fid}",
                "labels": [finding["category"]],
                "target": {"github": None, "gitlab": None},
            }

            body_parts = ["", "## Description", "", finding["description"], ""]
            if finding.get("suggestion"):
                body_parts += ["## Suggested Fix", "", finding["suggestion"], ""]
            if disposition:
                body_parts += ["## Review Context",
                               f"Found during adversarial review (round {round_data.get('round', '?')}). "
                               f"Disposition: {disposition}.", ""]
            else:
                body_parts += ["## Review Context",
                               f"Found during adversarial review (round {round_data.get('round', '?')}).", ""]
            body = "\n".join(body_parts)

            if args.dry_run:
                promoted.append({"finding": fid, "kind": kind, "would_write": str(target_path)})
            else:
                kind_dir.mkdir(parents=True, exist_ok=True)
                # Avoid clobbering existing files with the same name
                if target_path.exists():
                    n = 1
                    while (kind_dir / f"{today}-{slug}-{n}.md").exists():
                        n += 1
                    target_path = kind_dir / f"{today}-{slug}-{n}.md"
                write_markdown(target_path, metadata, body)
                finding["promoted"] = True
                finding["markdown_path"] = str(target_path)
                promoted.append({"finding": fid, "kind": kind, "id": issue_id, "path": str(target_path)})

    # Write back state if not dry-run
    if not args.dry_run:
        with open(args.state, "w") as f:
            json.dump(state, f, indent=2)

    print(json.dumps({"promoted": promoted, "skipped": skipped}, indent=2))


if __name__ == "__main__":
    main()
