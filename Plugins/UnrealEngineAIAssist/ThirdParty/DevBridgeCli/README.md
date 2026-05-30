# devbridge — UE4 Android device debugging CLI

A thin wrapper over `adb` that encodes the project's on-device debugging workflow: console commands, CVars, UnLua `ExecDoString`, logcat filtering, and persistent execution history.

Modeled after [`rdc-cli`](../RdcCli/) and installed the same way.

## Install

```bash
cd ThirdParty/DevBridgeCli
uv tool install .
# Update after source changes:
uv tool install . --force
# Uninstall:
uv tool uninstall devbridge-cli
```

Requires Python 3.10+ and `adb` on PATH (Android SDK platform-tools).

## Quick start

```bash
devbridge snapshot --json              # one-shot context: devices + game PID + preflight + history tail
devbridge preflight                    # enable Log/LogTemp categories + grow logcat buffer (idempotent)
devbridge lua 'return 1+1'             # ExecDoString with auto clear→send→wait→parse RetVal
devbridge cmd 'stat fps'               # any UE console command
devbridge cvar set r.ShadowQuality 0
devbridge logcat --tag UE4:V --grep RetVal
devbridge history list --tail 20
devbridge history show 20260421_104500_spawn_water_pet
devbridge history replay 20260421_104500_spawn_water_pet
```

## Command index

| Group | Commands |
|-------|----------|
| Session | `doctor`, `devices`, `use <id>`, `info` |
| Preflight | `preflight [--check]` |
| Execution | `cmd <cmd>`, `cvar get/set`, `lua <code>`, `lua-file <path>` |
| Logcat | `logcat [--tag --grep --follow --clear --pid-only --lines N]` |
| Utility | `screenshot [-o file.png]`, `snapshot [--json]` |
| History | `history list`, `history show <id>`, `history replay <id>` |

Every command supports `--json` for structured output and `-d/--device <id>` to target a specific device when multiple are connected.

## Persistent state

Under `<plugin>/.claude/devbridge/`:

```
config.json            # default device, package name (<YOUR_PACKAGE>)
cache/<dev_id>.json    # preflight status (24h TTL)
history/
  index.json           # [{id, device, mode, summary, timestamp, success}, ...]  FIFO-200
  {id}.lua             # code with header comment
  {id}.meta.json       # retval, logcat excerpt path, etc.
logs/
  logcat_{id}.txt      # large logcat excerpts
```

History survives across Claude sessions — AI agents can grep for prior successful commands and replay them.

## Architecture

```
AI / user ──Bash──> devbridge ──subprocess──> adb ──> device
                       │
                       └─> <plugin>/.claude/devbridge/  (history, cache, logs)
```

No daemon, no TCP, no MCP server. Each invocation is independent — stateless except for the project-scoped persistence directory.

## Why `devbridge` over raw `adb shell`?

| Pain with raw `adb` | `devbridge` solution |
|--------------------|-------------------|
| 5+ separate tool calls per ExecDoString (clear → broadcast → sleep → grep → parse) | `devbridge lua '<code>'` does all five |
| `Log LogTemp verbose` must be re-sent every session, easy to forget | `devbridge preflight` is idempotent (24h TTL cache) |
| Game log volume drowns RetVal lines | Auto tag filter `-s UE4:V`, PID filter, big ring buffer |
| No cross-session memory | `<plugin>/.claude/devbridge/history/` + `history list/show/replay` |
| Need 6 probes to understand device state | `devbridge snapshot` aggregates into one JSON |

## Integration with the plugin

`setup.py` adds `Bash(devbridge:*)` to the agent's permitted commands so Claude Code can invoke `devbridge` directly. See `Skills/device-bridge/SKILL.md` for how the agent uses it.
