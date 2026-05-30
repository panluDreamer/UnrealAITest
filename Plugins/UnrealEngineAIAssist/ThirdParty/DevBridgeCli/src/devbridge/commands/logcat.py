"""logcat command — filtered reads, optional clear, optional follow."""

from __future__ import annotations

import subprocess
import sys

import click

from .. import config, output
from ..transport import TCPProxyTransport
from ._shared import get_manager, is_json, resolve_device_or_fail, resolve_transport


@click.command(name="logcat", help="Read (or tail / clear) logcat with game-aware defaults.")
@click.option("--lines", "-n", type=int, default=500,
              help="Number of recent lines (ignored with --follow).")
@click.option("--tag", "tags", multiple=True, default=[],
              help="Logcat tag filter (repeatable; e.g. --tag UE4:V --tag LogUnLua:E).")
@click.option("--grep", default="", help="Case-insensitive substring filter applied after read.")
@click.option("--pid-only/--no-pid", default=True,
              help="Restrict to the game process (default on).")
@click.option("--clear", "do_clear", is_flag=True, default=False,
              help="Clear the ring buffer after reading.")
@click.option("--clear-only", is_flag=True, default=False,
              help="Clear and exit, don't read.")
@click.option("--follow", "-f", is_flag=True, default=False,
              help="Stream live (Ctrl+C to stop).")
@click.pass_context
def logcat(ctx: click.Context, lines: int, tags: tuple[str, ...], grep: str,
           pid_only: bool, do_clear: bool, clear_only: bool, follow: bool) -> None:

    # --- TCP transport path ---
    transport = resolve_transport(ctx)
    if isinstance(transport, TCPProxyTransport):
        if clear_only or do_clear:
            output.fail("logcat clear not supported in TCP mode (device LogCapture has no clear API). Use ADB.",
                        exit_code=output.EXIT_DEVICE, json_mode=is_json(ctx))
            return
        if follow:
            output.fail("logcat --follow not supported in TCP mode (requires ADB for live stream).",
                        exit_code=output.EXIT_DEVICE, json_mode=is_json(ctx))
            return

        # Batched read via device-side LogCapture ring buffer
        params: dict = {"count": lines}
        if grep:
            params["filter"] = grep
        if tags:
            # Extract category from tag format "UE4:V" → "UE4"
            params["category"] = tags[0].split(":")[0]

        resp = transport.send_command("get_log", params)

        if not resp.get("success"):
            output.fail(resp.get("error", "get_log failed"),
                        exit_code=output.EXIT_DEVICE, json_mode=is_json(ctx))
            return

        if is_json(ctx):
            output.emit(resp, json_mode=True)
        else:
            entries = resp.get("entries", [])
            if not entries:
                output.emit(resp, text="(no log entries)")
            else:
                text_lines = []
                for e in entries:
                    cat = e.get("category", "")
                    msg = e.get("message", "")
                    verb = e.get("verbosity", "info")
                    text_lines.append(f"[{cat}][{verb}] {msg}")
                output.emit(resp, text="\n".join(text_lines))
        return

    # --- ADB path (original logic) ---
    mgr, dev = resolve_device_or_fail(ctx)

    if clear_only:
        ok = mgr.adb.logcat_clear(dev)
        status = {"success": ok, "device_id": dev}
        if is_json(ctx):
            output.emit(status, json_mode=True)
        else:
            output.emit(status, text="logcat buffer cleared" if ok else "clear failed")
        return

    # Build filter args
    filter_parts: list[str] = []

    if pid_only:
        pkg = config.get("package_name", "com.yourcompany.yourgame")
        pid = mgr.adb.pidof(dev, pkg)
        if pid:
            filter_parts.append(f"--pid={pid}")
        # If PID unresolved we silently fall back to unfiltered — game might not be running

    if tags:
        # Default pattern: `-s UE4:V LogUnLua:V` silences everything else
        filter_parts.append("-s")
        for t in tags:
            filter_parts.append(t)

    filter_expr = " ".join(filter_parts)

    if follow:
        # Stream mode bypasses our get_log/dump layer
        cmd = [mgr.adb.adb_path, "-s", dev, "logcat"] + filter_expr.split()
        if grep:
            # We can't easily pipe to grep here on Windows. Stream and filter in Python.
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        encoding="utf-8", errors="replace")
                assert proc.stdout is not None
                needle = grep.lower()
                for line in proc.stdout:
                    if needle in line.lower():
                        sys.stdout.write(line)
                        sys.stdout.flush()
            except KeyboardInterrupt:
                proc.terminate()
            return
        try:
            subprocess.run(cmd)
        except KeyboardInterrupt:
            pass
        return

    # Batched read via DeviceBridgeManager.get_log (handles file-dump for big output)
    resp = mgr.get_log(lines=lines, filter_expr=filter_expr,
                       text_filter=grep, device_id=dev)

    if do_clear:
        mgr.adb.logcat_clear(dev)

    if not resp.get("success"):
        output.fail(resp.get("error", "logcat failed"),
                    exit_code=output.EXIT_DEVICE, json_mode=is_json(ctx))
        return

    if is_json(ctx):
        output.emit(resp, json_mode=True)
    else:
        if "log_output" in resp:
            output.emit(resp, text=resp["log_output"])
        else:
            # Large output was dumped to file
            output.emit(resp, text=f"{resp['log_summary']}\n\n-- {resp['hint']}")
