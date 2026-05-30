#!/usr/bin/env python3
"""Compare two pixels' shader execution to find the divergence point.

Usage:
    python pixel_compare.py <EID> <X1> <Y1> <X2> <Y2>

Example:
    python pixel_compare.py 5942 612 264 612 265

Output:
    - Pixel values for both pixels
    - First divergent instruction number and register values
    - Shader disassembly around the divergence
    - Relevant constants
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
            timeout=30,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return -1, "", str(e)


def parse_trace(text: str) -> list[dict]:
    """Parse debug trace TSV into list of {step, instr, var, value}."""
    lines = text.strip().splitlines()
    if not lines:
        return []
    rows = []
    for line in lines[1:]:  # skip header
        parts = line.split("\t")
        if len(parts) >= 7:
            rows.append({
                "step": int(parts[0]),
                "instr": int(parts[1]),
                "var": parts[4],
                "type": parts[5],
                "value": parts[6],
            })
    return rows


def find_divergence(trace_a: list[dict], trace_b: list[dict]) -> int | None:
    """Find the first instruction where traces diverge in output register values."""
    # Group by (instr, var) and compare values
    def key(row: dict) -> tuple:
        return (row["instr"], row["var"])

    map_a = {}
    for r in trace_a:
        k = key(r)
        map_a[k] = r["value"]

    for r in trace_b:
        k = key(r)
        if k in map_a and map_a[k] != r["value"]:
            # Found divergence - but skip initial registers (step 0)
            if r["step"] > 0:
                return r["instr"]
    return None


def main() -> None:
    if len(sys.argv) != 6:
        print("Usage: pixel_compare.py <EID> <X1> <Y1> <X2> <Y2>", file=sys.stderr)
        sys.exit(1)

    eid, x1, y1, x2, y2 = sys.argv[1:6]

    print(f"=== Comparing pixel ({x1},{y1}) vs ({x2},{y2}) at EID {eid} ===")
    print()

    # 1. Get pixel values
    print("--- Pixel Values ---")
    for x, y, label in [(x1, y1, "A"), (x2, y2, "B")]:
        code, out, err = rdc("pixel", x, y, eid, "--json")
        if code == 0:
            data = json.loads(out)
            mods = data.get("modifications", [{}])
            if mods:
                so = mods[0].get("shader_out", {})
                print(f"  Pixel {label} ({x},{y}): R={so.get('r', '?'):.6f}  G={so.get('g', '?'):.6f}  B={so.get('b', '?'):.6f}")
            else:
                print(f"  Pixel {label} ({x},{y}): no modifications")
        else:
            print(f"  Pixel {label} ({x},{y}): error - {err}")
    print()

    # 2. Get debug traces
    print("--- Debug Traces ---")
    traces = {}
    for x, y, label in [(x1, y1, "A"), (x2, y2, "B")]:
        code, out, err = rdc("debug", "pixel", eid, x, y, "--trace")
        if code == 0:
            traces[label] = parse_trace(out)
            print(f"  Pixel {label}: {len(traces[label])} trace steps")
        else:
            traces[label] = []
            print(f"  Pixel {label}: trace failed - {err}")
    print()

    # 3. Find divergence
    if traces.get("A") and traces.get("B"):
        div_instr = find_divergence(traces["A"], traces["B"])
        if div_instr is not None:
            print(f"--- First Divergence at Instruction {div_instr} ---")

            # Show trace values around divergence
            for label, trace in traces.items():
                relevant = [r for r in trace if abs(r["instr"] - div_instr) <= 2]
                print(f"  Pixel {label}:")
                for r in relevant:
                    print(f"    instr={r['instr']:>4}  {r['var']:>4} = {r['value']}")
            print()

            # 4. Show shader disassembly around divergence
            print(f"--- Shader Disasm (instructions {max(0,div_instr-5)} to {div_instr+5}) ---")
            code, out, _ = rdc("cat", f"/draws/{eid}/shader/ps/disasm")
            if code == 0:
                for line in out.splitlines():
                    line_stripped = line.strip()
                    # Match instruction numbers like "  127: add r0.z, ..."
                    if ":" in line_stripped:
                        try:
                            instr_num = int(line_stripped.split(":")[0].strip())
                            if abs(instr_num - div_instr) <= 5:
                                marker = " >>>" if instr_num == div_instr else "    "
                                print(f"{marker} {line.rstrip()}")
                        except ValueError:
                            pass
        else:
            print("--- No divergence found in traces ---")
    print()

    # 5. Show constants
    print("--- Shader Constants (cb3 material params) ---")
    code, out, _ = rdc("cat", f"/draws/{eid}/shader/ps/constants")
    if code == 0:
        # Extract just cb3 entries (material params) - they're the most relevant
        for line in out.splitlines():
            if "cb3" in line:
                print(f"  {line.strip()[:120]}")


if __name__ == "__main__":
    main()
