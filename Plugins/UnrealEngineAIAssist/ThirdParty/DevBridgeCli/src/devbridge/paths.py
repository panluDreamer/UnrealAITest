"""Filesystem path discovery and directory management for devbridge.

Locates the UnrealEngineAIAssist plugin root by walking up from CWD (or from an
environment override), then provides lazily-created subdirectories under
`<plugin>/.claude/devbridge/`.

Env overrides:
    DEVBRIDGE_PLUGIN_DIR   Force the plugin root (skips auto-discovery)
    DEVBRIDGE_AGENT_DIR    Agent dir name under the plugin (default: ".claude")
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


# Marker files that together uniquely identify the UnrealEngineAIAssist plugin root.
# We require ALL markers to avoid false matches on unrelated ancestor directories.
_PLUGIN_MARKERS = (
    "UnrealEngineAIAssist.uplugin",
    "Source/UnrealEngineAIAssist",
)


def _is_plugin_root(path: Path) -> bool:
    return all((path / m).exists() for m in _PLUGIN_MARKERS)


@lru_cache(maxsize=1)
def plugin_root() -> Path:
    """Return the UnrealEngineAIAssist plugin root directory.

    Resolution order:
      1. $DEVBRIDGE_PLUGIN_DIR if set and valid.
      2. Walk up from the current working directory looking for plugin markers.
      3. Walk up from this module's install location (fallback when cwd is elsewhere).
      4. Raise RuntimeError if none found.
    """
    env = os.environ.get("DEVBRIDGE_PLUGIN_DIR", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if _is_plugin_root(p):
            return p
        raise RuntimeError(
            f"DEVBRIDGE_PLUGIN_DIR={env} is set but does not point to a valid plugin root "
            f"(missing {_PLUGIN_MARKERS})."
        )

    for start in (Path.cwd().resolve(), Path(__file__).resolve()):
        for candidate in (start, *start.parents):
            if _is_plugin_root(candidate):
                return candidate

    raise RuntimeError(
        "Could not locate UnrealEngineAIAssist plugin root. "
        "Run devbridge from somewhere inside the plugin, or set DEVBRIDGE_PLUGIN_DIR."
    )


def agent_dir_name() -> str:
    return os.environ.get("DEVBRIDGE_AGENT_DIR", ".claude").strip() or ".claude"


def devbridge_dir() -> Path:
    """Root of devbridge's persistent state: <plugin>/.claude/devbridge/."""
    p = plugin_root() / agent_dir_name() / "devbridge"
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    return devbridge_dir() / "config.json"


def cache_dir() -> Path:
    p = devbridge_dir() / "cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def history_dir() -> Path:
    p = devbridge_dir() / "history"
    p.mkdir(parents=True, exist_ok=True)
    return p


def history_index_path() -> Path:
    return history_dir() / "index.json"


def logs_dir() -> Path:
    p = devbridge_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p
