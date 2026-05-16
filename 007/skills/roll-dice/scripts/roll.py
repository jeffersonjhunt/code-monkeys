#!/usr/bin/env python3
"""Roll Dice - Agent Skill

Roll one or more dice with configurable sides. Supports standard dice notation.

Dependencies: None (Python 3.6+ standard library only)

Usage:
    python roll.py [--sides N] [--rolls N]
    python roll.py --notation 2d6
    python roll.py --notation 3d8+2

Examples:
    python roll.py                  # Roll 1d6
    python roll.py --sides 20      # Roll 1d20
    python roll.py --rolls 3       # Roll 3d6
    python roll.py --notation 2d6  # Roll 2d6
    python roll.py --notation 3d8+2  # Roll 3d8 and add 2
"""

import argparse
import json
import random
import re
import sys


def roll_dice(sides=6, rolls=1):
    """Roll `rolls` dice each with `sides` sides."""
    return [random.randint(1, sides) for _ in range(rolls)]


def parse_notation(notation):
    """Parse dice notation like 2d6, d20, 3d8+2, 2d6-1."""
    m = re.match(r'^(\d*)d(\d+)([+-]\d+)?$', notation.strip())
    if not m:
        return None
    rolls = int(m.group(1)) if m.group(1) else 1
    sides = int(m.group(2))
    modifier = int(m.group(3)) if m.group(3) else 0
    return rolls, sides, modifier


def main():
    parser = argparse.ArgumentParser(description="Roll dice.")
    parser.add_argument("--sides", type=int, default=6, help="Number of sides (default: 6)")
    parser.add_argument("--rolls", type=int, default=1, help="Number of dice to roll (default: 1)")
    parser.add_argument("--notation", help="Dice notation (e.g., 2d6, 3d8+2)")
    args = parser.parse_args()

    if args.notation:
        parsed = parse_notation(args.notation)
        if not parsed:
            print(f"Error: invalid dice notation '{args.notation}'.", file=sys.stderr)
            sys.exit(1)
        rolls, sides, modifier = parsed
    else:
        if args.sides < 1:
            print("Error: --sides must be at least 1.", file=sys.stderr)
            sys.exit(1)
        if args.rolls < 1:
            print("Error: --rolls must be at least 1.", file=sys.stderr)
            sys.exit(1)
        rolls, sides, modifier = args.rolls, args.sides, 0

    results = roll_dice(sides, rolls)
    total = sum(results) + modifier
    output = {"sides": sides, "rolls": rolls, "results": results, "total": total}
    if modifier:
        output["modifier"] = modifier
    print(json.dumps(output))


if __name__ == "__main__":
    main()
