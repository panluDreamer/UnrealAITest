# rdc-cli Setup Guide

One-time setup for RenderDoc frame capture analysis via the `rdc-cli` command-line tool.

rdc-cli is a Python package **managed by [uv](https://docs.astral.sh/uv/)** — uv handles Python version resolution, dependency isolation, and CLI tool installation.

## Prerequisites

| Requirement | Check Command | Notes |
|-------------|---------------|-------|
| Python 3.12 | `python --version` | Must be 3.12.x (bundled `.pyd` is compiled for 3.12). uv will auto-resolve if available. |
| uv | `uv --version` | Python package manager. Install: `curl -LsSf https://astral.sh/uv/install.sh \| sh` (or `pip install uv`) |

**No Visual Studio Build Tools, CMake, or compilation required.** The package ships with precompiled `renderdoc.pyd` + `renderdoc.dll` for RenderDoc v1.21 and v1.43.

## Installation (One Command)

```bash
cd <plugin_dir>/ThirdParty/RdcCli
uv tool install .
```

Where `<plugin_dir>` is the UnrealEngineAIAssist plugin directory, e.g.:
```bash
cd D:\Projects\MyGame\Plugins\UnrealEngineAIAssist\ThirdParty\RdcCli
uv tool install .
```

Verify:
```bash
rdc --version    # Should show rdc, version 0.5.3.dev5 or similar
rdc doctor       # Should show renderdoc-module: version=1.43
```

## What's Included

The package bundles precompiled RenderDoc Python modules:

| Version | Location in package | Notes |
|---------|-------------------|-------|
| v1.43 | `_renderdoc_bins/v1_43/py312/` | Newest, used by default |
| v1.21 | `_renderdoc_bins/v1_21/py312/` | Legacy stable version |

rdc-cli automatically discovers and uses the highest available version. Both versions include:
- `renderdoc.pyd` — Python binding (compiled for Python 3.12)
- `renderdoc.dll` — Core RenderDoc library
- `renderdoccmd.exe` — Command-line replay tool

## Test with a Capture

```bash
rdc open <path_to_any.rdc>
rdc info
rdc draws | head -20
rdc close
```

## Troubleshooting

### "rdc: command not found"

The tool isn't on PATH. Try:
```bash
cd <plugin_dir>/rdc-cli
uv tool install . --force
# Check uv tool bin path:
uv tool dir
```

### "renderdoc module not found"

The bundled Python bindings aren't being found:
```bash
# Verify Python version (must be 3.12.x)
rdc doctor

# If Python version mismatch, ensure uv uses 3.12:
uv tool install . --force --python 3.12
```

### "OpenCapture failed: ... E_INVALIDARG"

D3D12 GPU compatibility issue. rdc-cli automatically retries without forced GPU matching. If it still fails:
- Try replaying on the same machine/GPU that captured the frame
- Check that the RenderDoc version matches (v1.21 captures may need v1.21 replay)

### "Daemon connection failed"

Stale daemon from a previous session:
```bash
rdc close
rdc open <file.rdc>   # Re-open
```

## Updating

After pulling changes to the rdc-cli source, uv rebuilds from local source:
```bash
cd <plugin_dir>/ThirdParty/RdcCli
uv tool install . --force      # --force ensures uv picks up source changes
```

## Uninstall

```bash
uv tool uninstall rdc-cli      # removes the CLI tool and its isolated environment
```

## uv Management Notes

- `uv tool install .` creates an **isolated virtual environment** for rdc-cli with its own Python and dependencies — it won't conflict with other tools
- The `rdc` executable is placed in uv's bin directory (usually `~/.local/bin` or `%APPDATA%\uv\bin`), which should be on PATH
- Run `uv tool dir` to see where uv stores tool environments
- Run `uv tool list` to see all installed uv tools

## Advanced: Building for Other RenderDoc Versions

If you need a RenderDoc version not bundled (e.g., v1.30), you can still build from source:

```bash
rdc setup-renderdoc --version v1.30
```

This requires Visual Studio 2022 Build Tools with C++ workload and takes 5-10 minutes.
