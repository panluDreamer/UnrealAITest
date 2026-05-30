"""history command group: list, show, replay."""

from __future__ import annotations

import json as _json

import click

from .. import history as hist
from .. import output
from ._shared import is_json, is_quiet


@click.group(name="history", help="Browse and replay past devbridge executions.")
def history() -> None:
    pass


@history.command(name="list", help="List history entries (most recent last).")
@click.option("--tail", "-n", type=int, default=20, help="Last N entries (0 = all).")
@click.option("--grep", default=None, help="Substring filter on id / summary / mode.")
@click.option("--device", default=None, help="Filter by device id.")
@click.option("--mode", default=None,
              type=click.Choice(["lua", "cmd", "cvar", "lua_file"]),
              help="Filter by execution mode.")
@click.option("--success-only", is_flag=True, default=False)
@click.pass_context
def history_list(ctx: click.Context, tail: int, grep: str, device: str,
                 mode: str, success_only: bool) -> None:
    entries = hist.list_entries(tail=tail, grep=grep, device=device,
                                mode=mode, success_only=success_only)

    if is_json(ctx):
        output.emit(entries, json_mode=True)
        return
    if is_quiet(ctx):
        for e in entries:
            output.emit({"quiet_text": e["id"]}, quiet=True)
        return
    if not entries:
        output.emit(entries, text="(no matching history entries)")
        return

    rows = ["TIMESTAMP\t\t\tOK\tMODE\tDEVICE\t\tSUMMARY"]
    for e in entries:
        rows.append(
            f"{e.get('timestamp', ''):24s}\t{'Y' if e.get('success') else 'N'}\t"
            f"{e.get('mode', ''):<6s}\t{e.get('device', '')[:12]:<12s}\t{e.get('summary', '')}"
        )
    output.emit(entries, text="\n".join(rows))


@history.command(name="show", help="Show a history entry's code + meta.")
@click.argument("entry_id")
@click.pass_context
def history_show(ctx: click.Context, entry_id: str) -> None:
    # Allow partial prefix match
    resolved = hist.find_by_prefix(entry_id) or entry_id
    code, meta, path = hist.show(resolved)

    if code is None and meta is None:
        output.fail(f"history entry not found: {entry_id}",
                    exit_code=output.EXIT_FAILED, json_mode=is_json(ctx))
        return

    data = {"id": resolved, "path": str(path) if path else "", "meta": meta, "code": code}

    if is_json(ctx):
        output.emit(data, json_mode=True)
        return

    lines = [
        f"id:        {resolved}",
        f"path:      {path}",
        f"meta:      {_json.dumps(meta, ensure_ascii=False, indent=2) if meta else '(none)'}",
        "",
        "--- code ---",
        code or "(payload missing)",
    ]
    output.emit(data, text="\n".join(lines))


@history.command(name="replay", help="Re-execute a history entry.")
@click.argument("entry_id")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation.")
@click.pass_context
def history_replay(ctx: click.Context, entry_id: str, yes: bool) -> None:
    resolved = hist.find_by_prefix(entry_id) or entry_id
    code, meta, _ = hist.show(resolved)
    if code is None or meta is None:
        output.fail(f"history entry not found: {entry_id}",
                    exit_code=output.EXIT_FAILED, json_mode=is_json(ctx))
        return

    mode = meta.get("mode", "")
    if not yes:
        click.echo(f"Replay {resolved} (mode={mode}, device={meta.get('device', '')}):")
        click.echo(f"  summary: {meta.get('summary', '')}")
        click.echo("  --- code ---")
        click.echo(code)
        click.echo("  --- end ---")
        if not click.confirm("Replay?", default=False):
            output.emit({"cancelled": True}, text="cancelled")
            return

    # Dispatch to the appropriate command
    from . import exec as exec_cmds
    if mode == "lua" or mode == "lua_file":
        ctx.invoke(exec_cmds.lua, code=(code,), wait_seconds=None,
                   timeout_seconds=None, raw=False, no_history=False,
                   summary=f"replay of {resolved}")
    elif mode == "cmd":
        ctx.invoke(exec_cmds.cmd, command=tuple(code.strip().split()),
                   no_history=False, summary=f"replay of {resolved}")
    elif mode == "cvar":
        # code is "<name> <value>"
        parts = code.strip().split(None, 1)
        if len(parts) != 2:
            output.fail(f"cannot parse cvar payload: {code!r}",
                        exit_code=output.EXIT_FAILED, json_mode=is_json(ctx))
            return
        ctx.invoke(exec_cmds.cvar_set, name=parts[0], value=parts[1], no_history=False)
    else:
        output.fail(f"unknown history mode: {mode}",
                    exit_code=output.EXIT_FAILED, json_mode=is_json(ctx))
