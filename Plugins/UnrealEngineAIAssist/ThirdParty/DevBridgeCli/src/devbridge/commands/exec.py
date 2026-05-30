"""Execution commands: cmd, cvar, lua, lua-file.

`lua` is the headline feature: it runs the full round-trip (clear buffer →
broadcast → wait → grep RetVal → parse) so a caller gets a structured return
value in a single invocation. `--raw` keeps the old fire-and-forget behaviour.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import click

from .. import config, history, output
from ..lua_parse import parse_retval
from ..transport import TCPProxyTransport
from ._shared import get_manager, is_json, is_quiet, resolve_device_or_fail, resolve_transport


# --------------------------------------------------------------------------- #
# `devbridge cmd <console_cmd>`                                               #
# --------------------------------------------------------------------------- #

@click.command(
    name="cmd",
    help="Send a UE console command to the device (e.g. 'stat fps').",
    context_settings={"ignore_unknown_options": True},
)
@click.argument("command", nargs=-1, required=True)
@click.option("--no-history", is_flag=True, default=False, help="Skip history recording.")
@click.option("--summary", default="", help="History summary (defaults to the command itself).")
@click.pass_context
def cmd(ctx: click.Context, command: tuple[str, ...], no_history: bool, summary: str) -> None:
    console_cmd = " ".join(command)

    # Try TCP proxy first (serve running + device connected)
    transport = resolve_transport(ctx)
    if isinstance(transport, TCPProxyTransport):
        resp = transport.send_command("exec_console", {"command": console_cmd})
        dev = "(tcp)"
    else:
        mgr, dev = resolve_device_or_fail(ctx)
        resp = mgr.exec_console(console_cmd, device_id=dev)

    if not no_history:
        history.record(
            mode="cmd",
            code=console_cmd,
            device_id=dev,
            summary=summary or console_cmd,
            success=bool(resp.get("success")),
            broadcast_output=resp.get("broadcast_output", ""),
            error=resp.get("error", ""),
        )

    exit_code = output.EXIT_OK if resp.get("success") else output.EXIT_DEVICE
    if is_json(ctx):
        output.emit(resp, json_mode=True)
    elif is_quiet(ctx):
        output.emit({"quiet_text": "ok" if resp.get("success") else "fail"}, quiet=True)
    else:
        if resp.get("success"):
            output.emit(resp, text=f"[OK] {dev}: {console_cmd}")
        else:
            output.emit(resp, text=f"[FAIL] {dev}: {console_cmd}\n  error: {resp.get('error', '')}")

    if exit_code != output.EXIT_OK:
        raise SystemExit(exit_code)


# --------------------------------------------------------------------------- #
# `devbridge cvar set/get`                                                    #
# --------------------------------------------------------------------------- #

@click.group(name="cvar", help="Get or set console variables.")
def cvar() -> None:
    pass


@cvar.command(name="set", help="Set a CVar: `devbridge cvar set r.ShadowQuality 0`.")
@click.argument("name")
@click.argument("value")
@click.option("--no-history", is_flag=True, default=False)
@click.pass_context
def cvar_set(ctx: click.Context, name: str, value: str, no_history: bool) -> None:
    transport = resolve_transport(ctx)
    if isinstance(transport, TCPProxyTransport):
        resp = transport.send_command("set_cvar", {"name": name, "value": value})
        dev = "(tcp)"
    else:
        mgr, dev = resolve_device_or_fail(ctx)
        resp = mgr.set_cvar(name, value, device_id=dev)

    if not no_history:
        history.record(
            mode="cvar",
            code=f"{name} {value}",
            device_id=dev,
            summary=f"set {name}={value}",
            success=bool(resp.get("success")),
            broadcast_output=resp.get("broadcast_output", ""),
            error=resp.get("error", ""),
        )

    if is_json(ctx):
        output.emit(resp, json_mode=True)
    else:
        tag = "[OK]" if resp.get("success") else "[FAIL]"
        output.emit(resp, text=f"{tag} {name} = {value}")
    if not resp.get("success"):
        raise SystemExit(output.EXIT_DEVICE)


@cvar.command(name="get", help="Read a CVar via ExecDoString (prints current value).")
@click.argument("name")
@click.option("--wait", "wait_seconds", type=float, default=None,
              help="Seconds to wait before grepping logcat (default from config).")
@click.pass_context
def cvar_get(ctx: click.Context, name: str, wait_seconds: float | None) -> None:
    """Implemented via ExecDoString + IConsoleManager::FindConsoleVariable."""
    lua_code = (
        "local cvar = UE4.UKismetSystemLibrary.GetConsoleVariableFloatValue and "
        "UE4.UKismetSystemLibrary.GetConsoleVariableFloatValue(\"%s\") or nil; "
        "return tostring(cvar)"
    ) % name.replace('"', '\\"')
    ctx.invoke(lua, code=(lua_code,), wait_seconds=wait_seconds, timeout_seconds=None,
               raw=False, no_history=False, summary=f"cvar_get {name}")


# --------------------------------------------------------------------------- #
# `devbridge lua <code>`                                                      #
# --------------------------------------------------------------------------- #

@click.command(
    name="lua",
    help=(
        "Run Lua via ExecDoString and return the parsed RetVal.\n\n"
        "Default flow: logcat -c → broadcast → sleep → grep RetVal → parse.\n"
        "--raw: send and exit immediately (old behaviour)."
    ),
    context_settings={"ignore_unknown_options": True},
)
@click.argument("code", nargs=-1, required=True)
@click.option("--wait", "wait_seconds", type=float, default=None,
              help="Seconds to wait before grepping logcat (default from config).")
@click.option("--timeout", "timeout_seconds", type=float, default=None,
              help="Max total seconds to poll for RetVal (default from config).")
@click.option("--raw", is_flag=True, default=False,
              help="Fire-and-forget: broadcast only, do not clear/wait/parse.")
@click.option("--no-history", is_flag=True, default=False)
@click.option("--summary", default="", help="History summary.")
@click.pass_context
def lua(ctx: click.Context, code: tuple[str, ...],
        wait_seconds: float | None, timeout_seconds: float | None,
        raw: bool, no_history: bool, summary: str) -> None:
    lua_code = " ".join(code)

    # Try TCP proxy first — if available, send_command gives synchronous retval
    transport = resolve_transport(ctx)
    if isinstance(transport, TCPProxyTransport):
        resp = transport.send_command("exec_unlua", {"code": lua_code})
        dev = "(tcp)"

        if not no_history:
            history.record(
                mode="lua", code=lua_code, device_id=dev,
                summary=summary, success=bool(resp.get("success")),
                retval=resp.get("output", ""), error=resp.get("error", ""),
                broadcast_output="(tcp)",
            )

        result_data = {
            "success": resp.get("success", False),
            "device_id": dev,
            "code": lua_code,
            "retval": resp.get("output", ""),
            "error": resp.get("error", ""),
        }

        if is_json(ctx):
            output.emit(result_data, json_mode=True)
        elif is_quiet(ctx):
            output.emit({"quiet_text": resp.get("output", "")}, quiet=True)
        else:
            if resp.get("success"):
                output.emit(result_data, text=f"[OK] retval: {resp.get('output', '(no output)')}")
            else:
                output.emit(result_data, text=f"[FAIL] {resp.get('error', '')}")

        if not resp.get("success"):
            raise SystemExit(output.EXIT_FAILED)
        return

    # Fallback to ADB mode
    mgr, dev = resolve_device_or_fail(ctx)

    wait_s = wait_seconds if wait_seconds is not None else float(config.get("lua_default_wait_seconds", 2.0))
    timeout_s = timeout_seconds if timeout_seconds is not None else float(config.get("lua_default_timeout_seconds", 10.0))

    if raw:
        resp = mgr.exec_unlua(lua_code, device_id=dev)
        if not no_history:
            history.record(
                mode="lua",
                code=lua_code,
                device_id=dev,
                summary=summary,
                success=bool(resp.get("success")),
                broadcast_output=resp.get("broadcast_output", ""),
                error=resp.get("error", ""),
                extra_meta={"raw": True},
            )
        if is_json(ctx):
            output.emit(resp, json_mode=True)
        else:
            tag = "[OK raw]" if resp.get("success") else "[FAIL]"
            output.emit(resp, text=f"{tag} broadcast sent (no RetVal read). Use `devbridge logcat --grep RetVal` if needed.")
        if not resp.get("success"):
            raise SystemExit(output.EXIT_DEVICE)
        return

    # Full auto flow
    mgr.adb.logcat_clear(dev)
    broadcast = mgr.exec_unlua(lua_code, device_id=dev)

    if not broadcast.get("success"):
        if not no_history:
            history.record(
                mode="lua",
                code=lua_code,
                device_id=dev,
                summary=summary,
                success=False,
                error=broadcast.get("error", "broadcast failed"),
                broadcast_output=broadcast.get("broadcast_output", ""),
            )
        output.fail(broadcast.get("error", "broadcast failed"),
                    exit_code=output.EXIT_DEVICE, json_mode=is_json(ctx))
        return

    time.sleep(wait_s)

    # Poll with -s UE4:V filter (applied by logcat itself)
    deadline = time.time() + timeout_s
    logcat_text = ""
    parsed = None
    while time.time() < deadline:
        out_text, err = mgr.adb.logcat(dev, lines=500, filter_expr="-s UE4:V", timeout=10.0)
        if err:
            break
        logcat_text = out_text
        parsed = parse_retval(out_text)
        if parsed.retval is not None:
            break
        time.sleep(0.5)

    if parsed is None:
        parsed = parse_retval(logcat_text)

    result_data = {
        "success": parsed.success,
        "device_id": dev,
        "code": lua_code,
        "retval": parsed.retval,
        "raw_line": parsed.raw_line,
        "error": parsed.error,
        "retval_count": len(parsed.all_retvals),
    }

    if not no_history:
        history.record(
            mode="lua",
            code=lua_code,
            device_id=dev,
            summary=summary,
            success=parsed.success,
            retval=parsed.retval,
            error=parsed.error or "",
            broadcast_output=broadcast.get("broadcast_output", ""),
            logcat_excerpt=logcat_text,
        )

    if is_json(ctx):
        output.emit(result_data, json_mode=True)
    elif is_quiet(ctx):
        # Just the retval itself on stdout for scripting
        output.emit({"quiet_text": parsed.retval if parsed.retval is not None else ""}, quiet=True)
    else:
        if parsed.success:
            output.emit(result_data, text=f"[OK] retval: {parsed.retval}")
        else:
            output.emit(result_data,
                        text=f"[FAIL] {parsed.error or '(no retval)'}\n"
                             f"  Hint: if no RetVal at all, run `devbridge preflight`.")

    if not parsed.success:
        raise SystemExit(output.EXIT_FAILED)


# --------------------------------------------------------------------------- #
# `devbridge lua-file <path>`                                                 #
# --------------------------------------------------------------------------- #

@click.command(
    name="lua-file",
    help="Push a .lua file to /sdcard and dofile() it via ExecDoString.",
)
@click.argument("path", type=click.Path(exists=True, dir_okay=False, resolve_path=True))
@click.option("--remote", default="/sdcard/devbridge_temp.lua",
              help="Remote path on device (default /sdcard/devbridge_temp.lua).")
@click.option("--wait", "wait_seconds", type=float, default=None)
@click.option("--timeout", "timeout_seconds", type=float, default=None)
@click.option("--raw", is_flag=True, default=False)
@click.option("--no-history", is_flag=True, default=False)
@click.option("--summary", default="")
@click.pass_context
def lua_file(ctx: click.Context, path: str, remote: str,
             wait_seconds: float | None, timeout_seconds: float | None,
             raw: bool, no_history: bool, summary: str) -> None:
    mgr, dev = resolve_device_or_fail(ctx)

    ok = mgr.adb.push(dev, path, remote)
    if not ok:
        output.fail(f"adb push failed: {path} -> {remote}",
                    exit_code=output.EXIT_DEVICE, json_mode=is_json(ctx))
        return

    # Escape double-quotes inside path
    safe_remote = remote.replace('"', '\\"')
    dof_code = f'dofile("{safe_remote}")'

    file_summary = summary or f"lua-file {Path(path).name}"

    ctx.invoke(lua, code=(dof_code,), wait_seconds=wait_seconds,
               timeout_seconds=timeout_seconds, raw=raw,
               no_history=no_history, summary=file_summary)
