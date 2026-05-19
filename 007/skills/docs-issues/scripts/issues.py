#!/usr/bin/env python3
"""issues.py — Manage markdown-based issues in docs/reviews/.

Commands:
    list      List all issues (with optional --kind, --status filters)
    show      Show a single issue by ID
    new       Create a new issue file
    status    Change the status of an existing issue
    export    Export issues to a target (todo|stdout|github|gitlab)

Usage:
    python issues.py list [--root docs/reviews] [--kind bug] [--status open] [--format json|table]
    python issues.py show <id> [--root docs/reviews]
    python issues.py new --kind bug --title "..." [--severity major] [--category security] [--location file:42]
    python issues.py status <id> --set open|closed|wontfix
    python issues.py export --target todo [--output docs/todo.md]
    python issues.py export --target stdout [--kind bug] [--status open]
    python issues.py export --target github [--label-prefix review/] [--force]
    python issues.py export --target gitlab [--label-prefix review/] [--force]

Schema: YAML frontmatter with id, kind, title, severity, category, location,
status, created, source (optional), labels, target.{github,gitlab}.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

VALID_KINDS = ["bug", "feature", "debt", "question"]
VALID_STATUSES = ["open", "closed", "wontfix"]
VALID_SEVERITIES = ["critical", "major", "minor", "nit"]
DEFAULT_ROOT = "docs/reviews"

# --- Frontmatter parser/writer (minimal YAML for our schema) ---

def parse_frontmatter(text):
    """Parse YAML frontmatter from a markdown string. Returns (metadata, body)."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    fm_text = text[4:end]
    body = text[end + 5:]
    return _parse_yaml(fm_text), body


def _parse_yaml(text):
    """Parse a small subset of YAML: scalars, flow-style lists, one-level nested maps."""
    result = {}
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if line.startswith(" "):
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue
        key, _, raw = line.partition(":")
        key = key.strip()
        raw = raw.strip()
        if raw == "":
            # Distinguish nested map from empty scalar by looking at next non-blank line
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            is_nested = j < len(lines) and lines[j].startswith("  ") and ":" in lines[j]
            if is_nested:
                nested = {}
                while j < len(lines) and (lines[j].startswith("  ") or not lines[j].strip()):
                    if lines[j].strip() and ":" in lines[j]:
                        sub_k, _, sub_v = lines[j].strip().partition(":")
                        nested[sub_k.strip()] = _parse_scalar(sub_v.strip())
                    j += 1
                result[key] = nested
                i = j
            else:
                result[key] = None
                i += 1
        else:
            result[key] = _parse_scalar(raw)
            i += 1
    return result


def _parse_scalar(s):
    """Parse a scalar value: null, list, quoted string, or plain string."""
    if s == "null" or s == "~" or s == "":
        return None
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"').strip("'") for item in inner.split(",")]
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


def write_frontmatter(metadata, body):
    """Serialize metadata + body back to a markdown string."""
    out = ["---"]
    # Preferred field order
    order = ["id", "kind", "title", "severity", "category", "location",
             "status", "created", "source", "labels", "target"]
    keys = [k for k in order if k in metadata] + [k for k in metadata if k not in order]
    for key in keys:
        val = metadata[key]
        if isinstance(val, dict):
            out.append(f"{key}:")
            for sub_k, sub_v in val.items():
                out.append(f"  {sub_k}: {_format_scalar(sub_v)}")
        elif isinstance(val, list):
            if not val:
                out.append(f"{key}: []")
            else:
                items = ", ".join(str(v) for v in val)
                out.append(f"{key}: [{items}]")
        else:
            out.append(f"{key}: {_format_scalar(val)}")
    out.append("---")
    out.append("")
    out.append(body.lstrip("\n"))
    return "\n".join(out)


def _format_scalar(v):
    if v is None:
        return "null"
    s = str(v)
    # Quote if it contains special characters
    if any(c in s for c in [":", "#", "[", "]", "{", "}"]):
        return f'"{s}"'
    return s


# --- Issue tree operations ---

def find_root(start=None):
    """Find docs/reviews root by walking up from cwd, or use DEFAULT_ROOT."""
    cur = Path(start or os.getcwd()).resolve()
    while cur != cur.parent:
        candidate = cur / DEFAULT_ROOT
        if candidate.is_dir():
            return candidate
        cur = cur.parent
    return Path(DEFAULT_ROOT).resolve()


def load_all_issues(root):
    """Load all issues from root/{kind}/*.md. Returns list of (path, metadata, body)."""
    issues = []
    if not root.exists():
        return issues
    for kind_dir in sorted(root.iterdir()):
        if not kind_dir.is_dir():
            continue
        for f in sorted(kind_dir.glob("*.md")):
            try:
                text = f.read_text()
                meta, body = parse_frontmatter(text)
                if "id" in meta:
                    issues.append((f, meta, body))
            except Exception:
                continue
    return issues


def find_by_id(root, issue_id):
    """Find an issue by ID. Returns (path, metadata, body) or None."""
    for path, meta, body in load_all_issues(root):
        if meta.get("id") == issue_id:
            return path, meta, body
    return None


def slugify(title):
    """Convert title to filename-safe slug."""
    s = title.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:60]


def next_id(root, kind):
    """Allocate next sequential ID for the given kind (e.g., bug-002)."""
    max_n = 0
    prefix = f"{kind}-"
    for _, meta, _ in load_all_issues(root):
        iid = meta.get("id", "")
        if iid.startswith(prefix):
            try:
                n = int(iid[len(prefix):])
                max_n = max(max_n, n)
            except ValueError:
                pass
    return f"{kind}-{max_n + 1:03d}"


# --- Commands ---

def cmd_list(args):
    root = Path(args.root) if args.root else find_root()
    issues = load_all_issues(root)
    if args.kind:
        issues = [i for i in issues if i[1].get("kind") == args.kind]
    if args.status:
        issues = [i for i in issues if i[1].get("status") == args.status]

    if args.format == "json":
        out = [{"id": m.get("id"), "kind": m.get("kind"), "title": m.get("title"),
                "status": m.get("status"), "severity": m.get("severity"),
                "path": str(p)} for p, m, _ in issues]
        print(json.dumps(out, indent=2))
    else:
        if not issues:
            print("(no issues)")
            return
        for path, meta, _ in issues:
            print(f"  {meta.get('id', '?'):<14} {meta.get('kind', '?'):<8} "
                  f"{meta.get('status', '?'):<8} {meta.get('severity', '?'):<8} "
                  f"{meta.get('title', '?')}")


def cmd_show(args):
    root = Path(args.root) if args.root else find_root()
    found = find_by_id(root, args.id)
    if not found:
        print(f"Error: issue '{args.id}' not found.", file=sys.stderr)
        sys.exit(1)
    path, meta, body = found
    print(json.dumps({"path": str(path), "metadata": meta, "body": body}, indent=2))


def cmd_new(args):
    root = Path(args.root) if args.root else find_root()
    if args.kind not in VALID_KINDS:
        print(f"Error: invalid kind '{args.kind}'. Must be: {', '.join(VALID_KINDS)}", file=sys.stderr)
        sys.exit(1)
    if args.severity and args.severity not in VALID_SEVERITIES:
        print(f"Error: invalid severity '{args.severity}'. Must be: {', '.join(VALID_SEVERITIES)}", file=sys.stderr)
        sys.exit(1)

    kind_dir = root / f"{args.kind}s"
    kind_dir.mkdir(parents=True, exist_ok=True)

    issue_id = next_id(root, args.kind)
    today = date.today().isoformat()
    slug = slugify(args.title)
    filename = f"{today}-{slug}.md"
    path = kind_dir / filename

    metadata = {
        "id": issue_id,
        "kind": args.kind,
        "title": args.title,
        "severity": args.severity or "minor",
        "category": args.category or "",
        "location": args.location or "",
        "status": "open",
        "created": today,
        "labels": args.labels.split(",") if args.labels else [],
        "target": {"github": None, "gitlab": None}
    }
    if args.source:
        metadata["source"] = args.source

    body = f"\n## Description\n\n{args.description or '(describe the issue)'}\n"
    if args.kind == "feature":
        body += "\n## Acceptance Criteria\n\n- [ ] (criteria)\n"

    path.write_text(write_frontmatter(metadata, body))
    print(json.dumps({"created": str(path), "id": issue_id}))


def cmd_status(args):
    root = Path(args.root) if args.root else find_root()
    if args.set not in VALID_STATUSES:
        print(f"Error: invalid status '{args.set}'. Must be: {', '.join(VALID_STATUSES)}", file=sys.stderr)
        sys.exit(1)
    found = find_by_id(root, args.id)
    if not found:
        print(f"Error: issue '{args.id}' not found.", file=sys.stderr)
        sys.exit(1)
    path, meta, body = found
    meta["status"] = args.set
    path.write_text(write_frontmatter(meta, body))
    print(json.dumps({"id": args.id, "status": args.set, "path": str(path)}))


# --- Export targets ---

TODO_BEGIN = "<!-- BEGIN: docs-issues -->"
TODO_END = "<!-- END: docs-issues -->"


def export_todo(args, issues):
    output_path = Path(args.output) if args.output else Path("docs/todo.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Group by kind
    by_kind = {}
    for path, meta, _ in issues:
        if meta.get("status") != "open":
            continue
        by_kind.setdefault(meta.get("kind", "other"), []).append((path, meta))

    lines = [TODO_BEGIN, "<!-- generated by docs-issues; do not edit between markers -->", ""]
    for kind in ["bug", "feature", "debt", "question"]:
        items = by_kind.get(kind, [])
        if not items:
            continue
        heading = {"bug": "Bugs", "feature": "Features", "debt": "Tech Debt", "question": "Open Questions"}[kind]
        lines.append(f"## {heading}")
        lines.append("")
        for path, meta in items:
            try:
                rel = path.resolve().relative_to(output_path.resolve().parent)
            except ValueError:
                rel = path
            sev = meta.get("severity", "")
            sev_tag = f" — {sev}" if sev else ""
            lines.append(f"- [ ] [{meta.get('title', '?')}]({rel}){sev_tag}")
        lines.append("")
    lines.append(TODO_END)
    new_block = "\n".join(lines)

    # Splice into existing file if present
    if output_path.exists():
        existing = output_path.read_text()
        if TODO_BEGIN in existing and TODO_END in existing:
            pre, _, rest = existing.partition(TODO_BEGIN)
            _, _, post = rest.partition(TODO_END)
            output_path.write_text(pre + new_block + post)
        else:
            sep = "\n\n" if existing and not existing.endswith("\n") else "\n"
            output_path.write_text(existing + sep + new_block + "\n")
    else:
        output_path.write_text(new_block + "\n")

    print(json.dumps({"exported": str(output_path), "count": sum(len(v) for v in by_kind.values())}))


def export_stdout(args, issues):
    for path, meta, body in issues:
        if args.kind and meta.get("kind") != args.kind:
            continue
        if args.status and meta.get("status") != args.status:
            continue
        print(f"# [{meta.get('id')}] {meta.get('title')}")
        info_parts = [f"kind: {meta.get('kind')}"]
        for key in ("severity", "status", "category", "location"):
            val = meta.get(key)
            if val:
                info_parts.append(f"{key}: {val}")
        print(" | ".join(info_parts))
        print(body.strip())
        print()
        print("---")
        print()


def export_tracker(args, issues, target):
    """Generic tracker export (github via gh, gitlab via glab)."""
    cli = {"github": "gh", "gitlab": "glab"}[target]
    if not shutil.which(cli):
        print(f"Error: '{cli}' CLI not found on PATH. Install it to use --target {target}.", file=sys.stderr)
        sys.exit(2)

    label_prefix = args.label_prefix or "review/"
    pushed = []
    skipped = []

    for path, meta, body in issues:
        if meta.get("status") != "open":
            continue
        existing_id = meta.get("target", {}).get(target)
        if existing_id and not args.force:
            skipped.append({"id": meta.get("id"), "target_id": existing_id})
            continue

        labels = [f"{label_prefix}{meta.get('kind')}"]
        if meta.get("category"):
            labels.append(meta["category"])
        for lbl in meta.get("labels") or []:
            if lbl:
                labels.append(lbl)

        title = meta.get("title", "Untitled")
        body_text = body.strip()

        if target == "github":
            cmd = [cli, "issue", "create", "--title", title, "--body", body_text]
            for lbl in labels:
                cmd += ["--label", lbl]
        else:  # gitlab
            cmd = [cli, "issue", "create", "--title", title, "--description", body_text]
            if labels:
                cmd += ["--label", ",".join(labels)]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            url_or_id = result.stdout.strip().split()[-1] if result.stdout.strip() else ""
            meta.setdefault("target", {})[target] = url_or_id
            path.write_text(write_frontmatter(meta, body))
            pushed.append({"id": meta.get("id"), "target_id": url_or_id})
        except subprocess.CalledProcessError as e:
            print(f"Error pushing {meta.get('id')}: {e.stderr.strip()}", file=sys.stderr)
            sys.exit(1)

    print(json.dumps({"pushed": pushed, "skipped": skipped}, indent=2))


def cmd_export(args):
    root = Path(args.root) if args.root else find_root()
    issues = load_all_issues(root)
    if args.target == "todo":
        export_todo(args, issues)
    elif args.target == "stdout":
        export_stdout(args, issues)
    elif args.target in ("github", "gitlab"):
        export_tracker(args, issues, args.target)
    else:
        print(f"Error: unknown target '{args.target}'", file=sys.stderr)
        sys.exit(1)


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(description="Manage markdown-based issues in docs/reviews/.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", help="Root directory (default: auto-detect docs/reviews)")
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", parents=[common], help="List all issues")
    p_list.add_argument("--kind", choices=VALID_KINDS)
    p_list.add_argument("--status", choices=VALID_STATUSES)
    p_list.add_argument("--format", choices=["json", "table"], default="table")

    p_show = sub.add_parser("show", parents=[common], help="Show a single issue")
    p_show.add_argument("id", help="Issue ID (e.g., bug-001)")

    p_new = sub.add_parser("new", parents=[common], help="Create a new issue")
    p_new.add_argument("--kind", required=True, choices=VALID_KINDS)
    p_new.add_argument("--title", required=True)
    p_new.add_argument("--severity", choices=VALID_SEVERITIES)
    p_new.add_argument("--category")
    p_new.add_argument("--location")
    p_new.add_argument("--labels", help="Comma-separated labels")
    p_new.add_argument("--description")
    p_new.add_argument("--source", help="Provenance (e.g., review-adversarial:F1)")

    p_status = sub.add_parser("status", parents=[common], help="Change issue status")
    p_status.add_argument("id", help="Issue ID")
    p_status.add_argument("--set", required=True, choices=VALID_STATUSES)

    p_export = sub.add_parser("export", parents=[common], help="Export issues to a target")
    p_export.add_argument("--target", required=True, choices=["todo", "stdout", "github", "gitlab"])
    p_export.add_argument("--output", help="Output path (for todo target)")
    p_export.add_argument("--kind", choices=VALID_KINDS)
    p_export.add_argument("--status", choices=VALID_STATUSES)
    p_export.add_argument("--label-prefix", help="Label prefix for tracker exports (default: review/)")
    p_export.add_argument("--force", action="store_true", help="Re-push already-exported issues")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    {"list": cmd_list, "show": cmd_show, "new": cmd_new,
     "status": cmd_status, "export": cmd_export}[args.command](args)


if __name__ == "__main__":
    main()
