"""preflight command — enable Log/LogTemp verbose + grow logcat buffer."""

from __future__ import annotations

import click

from .. import output
from .. import preflight as pf
from ..transport import TCPProxyTransport
from ._shared import get_manager, is_json, resolve_device_or_fail, resolve_transport


@click.command(
    name="preflight",
    help="Enable Log/LogTemp verbose on the device + grow logcat buffer. Idempotent.",
)
@click.option("--check", "check_only", is_flag=True, default=False,
              help="Report cached status only; do not modify device state.")
@click.option("--force", is_flag=True, default=False,
              help="Re-enable even if cache is fresh.")
@click.option("--no-canary", is_flag=True, default=False,
              help="Skip the ExecDoString 'return 1+1' canary probe.")
@click.option("--buffer", "buffer_size", default="",
              help="Logcat ring buffer size (e.g. 16M). Default from config.")
@click.pass_context
def preflight(ctx: click.Context, check_only: bool, force: bool,
              no_canary: bool, buffer_size: str) -> None:

    # --- TCP transport path ---
    transport = resolve_transport(ctx)
    if isinstance(transport, TCPProxyTransport):
        _preflight_tcp(ctx, transport, check_only, force, no_canary)
        return

    # --- ADB path (original logic) ---
    mgr, _ = resolve_device_or_fail(ctx)

    if check_only:
        status = pf.check(mgr, run_canary=not no_canary)
    else:
        status = pf.ensure(mgr, force=force, buffer_size=buffer_size,
                           run_canary=not no_canary)

    data = status.to_dict()

    # Exit code: non-zero if canary explicitly failed
    exit_code = output.EXIT_OK
    if status.canary_ok is False:
        exit_code = output.EXIT_FAILED

    if is_json(ctx):
        output.emit(data, json_mode=True)
        if exit_code != output.EXIT_OK:
            raise SystemExit(exit_code)
        return

    lines = [
        f"device:        {status.device_id}",
        f"enabled:       {status.enabled}  ({status.notes})",
        f"checked_at:    {status.checked_at or '(never)'}",
        f"canary_ok:     {status.canary_ok if status.canary_ok is not None else '(skipped)'}",
        f"logcat buffer: {status.logcat_buffer.strip().splitlines()[0] if status.logcat_buffer else '(unknown)'}",
    ]
    output.emit(data, text="\n".join(lines))
    if exit_code != output.EXIT_OK:
        raise SystemExit(exit_code)


def _preflight_tcp(ctx: click.Context, transport: TCPProxyTransport,
                   check_only: bool, force: bool, no_canary: bool) -> None:
    """TCP-mode preflight: enable verbosity via exec_console, canary via exec_unlua."""

    if check_only:
        # In TCP mode, just run canary to verify
        if no_canary:
            data = {"success": True, "device_id": "(tcp)", "enabled": None,
                    "canary_ok": None, "notes": "check-only, no canary"}
            if is_json(ctx):
                output.emit(data, json_mode=True)
            else:
                output.emit(data, text="preflight (tcp): check-only, canary skipped")
            return
        # Run canary
        canary_ok = _tcp_canary(transport)
        data = {"success": True, "device_id": "(tcp)", "enabled": canary_ok,
                "canary_ok": canary_ok, "notes": "tcp canary probe"}
        if is_json(ctx):
            output.emit(data, json_mode=True)
        else:
            status_text = "OK" if canary_ok else "FAILED"
            output.emit(data, text=f"preflight (tcp): canary {status_text}")
        if not canary_ok:
            raise SystemExit(output.EXIT_FAILED)
        return

    # Enable log categories
    transport.send_command("exec_console", {"command": "Log LogTemp Verbose"})
    transport.send_command("exec_console", {"command": "Log Log Verbose"})

    # Run canary
    canary_ok = None
    if not no_canary:
        canary_ok = _tcp_canary(transport)

    data = {
        "success": True,
        "device_id": "(tcp)",
        "enabled": True,
        "canary_ok": canary_ok,
        "notes": "enabled via TCP" if not force else "enabled via TCP (forced)",
    }

    exit_code = output.EXIT_OK
    if canary_ok is False:
        exit_code = output.EXIT_FAILED

    if is_json(ctx):
        output.emit(data, json_mode=True)
    else:
        lines = [
            "device:        (tcp)",
            f"enabled:       True  ({data['notes']})",
            f"canary_ok:     {canary_ok if canary_ok is not None else '(skipped)'}",
        ]
        output.emit(data, text="\n".join(lines))

    if exit_code != output.EXIT_OK:
        raise SystemExit(exit_code)


def _tcp_canary(transport: TCPProxyTransport) -> bool:
    """Send 'return 1+1' via exec_unlua and check if retval is '2'."""
    resp = transport.send_command("exec_unlua", {"code": "return 1+1"})
    retval = resp.get("output", "").strip()
    return retval == "2"
