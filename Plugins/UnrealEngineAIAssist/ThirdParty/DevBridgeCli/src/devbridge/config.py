"""Configuration read/write for devbridge.

Config lives at <plugin>/.claude/devbridge/config.json. Stores user preferences:
default device, game package name, logcat buffer target size, lua wait/timeout.
"""

from __future__ import annotations

import json
from typing import Any

from . import paths

# Defaults
DEFAULTS: dict[str, Any] = {
    "default_device": "",
    "package_name": "com.yourcompany.yourgame",
    "logcat_buffer_target": "16M",
    "lua_default_wait_seconds": 2.0,
    "lua_default_timeout_seconds": 10.0,
    "preflight_ttl_hours": 24,
}


def load() -> dict[str, Any]:
    """Load config from disk, falling back to defaults for missing keys."""
    path = paths.config_path()
    if not path.exists():
        return dict(DEFAULTS)
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return dict(DEFAULTS)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    merged.update(data)
    return merged


def save(cfg: dict[str, Any]) -> None:
    """Write config, preserving only known keys."""
    path = paths.config_path()
    # Only keep known keys to avoid schema drift
    out = {k: cfg.get(k, DEFAULTS[k]) for k in DEFAULTS}
    with path.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")


def get(key: str, default: Any = None) -> Any:
    cfg = load()
    return cfg.get(key, default if default is not None else DEFAULTS.get(key))


def set_key(key: str, value: Any) -> None:
    cfg = load()
    cfg[key] = value
    save(cfg)
