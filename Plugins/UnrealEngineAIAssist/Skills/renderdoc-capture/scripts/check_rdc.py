#!/usr/bin/env python3
"""
Quick health check for rdc-cli setup.

Usage:
    python check_rdc.py          # Full check
    python check_rdc.py --quick  # Just check if rdc is installed
"""

import subprocess
import sys


def run(cmd, timeout=10):
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -2, "", f"Timeout after {timeout}s"


def check(quick=False):
    ok = True

    # 1. Check rdc-cli installed
    code, out, err = run(["rdc", "--version"])
    if code == 0:
        print(f"  rdc-cli: OK ({out})")
    elif code == -1:
        print("  rdc-cli: NOT INSTALLED")
        print("    Fix: cd <plugin_dir>/ThirdParty/RdcCli && uv tool install .")
        return False
    else:
        print(f"  rdc-cli: ERROR ({err})")
        return False

    if quick:
        return ok

    # 2. Check renderdoc module via doctor
    print("  Running rdc doctor...")
    code, out, err = run(["rdc", "doctor"], timeout=15)
    if code == 0:
        print(f"  renderdoc module: OK")
        # Print doctor output indented
        for line in out.splitlines():
            print(f"    {line}")
    else:
        print(f"  renderdoc module: ISSUE")
        for line in (out + "\n" + err).strip().splitlines():
            print(f"    {line}")
        print("    Fix: uv tool install . --force (from rdc-cli directory)")
        print("    Bundled renderdoc should be included. Check Python version is 3.12.")
        ok = False

    return ok


def main():
    quick = "--quick" in sys.argv

    print("rdc-cli Setup Check")
    print("=" * 40)
    ok = check(quick=quick)
    print("=" * 40)
    if ok:
        print("All checks passed.")
    else:
        print("Some checks failed. See above for fixes.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
