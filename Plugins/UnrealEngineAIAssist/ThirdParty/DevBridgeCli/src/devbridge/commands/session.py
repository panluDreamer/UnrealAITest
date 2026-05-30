"""Session / device-discovery commands: doctor, devices, use, info."""

from __future__ import annotations

import click

from .. import config, output
from ._shared import get_manager, is_json, is_quiet, resolve_device_or_fail


@click.command(name="doctor", help="Check devbridge environment (adb, devices, game, preflight).")
@click.pass_context
def doctor(ctx: click.Context) -> None:
    mgr = get_manager(ctx)
    report = {
        "adb_path": mgr.adb.adb_path,
        "adb_version": mgr.adb.version() or "(failed)",
        "devices": [{"id": d.device_id, "state": d.state, "model": d.model} for d in mgr.list_devices()],
        "default_device": config.get("default_device", ""),
        "package_name": config.get("package_name"),
    }

    if is_json(ctx):
        output.emit(report, json_mode=True)
        return

    lines = [
        f"adb:        {report['adb_path']}",
        f"version:    {report['adb_version']}",
        f"default:    {report['default_device'] or '(auto)'}",
        f"package:    {report['package_name']}",
        "",
        "Devices:",
    ]
    if not report["devices"]:
        lines.append("  (none connected — run `adb devices` to verify USB + debugging)")
    for d in report["devices"]:
        lines.append(f"  {d['id']:16s}  {d['state']:14s}  {d['model']}")
    output.emit(report, text="\n".join(lines))


@click.command(name="devices", help="List connected Android devices.")
@click.pass_context
def devices(ctx: click.Context) -> None:
    mgr = get_manager(ctx)
    devs = mgr.list_devices()
    data = [{"id": d.device_id, "state": d.state, "model": d.model,
             "product": d.product, "transport_id": d.transport_id,
             "ready": d.is_ready} for d in devs]

    if is_json(ctx):
        output.emit(data, json_mode=True)
        return

    if is_quiet(ctx):
        for d in data:
            output.emit({"quiet_text": d["id"]}, quiet=True)
        return

    if not data:
        output.emit(data, text="(no devices connected)")
        return

    rows = ["DEVICE_ID\tSTATE\tMODEL\tREADY"]
    for d in data:
        rows.append(f"{d['id']}\t{d['state']}\t{d['model']}\t{d['ready']}")
    output.emit(data, text="\n".join(rows))


@click.command(name="use", help="Set default device (persisted to config).")
@click.argument("device_id")
@click.pass_context
def use(ctx: click.Context, device_id: str) -> None:
    mgr = get_manager(ctx)
    # Validate device exists (but allow setting even if offline — user may reconnect)
    devs = mgr.list_devices()
    exists = any(d.device_id == device_id for d in devs)
    config.set_key("default_device", device_id)
    msg = {
        "default_device": device_id,
        "verified_connected": exists,
    }
    if is_json(ctx):
        output.emit(msg, json_mode=True)
    else:
        note = "" if exists else " (warning: not currently connected)"
        output.emit(msg, text=f"default_device = {device_id}{note}")


@click.command(name="info", help="Show device details (model, OS, GPU, resolution).")
@click.pass_context
def info(ctx: click.Context) -> None:
    mgr, dev = resolve_device_or_fail(ctx)
    data = mgr.device_info(device_id=dev)

    if not data.get("success"):
        output.fail(data.get("error", "device_info failed"),
                    exit_code=output.EXIT_DEVICE, json_mode=is_json(ctx))
        return

    if is_json(ctx):
        output.emit(data, json_mode=True)
        return

    lines = [
        f"device:     {data['device_id']}",
        f"model:      {data.get('manufacturer', '')} {data.get('model', '')}".strip(),
        f"android:    {data.get('android_version', '')} (sdk {data.get('sdk_version', '')})",
        f"abi:        {data.get('cpu_abi', '')}",
        f"screen:     {data.get('screen_resolution', '')}  density={data.get('screen_density', '')}",
        f"gpu:        {data.get('gpu_renderer', '')}",
    ]
    output.emit(data, text="\n".join(lines))
