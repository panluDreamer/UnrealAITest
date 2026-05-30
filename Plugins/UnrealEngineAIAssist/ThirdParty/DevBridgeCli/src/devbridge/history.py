"""Persistent execution history for devbridge.

Mirrors the pattern from ``ue-python-script``'s MCP server
(``_save_script_history`` / ``_slugify`` in ``unreal_agent_bridge_mcp.py``)
so Claude Code can grep/replay past executions across sessions.

Layout (under <plugin>/.claude/devbridge/history/):

    index.json                       # FIFO-200 array of IndexEntry
    {id}.lua | {id}.cmd | {id}.cvar  # the payload itself, with a header comment
    {id}.meta.json                   # retval, broadcast_output, logcat_excerpt_path

Large logcat excerpts go to ../logs/logcat_{id}.txt (not inlined in meta.json).

IDs are timestamp-based (``YYYYMMDD_HHMMSS_<slug>``) — naturally sortable,
collision-free across concurrent invocations thanks to the second-granularity
timestamp plus slug differentiator.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import paths

MAX_INDEX_ENTRIES = 200
LOGCAT_EXCERPT_INLINE_LIMIT = 2000   # chars; above this, dump to ../logs/ and store path only

# Mode → file extension for the payload file
_MODE_EXT = {
    "lua": "lua",
    "cmd": "cmd",
    "cvar": "cvar",
    "lua_file": "lua",
}


def _slugify(text: str, max_len: int = 50) -> str:
    """Turn an arbitrary summary string into a filename slug.

    Matches the MCP server's ``_slugify`` so history entries created by either
    tool follow the same shape.
    """
    slug = re.sub(r"[^a-zA-Z0-9_\- ]+", "", text).strip().replace(" ", "_")
    return slug[:max_len] if slug else "entry"


def _now() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%d_%H%M%S"), now.isoformat()


def _summary_from(code: str, fallback: str = "") -> str:
    """Derive a one-line summary from code when the caller didn't provide one."""
    for line in code.splitlines():
        s = line.strip()
        if s and not s.startswith("--") and not s.startswith("#"):
            return s[:80]
    return fallback or code.strip()[:80]


def _ensure_unique_id(base_id: str) -> str:
    """Disambiguate if two commands land on the same second."""
    d = paths.history_dir()
    # Check both the payload extensions and the meta file for any collision
    candidates = list(d.glob(f"{base_id}.*"))
    if not candidates:
        return base_id
    # Append a counter _2, _3, ...
    for i in range(2, 100):
        alt = f"{base_id}_{i}"
        if not list(d.glob(f"{alt}.*")):
            return alt
    # Extremely unlikely
    return f"{base_id}_{int(time.time()*1000)%1000}"


@dataclass
class IndexEntry:
    id: str
    device: str
    mode: str           # "lua" | "cmd" | "cvar" | "lua_file"
    summary: str
    timestamp: str      # ISO
    success: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _read_index() -> list[dict]:
    p = paths.history_index_path()
    if not p.exists():
        return []
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _write_index(entries: list[dict]) -> None:
    p = paths.history_index_path()
    # FIFO prune
    if len(entries) > MAX_INDEX_ENTRIES:
        entries = entries[-MAX_INDEX_ENTRIES:]
    with p.open("w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
        f.write("\n")


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #

def record(
    mode: str,
    code: str,
    device_id: str,
    summary: str = "",
    success: bool = True,
    retval: Any = None,
    error: str = "",
    broadcast_output: str = "",
    logcat_excerpt: str = "",
    extra_meta: Optional[dict] = None,
) -> IndexEntry:
    """Persist one execution to history. Returns the IndexEntry."""
    effective_summary = (summary or "").strip() or _summary_from(code)
    ts_file, ts_iso = _now()
    slug = _slugify(effective_summary)
    entry_id = _ensure_unique_id(f"{ts_file}_{slug}")

    ext = _MODE_EXT.get(mode, "txt")
    payload_path = paths.history_dir() / f"{entry_id}.{ext}"

    # Header comment on the payload file — syntax varies by mode
    comment_prefix = "--" if ext == "lua" else "#"
    header = "\n".join([
        f"{comment_prefix} devbridge history entry",
        f"{comment_prefix} id={entry_id}",
        f"{comment_prefix} device={device_id}",
        f"{comment_prefix} mode={mode}",
        f"{comment_prefix} timestamp={ts_iso}",
        f"{comment_prefix} summary={effective_summary}",
        f"{comment_prefix} success={success}",
    ])
    if retval is not None:
        header += f"\n{comment_prefix} retval={str(retval).replace(chr(10), ' | ')[:200]}"
    if error:
        header += f"\n{comment_prefix} error={error.replace(chr(10), ' | ')[:200]}"
    header += f"\n{comment_prefix} ---\n"

    with payload_path.open("w", encoding="utf-8") as f:
        f.write(header)
        f.write(code)
        if not code.endswith("\n"):
            f.write("\n")

    # Meta JSON
    meta: dict = {
        "id": entry_id,
        "device": device_id,
        "mode": mode,
        "summary": effective_summary,
        "timestamp": ts_iso,
        "success": success,
        "retval": retval,
        "error": error,
        "broadcast_output": broadcast_output,
    }
    if extra_meta:
        meta.update(extra_meta)

    # Logcat excerpt: inline if small, dump to file if large
    if logcat_excerpt:
        if len(logcat_excerpt) <= LOGCAT_EXCERPT_INLINE_LIMIT:
            meta["logcat_excerpt"] = logcat_excerpt
        else:
            excerpt_path = paths.logs_dir() / f"logcat_{entry_id}.txt"
            with excerpt_path.open("w", encoding="utf-8") as f:
                f.write(logcat_excerpt)
            meta["logcat_excerpt_path"] = str(excerpt_path)
            meta["logcat_excerpt_chars"] = len(logcat_excerpt)

    meta_path = paths.history_dir() / f"{entry_id}.meta.json"
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Index update
    index = _read_index()
    entry = IndexEntry(
        id=entry_id,
        device=device_id,
        mode=mode,
        summary=effective_summary,
        timestamp=ts_iso,
        success=success,
    )
    index.append(entry.to_dict())
    _write_index(index)

    return entry


def list_entries(
    tail: int = 20,
    grep: Optional[str] = None,
    device: Optional[str] = None,
    mode: Optional[str] = None,
    success_only: bool = False,
) -> list[dict]:
    """List history entries, most-recent-last (same order as index)."""
    index = _read_index()

    def keep(e: dict) -> bool:
        if device and e.get("device") != device:
            return False
        if mode and e.get("mode") != mode:
            return False
        if success_only and not e.get("success"):
            return False
        if grep:
            needle = grep.lower()
            hay = " ".join([
                str(e.get("id", "")),
                str(e.get("summary", "")),
                str(e.get("mode", "")),
            ]).lower()
            if needle not in hay:
                return False
        return True

    filtered = [e for e in index if keep(e)]
    if tail > 0:
        filtered = filtered[-tail:]
    return filtered


def read_tail(n: int = 10) -> list[dict]:
    """Shortcut for the snapshot command."""
    return list_entries(tail=n)


def show(entry_id: str) -> tuple[Optional[str], Optional[dict], Optional[Path]]:
    """Return (payload_code, meta_dict, payload_path). All None if not found."""
    d = paths.history_dir()

    meta_path = d / f"{entry_id}.meta.json"
    meta: Optional[dict] = None
    if meta_path.exists():
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                meta = json.load(f)
        except (json.JSONDecodeError, OSError):
            meta = None

    # Payload: find the single matching file regardless of ext
    payload_path: Optional[Path] = None
    for candidate in d.glob(f"{entry_id}.*"):
        if candidate.suffix == ".json":
            continue
        payload_path = candidate
        break

    code: Optional[str] = None
    if payload_path and payload_path.exists():
        try:
            with payload_path.open("r", encoding="utf-8") as f:
                text = f.read()
            # Strip header comment block
            lines = text.splitlines()
            start = 0
            for i, line in enumerate(lines):
                s = line.strip()
                if s in ("-- ---", "# ---"):
                    start = i + 1
                    break
            code = "\n".join(lines[start:]).lstrip("\n")
        except OSError:
            code = None

    return code, meta, payload_path


def find_by_prefix(prefix: str) -> Optional[str]:
    """Given a partial id (e.g. "20260421_104500"), return the full id if unambiguous."""
    index = _read_index()
    matches = [e["id"] for e in index if e.get("id", "").startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    return None
