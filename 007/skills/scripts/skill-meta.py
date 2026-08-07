#!/usr/bin/env python3
"""Read a frontmatter key from a SKILL.md, including nested `metadata.` keys.

The parser in resolve-deps.py handles top-level keys and `- item` lists only; nested children under
`metadata:` are silently dropped, so it cannot answer `metadata.runtime`.

Prints the value, or nothing if the key is absent. Exit 0 whether or not the key exists — "absent" is
an answer, not an error; exit 1 is reserved for a file that cannot be read.

    skill-meta.py sdlc/SKILL.md metadata.runtime
    skill-meta.py sdlc/SKILL.md name
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TOP = re.compile(r"^([A-Za-z_][\w-]*):\s*(.*)$")
NESTED = re.compile(r"^\s+([A-Za-z_][\w-]*):\s*(.*)$")


def frontmatter(path: Path) -> dict:
    """Flatten frontmatter to dotted keys: `metadata.runtime` -> value."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}

    out: dict[str, str] = {}
    parent = None
    for line in parts[1].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = TOP.match(line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            parent = key if not val else None
            if val:
                out[key] = val.strip("\"'")
            continue
        m = NESTED.match(line)
        if m and parent:
            val = m.group(2).strip()
            if val:
                out[f"{parent}.{m.group(1)}"] = val.strip("\"'")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("skill_md", help="path to a SKILL.md")
    ap.add_argument("key", help="frontmatter key, e.g. name or metadata.runtime")
    args = ap.parse_args()

    path = Path(args.skill_md)
    if not path.is_file():
        print(f"skill-meta: no such file: {path}", file=sys.stderr)
        return 1

    value = frontmatter(path).get(args.key, "")
    if value:
        print(value)
    return 0


if __name__ == "__main__":
    sys.exit(main())
