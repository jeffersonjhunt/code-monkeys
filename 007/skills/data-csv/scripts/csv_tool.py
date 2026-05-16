#!/usr/bin/env python3
"""CSV Tool - Agent Skill

Parse, query, and transform CSV files.

Dependencies: None (Python 3.6+ standard library only)

Usage:
    python csv_tool.py <command> <file> [options]

Commands:
    info    - Show column names and row count
    head    - Print first N rows
    filter  - Filter rows by column value
    select  - Select specific columns
    sort    - Sort by column
    json    - Convert to JSON
"""

import argparse
import csv
import json
import sys


def cmd_info(rows, headers, args):
    print(json.dumps({"columns": headers, "rows": len(rows)}))


def cmd_head(rows, headers, args):
    n = args.rows or 5
    out = [dict(zip(headers, r)) for r in rows[:n]]
    print(json.dumps(out, indent=2))


def cmd_filter(rows, headers, args):
    if args.column not in headers:
        print(f"Error: column '{args.column}' not found", file=sys.stderr)
        sys.exit(1)
    idx = headers.index(args.column)
    result = []
    for r in rows:
        val = r[idx]
        if args.eq and val == args.eq:
            result.append(r)
        elif args.contains and args.contains in val:
            result.append(r)
        elif args.gt is not None:
            try:
                if float(val) > args.gt:
                    result.append(r)
            except ValueError:
                pass
        elif args.lt is not None:
            try:
                if float(val) < args.lt:
                    result.append(r)
            except ValueError:
                pass
    out = [dict(zip(headers, r)) for r in result]
    print(json.dumps(out, indent=2))


def cmd_select(rows, headers, args):
    cols = [c.strip() for c in args.columns.split(",")]
    indices = []
    for c in cols:
        if c not in headers:
            print(f"Error: column '{c}' not found", file=sys.stderr)
            sys.exit(1)
        indices.append(headers.index(c))
    out = [dict(zip(cols, [r[i] for i in indices])) for r in rows]
    print(json.dumps(out, indent=2))


def cmd_sort(rows, headers, args):
    if args.by not in headers:
        print(f"Error: column '{args.by}' not found", file=sys.stderr)
        sys.exit(1)
    idx = headers.index(args.by)

    def sort_key(r):
        try:
            return float(r[idx])
        except ValueError:
            return r[idx]

    sorted_rows = sorted(rows, key=sort_key, reverse=args.desc)
    out = [dict(zip(headers, r)) for r in sorted_rows]
    print(json.dumps(out, indent=2))


def cmd_json(rows, headers, args):
    out = [dict(zip(headers, r)) for r in rows]
    print(json.dumps(out, indent=2))


def main():
    parser = argparse.ArgumentParser(description="CSV parsing and transformation.")
    parser.add_argument("command", choices=["info", "head", "filter", "select", "sort", "json"])
    parser.add_argument("file", help="Path to CSV file")
    parser.add_argument("--rows", type=int, help="Number of rows (head)")
    parser.add_argument("--column", help="Column name (filter)")
    parser.add_argument("--eq", help="Equals value (filter)")
    parser.add_argument("--contains", help="Contains value (filter)")
    parser.add_argument("--gt", type=float, help="Greater than (filter)")
    parser.add_argument("--lt", type=float, help="Less than (filter)")
    parser.add_argument("--columns", help="Comma-separated column names (select)")
    parser.add_argument("--by", help="Column to sort by (sort)")
    parser.add_argument("--desc", action="store_true", help="Sort descending")
    args = parser.parse_args()

    with open(args.file, newline="") as f:
        reader = csv.reader(f)
        headers = next(reader)
        rows = list(reader)

    cmds = {"info": cmd_info, "head": cmd_head, "filter": cmd_filter,
            "select": cmd_select, "sort": cmd_sort, "json": cmd_json}
    cmds[args.command](rows, headers, args)


if __name__ == "__main__":
    main()
