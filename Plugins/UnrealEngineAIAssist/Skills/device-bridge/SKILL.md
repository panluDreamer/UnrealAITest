---
name: device-bridge
description: |
  Execute UE console commands, CVars, and UnLua code on a connected Android device,
  with persistent execution history and one-shot session context.
  Primary interface: the `devbridge` CLI (installed via uv tool install from ThirdParty/DevBridgeCli).
  Falls back to raw `adb shell` only when devbridge is unavailable.
  TRIGGER when:
  - User wants to run a console command on a real device ("set stat fps on device", "toggle shadow on phone")
  - User wants to change CVars on device ("set r.ShadowQuality to 0 on device")
  - User wants to execute Lua code on device ("run this Lua on device", "call ExecDoString")
  - User mentions device debugging, real-device testing, or on-device verification
  - User says "adb", "device", "phone", "android" in context of running commands
  DO NOT TRIGGER when:
  - User is working in the editor only (use ue-python-script instead)
  - User asks about iOS devices (not yet supported)
  - User asks about building/packaging APK (not this skill's scope)
---

# Device Bridge — `devbridge` CLI for Android device debugging

The `devbridge` CLI wraps `adb` with sensible defaults (log-category preflight,
PID-scoped logcat, ExecDoString RetVal parsing, persistent history). Use it
instead of raw `adb shell "am broadcast ..."` one-liners for everything except
the rare edge cases documented in `references/adb-raw-fallback.md`.

---

## ⚡ Activation Checklist

When this skill activates, **immediately** run:

```bash
devbridge --json snapshot
```

One call returns: `devices`, `default_device`, `game:{package,pid,running}`,
`preflight:{enabled,canary_ok,logcat_buffer}`, and the last 10 `history_tail`
entries. This is your session context — cache it in memory and only re-query
if the user switches device or restarts the game.

**Then follow these rules:**
- If `game.running: false` → tell user to launch the game app first.
- If `preflight.enabled: false` or `canary_ok: false` → run `devbridge preflight` once.
- If `history_tail` contains a relevant past entry → prefer `devbridge history show <id>`
  / `devbridge history replay <id>` over re-discovering the same Lua from scratch.

If `devbridge` is not installed (`devbridge: command not found`), install it:
```bash
cd <plugin>/ThirdParty/DevBridgeCli && uv tool install .
```
See `ThirdParty/DevBridgeCli/README.md` for details.

---

## Command Cheat Sheet

| Intent | Command |
|--------|---------|
| One-shot context snapshot | `devbridge --json snapshot` |
| Enable Log categories + grow buffer | `devbridge preflight` (idempotent; 24h cache) |
| Check preflight without changing state | `devbridge preflight --check` |
| Send a UE console command | `devbridge cmd 'stat fps'` |
| Set / get a CVar | `devbridge cvar set r.ShadowQuality 0` / `devbridge cvar get <name>` |
| Run Lua, get the RetVal parsed | `devbridge lua 'return 1+1'` |
| Run a Lua file | `devbridge lua-file ./script.lua` |
| Read logcat, game-process scoped | `devbridge logcat --grep RetVal` |
| Capture a screenshot | `devbridge screenshot -o out.png` |
| Device details | `devbridge info` |
| Pick default device | `devbridge use <device_id>` |
| Browse history | `devbridge history list [--tail N] [--grep ...] [--device ID]` |
| See a past entry | `devbridge history show <id>` (prefix-match OK) |
| Replay a past entry | `devbridge history replay <id> [--yes]` |

Global flags (must come **before** the subcommand): `--json`, `--quiet`/`-q`,
`--device ID`/`-d ID`.

---

## Three Modes (CLI-first)

### Mode 1: Console Command Execution

```bash
devbridge cmd 'stat fps'
devbridge cmd 'DisableAllScreenMessages'
devbridge cmd 'show collision'
```

Each invocation:
- auto-resolves the device (single device → implicit; multiple → `-d` required)
- broadcasts via `am broadcast -a android.intent.action.RUN -e cmd '...'`
- records to history (`history list --mode cmd`) for later replay

### Mode 2: CVar Debugging

```bash
devbridge cvar set r.ShadowQuality 0
devbridge cvar set r.MobileContentScaleFactor 1.5
devbridge cvar set sg.PostProcessQuality 0
devbridge cvar get r.ShadowQuality
```

**CVar Discovery**: Use `devbridge cvar get <name>` to read current values. Refer to your project's scalability configs or engine source for available CVar names. Never invent a CVar name.

### Mode 3: UnLua Code Execution

```bash
devbridge lua 'return 1+1'                                   # → [OK] retval: 2
devbridge lua 'return string.format("x=%d", 42)'             # → [OK] retval: x=42
devbridge --json lua 'return UE4.UGameplayStatics.GetGameInstance():GetName()'  # generic example
```

**What happens under the hood (one command, full flow):**
1. `adb logcat -c` — clear buffer so RetVal isn't drowned
2. `am broadcast ... ExecDoString <code>` — send
3. sleep 2s (configurable via `--wait`)
4. `adb logcat -d -s UE4:V` + grep for `ExecDoString RetVal:` — filter
5. Parse the last RetVal; detect `Error:[Error]` to surface xpcall failures
6. Persist to `<plugin>/.claude/devbridge/history/` with the code + retval + logcat excerpt

**Flags:**
- `--raw` — fire-and-forget (old behaviour, no clear/wait/parse)
- `--wait N` — override pre-poll sleep (default 2s)
- `--timeout N` — max total seconds to keep grepping (default 10s)
- `--summary "..."` — meaningful history summary (defaults to the code itself)
- `--no-history` — skip history recording

For multi-line Lua:
```bash
devbridge lua-file ./my_debug_script.lua
```

This `adb push`es the file to `/sdcard/devbridge_temp.lua` and runs `dofile(...)`.

---

## Log Category Enablement (handled by `devbridge preflight`)

Some projects silence `LogTemp` and `Log` by default, so `ExecDoString RetVal:` lines
are invisible in logcat until enabled. `devbridge preflight` handles the full
enablement sequence idempotently:

```bash
devbridge preflight
# Sends: Log LogTemp verbose, Log Log verbose
# Sets:  adb logcat -G 16M (ring buffer)
# Probes: canary ExecDoString "return 1+1" → expects retval=2
# Caches: <plugin>/.claude/devbridge/cache/<device_id>.json with 24h TTL
```

Second and subsequent calls within 24h short-circuit to "already enabled
(cached)" unless you pass `--force`.

To verify without modifying state:
```bash
devbridge preflight --check
```

If the canary fails (`canary_ok: false`), the RetVal pipeline is broken —
likely the game restarted and dropped the category state; run `devbridge preflight --force`.

---

## Reading logcat

`devbridge logcat` applies the game-PID filter and the `-s UE4:V` tag filter by default:

```bash
devbridge logcat                              # last 500 lines from the game process
devbridge logcat --grep RetVal                # substring filter (applied after read)
devbridge logcat --tag UE4:V --tag LogUnLua:E # two tag filters (applied by logcat itself)
devbridge logcat --no-pid                     # disable PID filter (all processes)
devbridge logcat --clear-only                 # just clear the buffer
devbridge logcat --follow --grep RetVal       # live stream (Ctrl+C to stop)
devbridge logcat --lines 2000                 # larger batch
```

Why tag filters beat post-hoc grep: tag filters (`-s UE4:V`) are applied by
logcat itself before lines enter the pipe, so they survive ring-buffer
rotation. `grep` runs on whatever got into stdout, which may already be
truncated on a noisy game. Prefer tag filters when you can.

Large output (>2000 chars) is auto-dumped to
`<plugin>/.claude/devbridge/logs/device_log_*.txt` and the CLI returns a summary
+ file path — use `Read`/`Grep` tools on that path to inspect.

---

## Persistent History

Every successful `devbridge cmd` / `devbridge lua` / `devbridge cvar set` is recorded
to `<plugin>/.claude/devbridge/history/`:

```
history/
  index.json                                # FIFO-200 array (see below)
  20260421_104500_spawn_water_pet.lua       # payload with header comment
  20260421_104500_spawn_water_pet.meta.json # retval, broadcast_output, logcat excerpt
```

Index entry schema: `{id, device, mode, summary, timestamp, success}`.

**AI workflow pattern:** before writing a new Lua snippet, grep history:
```bash
devbridge history list --grep "pet"           # was this task done before?
devbridge history show 20260421_104500        # see the exact code + retval
devbridge history replay 20260421_104500 -y   # re-execute it
```

Use `--summary "..."` on `lua`/`cmd` to make history entries grep-friendly.

---

## Utility Operations

```bash
devbridge devices [--json]           # list connected devices
devbridge use <device_id>            # persist as default (writes config.json)
devbridge info                       # model / Android / ABI / screen / GPU
devbridge doctor                     # adb path + version + devices + package + default
devbridge screenshot -o shot.png     # two-step screencap + pull (binary-safe)
```

Multi-device handling: if more than one device is connected and no default is
set, commands will error with `Multiple devices connected: ...`. Resolve with:
```bash
devbridge use <device_id>            # persist
# or per-call:
devbridge -d <device_id> cmd 'stat fps'
```

---

## Typical Debugging Workflow

Common pattern for on-device verification:

1. `devbridge cvar set <name> <value>` — apply the CVar under test
2. `devbridge screenshot -o before_after.png` — visual check
3. `devbridge lua '<query>'` — inspect game state
4. `devbridge history show <id>` — reference past runs

---

## When `devbridge` is missing or inadequate

Fall back to raw `adb` commands documented in `references/adb-raw-fallback.md`.
This includes corner cases devbridge does NOT cover:

- Running commands on a machine without `uv` installed
- Running on a device with a different package name (devbridge defaults to
  `<YOUR_PACKAGE>` via config)
- Very low-level `adb` operations: `reboot`, `install`, `uninstall`, `root`

---

## Domain knowledge (unchanged)

These files describe the project's runtime debug surface, not the tooling. They
remain valid and are tool-agnostic (example project-specific docs):

- `references/lua-patterns.md` — common Lua one-liners for `devbridge lua`
- `references/adb-commands.md` — project-specific protocol details (ExecDoString
  format, BroadcastReceiver semantics, RetVal line format). Useful when
  debugging devbridge itself or writing a new helper.

---

## Project Path Discovery

`devbridge` auto-discovers the plugin root by walking up from the CWD looking for
`UnrealEngineAIAssist.uplugin` + `Source/UnrealEngineAIAssist/`. It stores all
state under `<plugin_root>/.claude/devbridge/`:

```
config.json             # default_device, package_name, lua defaults
cache/<dev_id>.json     # preflight status, 24h TTL
history/                # see above
logs/                   # large logcat excerpts, screenshots
```

Override with `DEVBRIDGE_PLUGIN_DIR=<path>` when running outside the plugin tree.

---

## Limitations

- **Android only** — iOS not yet supported
- **Requires Development build** — the BroadcastReceiver is stripped in Shipping
- **`adb` required** — Android SDK platform-tools on PATH (or `ANDROID_HOME`)
- **`devbridge` requires Python 3.10+** via `uv tool install`

---

## Editor TCP Fallback (local testing)

When no ADB device is connected and no remote device is on TCP, the transport
layer can fall back to the **editor's runtime module** — useful for testing
the devbridge workflow without a physical device.

Prerequisites: editor running + `AIAssistDeviceBridge 127.0.0.1:8059` triggered once
(or `-AIAssistDeviceBridgeHost=127.0.0.1:8059` in editor launch args).

This does NOT change the skill's intended use (real-device debugging). It's a
developer convenience for validating commands locally before deploying to device.
For editor-only scripting (Python, asset manipulation), use `ue-python-script` instead.
