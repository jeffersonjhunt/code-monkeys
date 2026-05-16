#!/usr/bin/env python3
"""Fibonacci Tiles - Agent Skill

Generates line-art ASCII of Fibonacci tiles arranged in a counter-clockwise spiral.
Each tile is a square whose side length equals the corresponding Fibonacci number.
Tiles are placed adjacent to the previous tile in counter-clockwise order:
RIGHT, DOWN, LEFT, UP, repeating. Rendered with box-drawing characters.

Dependencies: fibonacci-generator.py (in the same directory)

Usage:
    python fibonacci-tiles.py [--start N] [--count N]

Arguments:
    --start N   Starting position in the Fibonacci sequence (default: 1)
    --count N   Number of tiles to render (default: 6)
"""

import argparse
import json
import os
import subprocess
import sys


def get_fibonacci(start, count):
    """Call fibonacci-generator.py and return the sequence."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    gen_path = os.path.join(script_dir, "fibonacci-generator.py")

    if not os.path.exists(gen_path):
        print(f"Error: fibonacci-generator.py not found at {gen_path}", file=sys.stderr)
        sys.exit(1)

    result = subprocess.run(
        [sys.executable, gen_path, "--start", str(start), "--count", str(count)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Error from fibonacci-generator.py: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(result.stdout)
    return data["values"]


def render_tiles(values, char=None):
    """Place Fibonacci square tiles in a counter-clockwise spiral and render as line art."""
    if not values:
        return ""

    # Filter out zeros - can't draw a 0-sized tile
    tiles = [v for v in values if v > 0]
    if not tiles:
        return "(all tile sizes are 0)"

    # Place tiles using bounding-box approach.
    # After placing each tile, track the bounding rectangle of all placed tiles.
    # Next tile is placed flush against the appropriate side.
    # Counter-clockwise: RIGHT, DOWN, LEFT, UP

    directions = ['up', 'left', 'down', 'right']
    # Each placement: (x, y, size) where (x,y) is top-left corner
    placements = []

    # Place first tile at origin
    placements.append((0, 0, tiles[0]))
    # Bounding box: left, top, right, bottom (exclusive)
    bb_l, bb_t, bb_r, bb_b = 0, 0, tiles[0], tiles[0]

    for idx in range(1, len(tiles)):
        size = tiles[idx]
        d = directions[idx % 4]

        if d == 'right':
            # Place to the right of bounding box, aligned to top
            x, y = bb_r, bb_t
        elif d == 'down':
            # Place below bounding box, aligned to right edge
            x, y = bb_r - size, bb_b
        elif d == 'left':
            # Place to the left of bounding box, aligned to bottom
            x, y = bb_l - size, bb_b - size
        elif d == 'up':
            # Place above bounding box, aligned to left edge
            x, y = bb_l, bb_t - size

        placements.append((x, y, size))
        # Update bounding box
        bb_l = min(bb_l, x)
        bb_t = min(bb_t, y)
        bb_r = max(bb_r, x + size)
        bb_b = max(bb_b, y + size)

    # Determine grid bounds
    min_x = min(x for x, y, s in placements)
    min_y = min(y for x, y, s in placements)
    max_x = max(x + s for x, y, s in placements)
    max_y = max(y + s for x, y, s in placements)

    cell_w = max_x - min_x
    cell_h = max_y - min_y

    # Build edge maps on the unit grid
    # h_edges[row][col] = horizontal line from (col,row) to (col+1,row)
    # v_edges[row][col] = vertical line from (col,row) to (col,row+1)
    h_edges = [[False] * cell_w for _ in range(cell_h + 1)]
    v_edges = [[False] * (cell_w + 1) for _ in range(cell_h)]

    for x, y, size in placements:
        ox, oy = x - min_x, y - min_y
        for c in range(size):
            h_edges[oy][ox + c] = True          # top
            h_edges[oy + size][ox + c] = True   # bottom
        for r in range(size):
            v_edges[oy + r][ox] = True          # left
            v_edges[oy + r][ox + size] = True   # right

    # Render with box-drawing characters
    # Each unit cell = 2 chars wide, 1 char tall
    lines = []
    for row in range(cell_h + 1):
        line = []
        for col in range(cell_w + 1):
            up = row > 0 and v_edges[row - 1][col]
            down = row < cell_h and v_edges[row][col]
            left = col > 0 and h_edges[row][col - 1]
            right = col < cell_w and h_edges[row][col]
            line.append(_node_char(up, down, left, right))
            if col < cell_w:
                line.append('──' if h_edges[row][col] else '  ')
        lines.append(''.join(line))

        if row < cell_h:
            line = []
            for col in range(cell_w + 1):
                line.append('│' if v_edges[row][col] else ' ')
                if col < cell_w:
                    line.append('  ')
            lines.append(''.join(line))

    return '\n'.join(lines)


def _node_char(up, down, left, right):
    """Return the appropriate box-drawing character for a node intersection."""
    key = (up, down, left, right)
    table = {
        (False, False, False, False): ' ',
        (False, False, False, True):  '╶',
        (False, False, True,  False): '╴',
        (False, False, True,  True):  '─',
        (False, True,  False, False): '╷',
        (False, True,  False, True):  '┌',
        (False, True,  True,  False): '┐',
        (False, True,  True,  True):  '┬',
        (True,  False, False, False): '╵',
        (True,  False, False, True):  '└',
        (True,  False, True,  False): '┘',
        (True,  False, True,  True):  '┴',
        (True,  True,  False, False): '│',
        (True,  True,  False, True):  '├',
        (True,  True,  True,  False): '┤',
        (True,  True,  True,  True):  '┼',
    }
    return table[key]


def main():
    parser = argparse.ArgumentParser(description="Render Fibonacci tiles as ASCII art.")
    parser.add_argument("--start", type=int, default=1,
                        help="Starting Fibonacci position (default: 1, skipping F(0)=0)")
    parser.add_argument("--count", type=int, default=6,
                        help="Number of tiles to render (default: 6)")
    args = parser.parse_args()

    if args.count <= 0:
        print("Error: --count must be positive.", file=sys.stderr)
        sys.exit(1)
    if args.start < 0:
        print("Error: --start must be non-negative.", file=sys.stderr)
        sys.exit(1)

    values = get_fibonacci(args.start, args.count)
    output = render_tiles(values)
    print(output)


if __name__ == "__main__":
    main()
