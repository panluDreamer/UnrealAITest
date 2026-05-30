# devbridge-cli verification log

Command matrix run against a real device during initial development.
Re-run this after any non-trivial refactor.

## Environment

- Host: Windows 11 Pro (26200), Python 3.12, uv 0.x
- Device: realme RMX1991 (Android 11, sdk 30, Adreno 618), id `79a39161`
- Game build: Development (BroadcastReceiver active)
- Date: 2026-04-21

## Install

```bash
rm -rf build/ src/*.egg-info  # only if re-installing after local edits
cd ThirdParty/DevBridgeCli
uv tool install .             # first install
uv tool install . --reinstall --force  # after pulling source changes
```

**IMPORTANT — setuptools cache gotcha:** if you edit source and re-install
without cleaning `build/` + `src/devbridge_cli.egg-info/`, the wheel will contain
STALE code. Symptom: code in the installed `site-packages/devbridge/` (the internal
Python package name) doesn't match the source tree, and fixes appear not to take effect. Always clean
caches before re-install, or rely on `.gitignore` + `uv tool install .`
starting from a fresh worktree.

## Results

| Command | Status | Notes |
|---------|--------|-------|
| `devbridge --version` | ✅ | Prints `0.1.0` |
| `devbridge --help` | ✅ | Lists all 13 commands |
| `devbridge doctor` | ✅ | Reports adb path, version, devices, default, package |
| `devbridge devices` | ✅ | TSV output; `--json` returns structured array; `--quiet` one id per line |
| `devbridge info` | ✅ | Model, Android 11, sdk 30, 1080x2340, Adreno 618 |
| `devbridge preflight` | ✅ | First run enables, caches, grows buffer to 16MiB, runs canary (retval=2) |
| `devbridge preflight --check` | ✅ | Reports `enabled: True (cached)` on second call |
| `devbridge cmd 'stat fps'` | ✅ | Broadcast completes, stat HUD visible on device |
| `devbridge cvar set r.ScreenPercentage 80` | ✅ | Visual change observed |
| `devbridge cvar set r.ScreenPercentage 100` | ✅ | Restore works |
| `devbridge lua 'return 1+1'` | ✅ | Returns `[OK] retval: 2` |
| `devbridge --json lua '...'` | ✅ | Structured response with retval/raw_line/error |
| `devbridge lua 'error("x")'` | ✅ | Correctly identified as failure (exit 1) |
| `devbridge history list` | ✅ | Shows entries sorted oldest-first |
| `devbridge history list --mode cvar` | ✅ | Filter works |
| `devbridge history list --grep "stat fps"` | ✅ | Grep works |
| `devbridge history show <id>` | ✅ | Shows code + full meta |
| `devbridge history show <prefix>` | ✅ | Prefix match resolves unambiguously |
| `devbridge history replay <id> --yes` | ✅ | Re-executes, re-returns retval=2 |
| `devbridge screenshot -o <path>` | ✅ | 2.1 MB PNG saved |
| `devbridge --json snapshot` | ✅ | All 10 top-level keys present |
| `devbridge snapshot` (no device) | ✅ | Graceful — empty devices list, history_tail preserved |
| `devbridge logcat --lines 5` | ✅ | Default PID filter applied, returns recent game lines |
| `devbridge logcat --tag UE4:V` | ✅ | Tag filter works |
| `devbridge logcat --grep RetVal` | ✅ | Keyword filter works |
| `devbridge logcat --clear-only` | ✅ | Clears buffer |

## Regression: MCP server isolation

```bash
grep -r "from device_bridge\|import device_bridge" Skills/ ThirdParty/
# → empty (only `.svn/pristine/` SVN copies, not real imports)
```

MCP server (`Skills/ue-python-script/mcp_server/unreal_agent_bridge_mcp.py`) never
imported `device_bridge.py`; moving the module to `ThirdParty/DevBridgeCli/src/devbridge/adb.py`
has zero runtime impact on the MCP server.

## SVN externals sync

```bash
svn up .claude/skills/device-bridge
diff Skills/device-bridge/SKILL.md .claude/skills/device-bridge/SKILL.md
# → identical (externals auto-sync)
```

## Known gotchas

1. **setuptools build cache** — see install notes above. Symptom is stale code
   in the installed package.
2. **Lua boolean returns** — `return true` yields an empty `retval` string;
   the game's ExecDoString only stringifies certain types. Wrap with `tostring(...)`
   when debugging boolean/nil/table results.
3. **Global flags must precede the subcommand**: `devbridge --json devices` works,
   `devbridge devices --json` fails with "No such option".
4. **`uv tool install .` clashes with existing install**: needs `--reinstall
   --force` *and* must delete `~/.local/bin/devbridge.exe` first if Windows holds
   the handle.
