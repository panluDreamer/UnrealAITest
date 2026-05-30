#!/usr/bin/env python3
"""Scan a horizontal or vertical line of pixels to find color/depth transitions.

Usage:
    python edge_scan.py <EID> x=<VALUE> <START_Y> <END_Y>   # vertical scan (fixed x)
    python edge_scan.py <EID> y=<VALUE> <START_X> <END_X>   # horizontal scan (fixed y)

Example:
    python edge_scan.py 5942 x=611 318 328
    python edge_scan.py 1210 y=260 440 560

Output:
    TSV with columns: coord, R, G, B, delta (color change from previous pixel)
    Marks transitions with *** where delta exceeds threshold.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys


def rdc(*args: str) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            ["rdc", *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return -1, "", str(e)


def get_pixel(eid: str, x: int, y: int) -> tuple[float, float, float] | None:
    """Get pixel shader output RGB at (x, y) for event eid."""
    code, out, _ = rdc("pixel", str(x), str(y), eid, "--json")
    if code != 0:
        return None
    try:
        data = json.loads(out)
        mods = data.get("modifications", [])
        if not mods:
            return None
        so = mods[0].get("shader_out", mods[0].get("post_mod", {}))
        return (so.get("r", 0.0), so.get("g", 0.0), so.get("b", 0.0))
    except (json.JSONDecodeError, KeyError, IndexError):
        return None


def color_delta(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Euclidean distance between two RGB colors."""
    return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))


def main() -> None:
    if len(sys.argv) != 5:
        print("Usage: edge_scan.py <EID> <x=N|y=N> <START> <END>", file=sys.stderr)
        print("  e.g.: edge_scan.py 5942 x=611 318 328", file=sys.stderr)
        sys.exit(1)

    eid = sys.argv[1]
    axis_spec = sys.argv[2]  # "x=611" or "y=260"
    start = int(sys.argv[3])
    end = int(sys.argv[4])

    if "=" not in axis_spec:
        print("error: axis must be x=<value> or y=<value>", file=sys.stderr)
        sys.exit(1)

    axis, value = axis_spec.split("=", 1)
    value = int(value)
    axis = axis.lower()

    if axis not in ("x", "y"):
        print("error: axis must be 'x' or 'y'", file=sys.stderr)
        sys.exit(1)

    threshold = 0.1  # color delta threshold for marking transitions

    print(f"Scanning {'vertically' if axis == 'x' else 'horizontally'} "
          f"at {axis}={value}, range {start}-{end}, EID={eid}")
    print()
    print("COORD\tR\tG\tB\tDELTA\tTRANSITION")

    prev_color = None
    for i in range(start, end + 1):
        x = value if axis == "x" else i
        y = i if axis == "x" else value

        color = get_pixel(eid, x, y)
        if color is None:
            print(f"{i}\t-\t-\t-\t-\t(no data)")
            prev_color = None
            continue

        delta = color_delta(color, prev_color) if prev_color else 0.0
        marker = "***" if delta > threshold and prev_color is not None else ""

        print(f"{i}\t{color[0]:.4f}\t{color[1]:.4f}\t{color[2]:.4f}\t{delta:.4f}\t{marker}")
        prev_color = color


if __name__ == "__main__":
    main()
