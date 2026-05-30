#!/usr/bin/env python3
"""Search draw calls by keyword(s).

Usage:
    python draw_search.py <keyword1> [keyword2] ...

Example:
    python draw_search.py PostProcess Outline
    python draw_search.py Shadow

Output:
    Matching draw calls with EID, name, triangle count.
"""

from __future__ import annotations

import json
import subprocess
import sys


def rdc(*args: str) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            ["rdc", *args],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return -1, "", str(e)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: draw_search.py <keyword1> [keyword2] ...", file=sys.stderr)
        sys.exit(1)

    keywords = [k.lower() for k in sys.argv[1:]]

    code, out, err = rdc("draws", "--json")
    if code != 0:
        print(f"error: {err}", file=sys.stderr)
        sys.exit(1)

    try:
        draws = json.loads(out)
    except json.JSONDecodeError:
        print("error: failed to parse draws JSON", file=sys.stderr)
        sys.exit(1)

    print(f"Searching {len(draws)} draws for: {', '.join(keywords)}")
    print()
    print("EID\tTRIANGLES\tINSTANCES\tNAME")

    matches = 0
    for d in draws:
        name = d.get("name", d.get("marker", ""))
        name_lower = name.lower()
        if any(kw in name_lower for kw in keywords):
            eid = d.get("eid", "?")
            tris = d.get("num_indices", d.get("triangles", 0))
            instances = d.get("num_instances", d.get("instances", 1))
            print(f"{eid}\t{tris}\t{instances}\t{name}")
            matches += 1

    print(f"\n{matches} matches found.")


if __name__ == "__main__":
    main()
