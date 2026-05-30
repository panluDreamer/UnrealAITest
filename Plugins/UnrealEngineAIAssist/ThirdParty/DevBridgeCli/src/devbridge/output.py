"""Output formatting helpers.

All devbridge commands should route human/JSON output through ``emit`` and errors
through ``fail`` so that ``--json`` / ``--quiet`` behave uniformly and exit
codes are consistent.

Exit codes:
    0   OK
    1   command failed (logical error, e.g. Lua xpcall failure)
    2   device / ADB error (no device, unauthorized, broadcast refused)
    3   config error (malformed config, can't find plugin root)
"""

from __future__ import annotations

import json
import sys
from typing import Any

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_DEVICE = 2
EXIT_CONFIG = 3


def emit(
    data: Any,
    json_mode: bool = False,
    quiet: bool = False,
    text: str | None = None,
) -> None:
    """Emit a result.

    - json_mode=True: dump ``data`` as pretty JSON to stdout.
    - quiet=True: only a minimal single-line representation is printed.
    - otherwise: use ``text`` if provided, else fall back to JSON.
    """
    if json_mode:
        json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return

    if quiet:
        # Prefer a specific "quiet_text" field, else a single line summary
        if isinstance(data, dict) and "quiet_text" in data:
            sys.stdout.write(str(data["quiet_text"]) + "\n")
        elif isinstance(data, (str, int, float, bool)):
            sys.stdout.write(str(data) + "\n")
        else:
            # Compact JSON fallback so scripts still get parseable output
            sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
        return

    if text is not None:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
        return

    # No custom text — use pretty JSON by default
    json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def fail(message: str, exit_code: int = EXIT_FAILED, json_mode: bool = False) -> None:
    """Emit an error message and exit with the given code."""
    if json_mode:
        json.dump({"success": False, "error": message}, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        sys.stderr.write(f"devbridge: {message}\n")
    sys.exit(exit_code)


def warn(message: str) -> None:
    """Emit a warning to stderr without exiting."""
    sys.stderr.write(f"devbridge: warning: {message}\n")
