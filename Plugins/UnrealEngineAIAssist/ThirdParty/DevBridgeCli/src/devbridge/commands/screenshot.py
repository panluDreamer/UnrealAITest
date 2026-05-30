"""screenshot command."""

from __future__ import annotations

import click

from .. import output, paths
from ._shared import get_manager, is_json, resolve_device_or_fail


@click.command(name="screenshot", help="Capture a screenshot and save locally.")
@click.option("-o", "--out", "out_path", default="",
              help="Output .png path (default: <plugin>/.claude/devbridge/logs/screenshot_<ts>.png).")
@click.pass_context
def screenshot(ctx: click.Context, out_path: str) -> None:
    mgr, dev = resolve_device_or_fail(ctx)
    if not out_path:
        # Use the plugin's logs dir for a stable default (same place big logcats land)
        import time
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = str(paths.logs_dir() / f"screenshot_{dev}_{ts}.png")

    resp = mgr.screenshot(device_id=dev, out_path=out_path)

    if is_json(ctx):
        output.emit(resp, json_mode=True)
    else:
        if resp.get("success"):
            output.emit(resp, text=f"saved: {resp['file_path']}")
        else:
            output.fail(resp.get("error", "screenshot failed"),
                        exit_code=output.EXIT_DEVICE, json_mode=False)
    if not resp.get("success"):
        raise SystemExit(output.EXIT_DEVICE)
