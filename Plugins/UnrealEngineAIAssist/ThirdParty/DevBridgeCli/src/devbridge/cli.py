"""devbridge CLI entry point.

Root ``click.Group`` that wires in all subcommand modules from ``devbridge.commands``.
Global flags (``--json``, ``--quiet``, ``-d/--device``) are attached to the root
group and made available to subcommands via ``ctx.obj``.
"""

from __future__ import annotations

import click

from . import __version__


@click.group(
    name="devbridge",
    help="CLI for UE4 Android device debugging via ADB.",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option(
    "--json",
    "json_mode",
    is_flag=True,
    default=False,
    help="Emit structured JSON instead of human-readable text.",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    default=False,
    help="Minimal output (id-only or single-line).",
)
@click.option(
    "--device",
    "-d",
    "device",
    default="",
    metavar="DEVICE_ID",
    help="Target device (from `adb devices`). Uses default / sole device if omitted.",
)
@click.version_option(version=__version__, prog_name="devbridge")
@click.pass_context
def entry(ctx: click.Context, json_mode: bool, quiet: bool, device: str) -> None:
    """Root group. Stashes global flags in ctx.obj for subcommand access."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_mode
    ctx.obj["quiet"] = quiet
    ctx.obj["device"] = device


# --------------------------------------------------------------------------- #
# Subcommand registration                                                     #
# --------------------------------------------------------------------------- #
# Imported here (not at module top) to avoid circular import issues during
# `from devbridge import cli` style introspection.


def _register_commands() -> None:
    from .commands import session, preflight, exec as exec_cmds, logcat, screenshot, history, snapshot, serve

    # Session / discovery
    entry.add_command(session.doctor)
    entry.add_command(session.devices)
    entry.add_command(session.use)
    entry.add_command(session.info)

    # Preflight
    entry.add_command(preflight.preflight)

    # Execution
    entry.add_command(exec_cmds.cmd)
    entry.add_command(exec_cmds.cvar)
    entry.add_command(exec_cmds.lua)
    entry.add_command(exec_cmds.lua_file)

    # Logcat
    entry.add_command(logcat.logcat)

    # Utility
    entry.add_command(screenshot.screenshot)
    entry.add_command(snapshot.snapshot)

    # History
    entry.add_command(history.history)

    # TCP server (device-bridge)
    entry.add_command(serve.serve)


_register_commands()


def main() -> None:  # pragma: no cover
    entry()


if __name__ == "__main__":  # pragma: no cover
    main()
