"""Parse ExecDoString RetVal lines out of raw logcat output.

The `ExecDoString` UFUNCTION logs under LogTemp with the format:

    [<unreal-timestamp>]LogTemp: [PlatformGameInstance]ExecDoString RetVal:<value>

This module extracts the most recent RetVal line from a logcat dump and
reports the value verbatim. It also detects the common error signature
(`ChunkDoString xpcall error`) so the CLI can surface a meaningful error
instead of a success-with-empty-retval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


_RETVAL_RE = re.compile(r"ExecDoString RetVal:(.*)$")
_ERROR_TAG_RE = re.compile(r"ChunkDoString xpcall error")
_ERROR_DETAIL_RE = re.compile(r'\[string "ChunkDoString"\]:\d+:\s*(.*)$')


@dataclass
class LuaResult:
    success: bool
    retval: Optional[str]           # the value after "RetVal:" verbatim (may be "Error:[Error]")
    raw_line: Optional[str]         # the full logcat line we matched
    error: Optional[str]            # extracted error detail if xpcall failure detected
    all_retvals: list[str]          # all RetVal lines seen (last one wins for `retval`)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "retval": self.retval,
            "raw_line": self.raw_line,
            "error": self.error,
            "retval_count": len(self.all_retvals),
        }


def parse_retval(logcat_text: str) -> LuaResult:
    """Scan a logcat dump for the most recent ExecDoString RetVal line.

    Semantics:
      - Returns ``success=True, retval=<value>`` for a normal return
        (including the string "nil" or an empty string).
      - Returns ``success=False, retval="Error:[Error]", error=<detail>`` if the
        RetVal itself indicates a Lua xpcall error (the game logs errors as RetVal too).
      - Returns ``success=False, retval=None, error="<no retval seen>"`` when
        no RetVal line is present in the buffer.

    Deduplicates adjacent identical lines (UE4 often logs the same line twice).
    """
    retvals: list[tuple[str, str]] = []  # (full_line, value)
    error_detail: Optional[str] = None
    last_line = ""

    for line in logcat_text.splitlines():
        if line == last_line:
            continue  # skip adjacent duplicates
        last_line = line

        m = _RETVAL_RE.search(line)
        if m:
            retvals.append((line.strip(), m.group(1).strip()))
            continue

        # Capture an error detail line if we see one (appears on the line after
        # the xpcall error marker)
        if _ERROR_TAG_RE.search(line):
            error_detail = "ChunkDoString xpcall error"
            continue

        m2 = _ERROR_DETAIL_RE.search(line)
        if m2 and error_detail is not None:
            # Promote to the concrete detail once available
            error_detail = m2.group(1).strip() or error_detail

    if not retvals:
        return LuaResult(
            success=False,
            retval=None,
            raw_line=None,
            error="No ExecDoString RetVal line found in logcat. Category suppressed (run `devbridge preflight`)? Game not running? Wait longer?",
            all_retvals=[],
        )

    raw_line, value = retvals[-1]
    all_values = [v for _, v in retvals]

    # The game logs errors as a RetVal starting with "Error:"
    if value.startswith("Error:"):
        return LuaResult(
            success=False,
            retval=value,
            raw_line=raw_line,
            error=error_detail or value,
            all_retvals=all_values,
        )

    return LuaResult(
        success=True,
        retval=value,
        raw_line=raw_line,
        error=None,
        all_retvals=all_values,
    )
