"""snapshot command — aggregate 7 independent probes into one JSON payload.

Purpose (vs rdc's snapshot): rdc uses snapshot to avoid re-opening captures;
devbridge uses it to collapse 5-6 independent ADB round-trips an AI would
otherwise run serially when entering the device-bridge skill.

Fields:
    version, adb_ok, adb_path, devices, default_device,
    game: {package, pid, running},
    preflight: {enabled, checked_at, canary_ok, logcat_buffer},
    history_tail: [...]
"""

from __future__ import annotations

import click

from .. import __version__, config, history as hist, output
from .. import preflight as pf
from ..transport import auto_resolve, _read_serve_session
from ._shared import get_manager, is_json


@click.command(name="snapshot", help="One-shot JSON of device + game + preflight + recent history.")
@click.option("--tail", type=int, default=10, help="Number of recent history entries to include.")
@click.option("--canary/--no-canary", default=False,
              help="Probe ExecDoString `return 1+1` as part of preflight check (default off — it clears logcat).")
@click.pass_context
def snapshot(ctx: click.Context, tail: int, canary: bool) -> None:
    mgr = get_manager(ctx)

    adb_version = mgr.adb.version()
    adb_ok = bool(adb_version)

    devices_list = mgr.list_devices()
    devices = [
        {"id": d.device_id, "state": d.state, "model": d.model, "ready": d.is_ready}
        for d in devices_list
    ]

    # Try to resolve a default device for the richer probes
    try:
        default_dev = mgr.resolve_device(ctx.obj.get("device", ""))
    except ValueError:
        default_dev = ""

    # Game state
    pkg = config.get("package_name", "com.yourcompany.yourgame")
    game: dict = {"package": pkg, "pid": None, "running": False}
    preflight_data: dict = {"enabled": None, "checked_at": None, "canary_ok": None, "logcat_buffer": ""}

    if default_dev:
        pid = mgr.adb.pidof(default_dev, pkg)
        game = {"package": pkg, "pid": pid, "running": bool(pid)}
        status = pf.check(mgr, device_id=default_dev, run_canary=canary)
        preflight_data = {
            "enabled": status.enabled,
            "checked_at": status.checked_at,
            "canary_ok": status.canary_ok,
            "logcat_buffer": status.logcat_buffer.strip(),
            "notes": status.notes,
        }

    # Serve status
    serve_session = _read_serve_session()
    serve_data = {
        "running": serve_session is not None,
        "ipc_port": serve_session.get("ipc_port") if serve_session else None,
        "device_connected": serve_session.get("device_connected", False) if serve_session else False,
        "device_label": serve_session.get("device_label", "") if serve_session else "",
    }

    # Auto-resolve transport
    transport = auto_resolve(ctx, explicit_device=ctx.obj.get("device", ""))
    transport_info = {"name": transport.name, "label": transport.label()}

    data = {
        "devbridge_version": __version__,
        "adb_ok": adb_ok,
        "adb_path": mgr.adb.adb_path,
        "adb_version": adb_version,
        "devices": devices,
        "default_device": default_dev,
        "configured_default": config.get("default_device", ""),
        "game": game,
        "preflight": preflight_data,
        "serve": serve_data,
        "transport": transport_info,
        "history_tail": hist.read_tail(tail),
    }

    if is_json(ctx):
        output.emit(data, json_mode=True)
        return

    # Human-readable summary
    lines = [
        f"devbridge v{__version__}",
        f"adb:            {data['adb_path']}  ({data['adb_version'] or 'UNAVAILABLE'})",
        f"devices:        {len(devices)} connected",
    ]
    for d in devices:
        lines.append(f"  - {d['id']} ({d['state']}, {d['model']})")
    lines.append(f"default:        {default_dev or '(none)'}")
    lines.append(f"game:           {pkg}  pid={game['pid']}  running={game['running']}")
    lines.append(f"preflight:      enabled={preflight_data['enabled']}  canary={preflight_data['canary_ok']}")
    lines.append(f"serve:          running={serve_data['running']}  device={serve_data['device_label'] or '(none)'}")
    lines.append(f"transport:      {transport_info['label']}")
    lines.append(f"history_tail:   {len(data['history_tail'])} entries (pass --json to see)")
    output.emit(data, text="\n".join(lines))
