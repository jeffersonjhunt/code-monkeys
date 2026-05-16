#!/usr/bin/env python3
"""Fibonacci Generator - Agent Skill

Generates Fibonacci numbers starting from a given position in the sequence.

Dependencies: None (Python 3.6+ standard library only)

Usage:
    python fibonacci-generator.py [--start N] [--count N]

Arguments:
    --start N   Starting position in the Fibonacci sequence (0-indexed, default: 0)
    --count N   Number of Fibonacci numbers to return (default: 10)

Examples:
    python fibonacci-generator.py                  # First 10: 0,1,1,2,3,5,8,13,21,34
    python fibonacci-generator.py --start 5        # 10 numbers starting at position 5
    python fibonacci-generator.py --start 5 --count 3  # 3 numbers starting at position 5
"""

import argparse
import sys
import json


def fibonacci(start=0, count=10):
    """Generate `count` Fibonacci numbers starting from position `start`.

    Position 0 = 0, position 1 = 1, position 2 = 1, position 3 = 2, etc.
    """
    if count <= 0:
        return []

    # Generate up to start + count numbers
    a, b = 0, 1
    seq = []
    for i in range(start + count):
        if i >= start:
            seq.append(a)
        a, b = b, a + b
    return seq


def main():
    parser = argparse.ArgumentParser(description="Generate Fibonacci numbers.")
    parser.add_argument("--start", type=int, default=0,
                        help="Starting position in the sequence (0-indexed, default: 0)")
    parser.add_argument("--count", type=int, default=10,
                        help="Number of Fibonacci numbers to return (default: 10)")
    parser.add_argument("--format", choices=["json", "csv", "plain"], default="json",
                        help="Output format (default: json)")
    args = parser.parse_args()

    if args.start < 0:
        print("Error: --start must be a non-negative integer.", file=sys.stderr)
        sys.exit(1)
    if args.count < 0:
        print("Error: --count must be a non-negative integer.", file=sys.stderr)
        sys.exit(1)

    result = fibonacci(args.start, args.count)

    if args.format == "json":
        print(json.dumps({"start": args.start, "count": args.count, "values": result}))
    elif args.format == "csv":
        print(",".join(str(v) for v in result))
    else:
        print("\n".join(str(v) for v in result))


if __name__ == "__main__":
    main()
