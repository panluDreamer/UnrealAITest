"""Shared helpers for devbridge command modules.

Kept in a separate module (with leading underscore) to avoid polluting the
command namespace while giving subcommands a single place to do:

  - click context unpacking
  - device resolution with user-friendly failure messages
  - DeviceBridgeManager instantiation
  - transport auto-resolution (serve TCP > ADB > editor)
"""

from __future__ import annotations

import click

from .. import config, output
from ..adb import DeviceBridgeManager
from ..transport import Transport, auto_resolve


def get_manager(ctx: click.Context, output_dir: str = "") -> DeviceBridgeManager:
    """Lazily construct a DeviceBridgeManager and stash it in ctx.obj."""
    if "manager" not in ctx.obj:
        mgr = DeviceBridgeManager(output_dir=output_dir)
        # Honour explicit default from config
        default_dev = config.get("default_device", "")
        if default_dev:
            mgr.set_default_device(default_dev)
        ctx.obj["manager"] = mgr
    else:
        mgr = ctx.obj["manager"]
        if output_dir and not mgr.output_dir:
            mgr.set_output_dir(output_dir)
    return mgr


def resolve_device_or_fail(ctx: click.Context, explicit: str = "") -> tuple[DeviceBridgeManager, str]:
    """Resolve to a device id, or fail with a clear error and proper exit code.

    Precedence: explicit param > ctx.obj["device"] (from -d flag) > config default > auto-discover.
    """
    mgr = get_manager(ctx)
    requested = explicit or ctx.obj.get("device", "")
    try:
        dev = mgr.resolve_device(requested)
    except ValueError as e:
        output.fail(str(e), exit_code=output.EXIT_DEVICE, json_mode=ctx.obj.get("json", False))
        raise  # unreachable; satisfies type checkers
    return mgr, dev


def resolve_transport(ctx: click.Context) -> Transport:
    """Auto-resolve the best transport (serve TCP > ADB > editor).

    The result is cached in ctx.obj["transport"] for reuse within the same
    command invocation.
    """
    if "transport" in ctx.obj:
        return ctx.obj["transport"]

    t = auto_resolve(ctx, explicit_device=ctx.obj.get("device", ""))
    ctx.obj["transport"] = t
    return t


def is_json(ctx: click.Context) -> bool:
    return bool(ctx.obj.get("json", False))


def is_quiet(ctx: click.Context) -> bool:
    return bool(ctx.obj.get("quiet", False))
