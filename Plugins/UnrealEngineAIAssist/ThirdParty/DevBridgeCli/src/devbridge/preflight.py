"""Preflight: ensure `Log LogTemp verbose` + `Log Log verbose` are enabled so
that ExecDoString RetVal lines reach logcat, and grow the ring buffer so the
lines aren't rotated out by the game's noisy logging.

Idempotency: the enablement state is cached per-device in
``<plugin>/.claude/devbridge/cache/<device_id>.json`` with a TTL (default 24h).
``check()`` reports the cached status without mutating state.
``ensure()`` is the idempotent write path — it re-enables only if the cache is
stale, missing, or the canary probe fails.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from typing import Optional

from . import config, paths
from .adb import DeviceBridgeManager
from .lua_parse import parse_retval


@dataclass
class PreflightStatus:
    device_id: str
    enabled: bool                      # True if we believe the categories are on
    checked_at: Optional[str]          # ISO timestamp of last successful enable or canary
    canary_ok: Optional[bool]          # last canary probe result, None if never probed
    logcat_buffer: str                 # last observed buffer sizing (raw text from `logcat -g`)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Cache file format (per device):                                             #
#   {                                                                         #
#     "enabled": bool,                                                        #
#     "enabled_at": iso_timestamp,                                            #
#     "canary_ok": bool,                                                      #
#     "canary_at": iso_timestamp,                                             #
#     "logcat_buffer": "ring buffer is 16Mb ..."                              #
#   }                                                                         #
# --------------------------------------------------------------------------- #

def _cache_file(device_id: str):
    safe = device_id.replace("/", "_").replace(":", "_")
    return paths.cache_dir() / f"{safe}.json"


def _load_cache(device_id: str) -> dict:
    p = _cache_file(device_id)
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(device_id: str, data: dict) -> None:
    p = _cache_file(device_id)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _is_fresh(iso_ts: str, ttl_hours: float) -> bool:
    if not iso_ts:
        return False
    try:
        t = time.mktime(time.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return False
    return (time.time() - t) < ttl_hours * 3600


def _run_canary(mgr: DeviceBridgeManager, device_id: str,
                wait_seconds: float = 2.0, timeout: float = 10.0) -> bool:
    """Clear logcat, broadcast `ExecDoString return 1+1`, grep for RetVal."""
    mgr.adb.logcat_clear(device_id)
    mgr.exec_unlua("return 1+1", device_id=device_id)
    time.sleep(wait_seconds)

    deadline = time.time() + timeout
    while time.time() < deadline:
        output, _ = mgr.adb.logcat(
            device_id, lines=500, filter_expr="-s UE4:V", timeout=5.0
        )
        result = parse_retval(output)
        if result.success and result.retval and result.retval.strip() == "2":
            return True
        time.sleep(0.5)
    return False


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #

def check(mgr: DeviceBridgeManager, device_id: str = "",
          run_canary: bool = False) -> PreflightStatus:
    """Report current preflight state without modifying the device.

    If ``run_canary`` is True, actively probe ExecDoString (this DOES clear
    logcat — semi-destructive). Default False — only returns cached info.
    """
    try:
        dev = mgr.resolve_device(device_id)
    except ValueError as e:
        return PreflightStatus(
            device_id=device_id or "",
            enabled=False,
            checked_at=None,
            canary_ok=None,
            logcat_buffer="",
            notes=str(e),
        )

    cache = _load_cache(dev)
    ttl = float(config.get("preflight_ttl_hours", 24))

    cached_enabled = bool(cache.get("enabled"))
    cached_ts = str(cache.get("enabled_at", ""))
    fresh = _is_fresh(cached_ts, ttl)

    canary_ok: Optional[bool] = cache.get("canary_ok")
    if run_canary:
        canary_ok = _run_canary(mgr, dev)
        cache["canary_ok"] = canary_ok
        cache["canary_at"] = _now_iso()
        _save_cache(dev, cache)

    buffer_text = cache.get("logcat_buffer", "") or mgr.adb.logcat_buffer_sizes(dev)

    enabled = cached_enabled and fresh
    return PreflightStatus(
        device_id=dev,
        enabled=enabled,
        checked_at=cached_ts or None,
        canary_ok=canary_ok,
        logcat_buffer=buffer_text,
        notes="cached" if enabled else ("stale" if cached_ts else "never enabled"),
    )


def ensure(mgr: DeviceBridgeManager, device_id: str = "",
           force: bool = False, buffer_size: str = "",
           run_canary: bool = True) -> PreflightStatus:
    """Idempotently enable Log/LogTemp categories and resize the logcat buffer.

    - If the cache says enabled and fresh, skip (unless ``force``).
    - Always re-send the `Log` commands if we're enabling (they're cheap).
    - Optionally run the canary afterwards to confirm (default on).
    """
    try:
        dev = mgr.resolve_device(device_id)
    except ValueError as e:
        return PreflightStatus(
            device_id=device_id or "",
            enabled=False,
            checked_at=None,
            canary_ok=None,
            logcat_buffer="",
            notes=str(e),
        )

    ttl = float(config.get("preflight_ttl_hours", 24))
    cache = _load_cache(dev)
    cached_ts = str(cache.get("enabled_at", ""))
    already_fresh = bool(cache.get("enabled")) and _is_fresh(cached_ts, ttl)

    buffer_size = buffer_size or config.get("logcat_buffer_target", "16M")

    if already_fresh and not force:
        # Still grab the buffer sizing + canary for reporting
        buffer_text = mgr.adb.logcat_buffer_sizes(dev)
        canary = _run_canary(mgr, dev) if run_canary else cache.get("canary_ok")
        cache["canary_ok"] = canary
        cache["canary_at"] = _now_iso()
        cache["logcat_buffer"] = buffer_text
        _save_cache(dev, cache)
        return PreflightStatus(
            device_id=dev,
            enabled=True,
            checked_at=cached_ts,
            canary_ok=canary,
            logcat_buffer=buffer_text,
            notes="already enabled (cached)",
        )

    # Enable categories
    mgr.exec_console("Log LogTemp verbose", device_id=dev, timeout=10.0)
    mgr.exec_console("Log Log verbose", device_id=dev, timeout=10.0)

    # Grow buffer
    mgr.adb.logcat_set_buffer(dev, buffer_size)
    buffer_text = mgr.adb.logcat_buffer_sizes(dev)

    canary: Optional[bool] = None
    if run_canary:
        canary = _run_canary(mgr, dev)

    now = _now_iso()
    cache = {
        "enabled": True,
        "enabled_at": now,
        "canary_ok": canary,
        "canary_at": now if canary is not None else cache.get("canary_at", ""),
        "logcat_buffer": buffer_text,
        "buffer_target": buffer_size,
    }
    _save_cache(dev, cache)

    return PreflightStatus(
        device_id=dev,
        enabled=True,
        checked_at=now,
        canary_ok=canary,
        logcat_buffer=buffer_text,
        notes="enabled" if not force else "enabled (forced)",
    )
