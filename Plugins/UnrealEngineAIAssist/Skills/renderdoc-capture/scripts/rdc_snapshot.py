#!/usr/bin/env python3
"""rdc session snapshot -- one-shot context for AI agents.

Outputs a single JSON object with current rdc session state:
  session_active, status, info, stats, passes

Usage:
    python rdc_snapshot.py
"""

from __future__ import annotations

import json
import subprocess
import sys


def rdc(*args: str) -> tuple[int, str, str]:
    """Run an rdc command and return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(
            ["rdc", *args],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return -1, "", "rdc not found on PATH"
    except subprocess.TimeoutExpired:
        return -2, "", "timeout"


def main() -> None:
    snapshot: dict = {"session_active": False}

    # Check if rdc is installed
    code, out, err = rdc("--version")
    if code != 0:
        snapshot["error"] = "rdc-cli not installed"
        snapshot["fix"] = "cd <plugin>/rdc-cli && uv tool install ."
        json.dump(snapshot, sys.stdout, indent=2)
        return

    snapshot["rdc_version"] = out

    # Check session status (rdc status outputs key: value text, not JSON)
    code, out, err = rdc("status")
    if code != 0:
        # No active session
        json.dump(snapshot, sys.stdout, indent=2)
        return

    # Parse "key: value" lines
    status = {}
    for line in out.splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            status[k.strip()] = v.strip()
    snapshot["status"] = status
    snapshot["session_active"] = True

    # Gather context in one shot
    for cmd, key in [("info", "info"), ("stats", "stats"), ("passes", "passes")]:
        code, out, _ = rdc(cmd, "--json")
        if code == 0:
            try:
                snapshot[key] = json.loads(out)
            except json.JSONDecodeError:
                snapshot[key + "_raw"] = out

    json.dump(snapshot, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
