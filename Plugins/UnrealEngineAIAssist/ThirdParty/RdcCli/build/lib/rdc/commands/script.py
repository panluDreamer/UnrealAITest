"""rdc script command -- execute a Python script inside the daemon."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import click

from rdc.commands._helpers import call


def _parse_args(raw: tuple[str, ...]) -> dict[str, str]:
    """Parse KEY=VALUE pairs into a dict.

    Raises:
        click.BadParameter: If any value is missing '='.
    """
    result: dict[str, str] = {}
    for item in raw:
        if "=" not in item:
            raise click.BadParameter(
                f"invalid format {item!r}, expected KEY=VALUE", param_hint="'--arg'"
            )
        k, v = item.split("=", 1)
        result[k] = v
    return result


@click.command("script")
@click.argument(
    "script_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=False,
    default=None,
)
@click.option(
    "--code", "-c",
    default=None,
    help="Execute inline Python code string (no temp file needed).",
)
@click.option("--arg", "args", multiple=True, metavar="KEY=VALUE", help="Script argument.")
@click.option("--json", "use_json", is_flag=True, help="Raw JSON output.")
def script_cmd(
    script_file: Path | None,
    code: str | None,
    args: tuple[str, ...],
    use_json: bool,
) -> None:
    """Execute a Python script inside the daemon process.

    Provide either a SCRIPT_FILE path or use --code/-c for inline Python.

    \b
    The script runs with these variables pre-injected:
      controller  ReplayController instance (live replay session)
      rd          renderdoc module (enums, types, helpers)
      adapter     RenderDocAdapter instance (high-level wrapper)
      state       DaemonState object (capture metadata, caches)
      args        dict of --arg KEY=VALUE arguments

    Assign to `result` to return structured data.

    \b
    Examples:
      rdc script analysis.py
      rdc script --code "print(len(controller.GetRootActions()))"
      rdc script -c "for t in controller.GetTextures()[:5]: print(t.width, t.height)"
    """
    if code and script_file:
        click.echo("error: provide either SCRIPT_FILE or --code, not both", err=True)
        raise SystemExit(1)
    if not code and not script_file:
        click.echo("error: provide SCRIPT_FILE or --code/-c", err=True)
        raise SystemExit(1)

    args_dict = _parse_args(args)

    if code:
        # Write inline code to a temp file, execute, then clean up
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".py", prefix="rdc_inline_")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(code)
            params: dict[str, Any] = {
                "path": tmp_path,
                "args": args_dict,
            }
            result = call("script", params)
        finally:
            os.unlink(tmp_path)
    else:
        params = {
            "path": str(script_file.resolve()),
            "args": args_dict,
        }
        result = call("script", params)

    if use_json:
        click.echo(json.dumps(result))
        return

    stdout_text = result.get("stdout", "")
    if stdout_text:
        click.echo(stdout_text, nl=False)

    stderr_text = result.get("stderr", "")
    if stderr_text:
        click.echo(stderr_text, err=True, nl=False)

    elapsed = result.get("elapsed_ms", 0)
    click.echo(f"# elapsed: {elapsed} ms", err=True)

    return_value = result.get("return_value")
    if return_value is not None:
        click.echo(f"# result: {return_value}", err=True)
