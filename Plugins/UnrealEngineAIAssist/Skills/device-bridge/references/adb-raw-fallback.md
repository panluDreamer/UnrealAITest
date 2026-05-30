# Raw ADB fallback reference

**Use this only when `devbridge` is unavailable or lacks coverage for a corner case.**

For normal workflows, see `../SKILL.md` and use the `devbridge` CLI. This document
preserves the raw `adb` knowledge for three situations:

1. `devbridge` is not installed on the current machine (e.g. CI runner, a QA
   engineer's first encounter).
2. The game is repackaged under a different Android package name and
   `config.json` has not been updated.
3. Low-level operations `devbridge` intentionally does not wrap (reboot, install,
   uninstall, root, port forwarding, etc.).

---

## The core mechanism

UE4 Android (non-Shipping) registers a `BroadcastReceiver` for
`android.intent.action.RUN`. The `cmd` extra is piped through `GEngine->Exec()`.

```bash
adb shell "am broadcast -a android.intent.action.RUN -e cmd '<command>'"
```

Expected output:
```
Broadcasting: Intent { act=android.intent.action.RUN flg=0x400000 (has extras) }
Broadcast completed: result=0
```

## Enabling log categories (required preflight)

`LogTemp` and `Log` are silenced by default. Must be enabled each game session:

```bash
adb shell "am broadcast -a android.intent.action.RUN -e cmd 'Log LogTemp verbose'"
adb shell "am broadcast -a android.intent.action.RUN -e cmd 'Log Log verbose'"
adb logcat -G 16M   # grow ring buffer
```

Verify with a canary:
```bash
adb logcat -c
adb shell "am broadcast -a android.intent.action.RUN -e cmd 'ExecDoString return 1+1'"
sleep 2
adb logcat -d -t 200 | grep "ExecDoString RetVal"
# Expected: ...LogTemp: [PlatformGameInstance]ExecDoString RetVal:2
```

## ExecDoString manual flow

```bash
# 1. Clear (don't skip — the game emits thousands of lines/sec)
adb logcat -c

# 2. Send
adb shell "am broadcast -a android.intent.action.RUN -e cmd 'ExecDoString return 1+1'"

# 3. Wait
sleep 2

# 4. Filtered read (tag filter preferred over post-hoc grep)
PID=$(adb shell pidof <YOUR_PACKAGE> | tr -d '\r')
adb logcat -d --pid=$PID -s UE4:V | grep "ExecDoString RetVal"
```

Quoting rules:

| Scenario | Solution |
|----------|----------|
| Simple expression | `'ExecDoString return 1+1'` |
| Double quotes in Lua | Escape with `\"`: `'ExecDoString return string.format(\"x\")'` |
| Single quotes in Lua | Use `string.char(39)` or escape: `'ExecDoString return "it'\''s"'` |
| Multi-line script | Push file: `adb push script.lua /sdcard/t.lua` then `ExecDoString dofile("/sdcard/t.lua")` |

## Logcat without `devbridge`

```bash
adb logcat -c                                              # clear
adb logcat -G 16M                                          # grow buffer
adb logcat -g                                              # inspect buffer sizes

# Tag filter (PREFERRED — applied in logd before pipe)
adb logcat -d -s "UE4:V"
adb logcat -d -s "UE4:V" "LogUnLua:E"

# PID filter
PID=$(adb shell pidof <YOUR_PACKAGE> | tr -d '\r')
adb logcat -d --pid=$PID -t 500

# Keyword filter (post-hoc, may miss rotated lines)
adb logcat -d -t 500 | grep "ExecDoString RetVal"
```

## Device info and utility

```bash
adb devices -l                                 # list
adb -s <id> shell getprop ro.product.model     # model
adb shell getprop ro.build.version.release     # android version
adb shell "dumpsys SurfaceFlinger | grep GLES" # GPU
adb shell wm size                              # screen
adb shell pidof <YOUR_PACKAGE>                # game PID
```

## Screenshot

```bash
adb shell screencap -p /data/local/tmp/screen.png
adb pull /data/local/tmp/screen.png ./shot.png
# Fallback: exec-out pipe
adb exec-out screencap -p > shot.png
```

## File operations

```bash
adb push local.lua /sdcard/temp.lua
adb pull /sdcard/some.log ./local.log
```

## Common console commands (all work via the broadcast syntax)

```bash
# Performance
stat fps / stat unit / stat gpu / stat memory / stat none

# Screen messages
DisableAllScreenMessages / EnableAllScreenMessages

# Rendering CVars
r.ShadowQuality 0 / r.MobileContentScaleFactor 1.5 / r.ScreenPercentage 50
sg.PostProcessQuality 0 / sg.EffectsQuality 0
r.MobileMSAA 1 / r.MobileHDR 0 / r.ViewDistanceScale 0.5
```

## Project console / cheat commands

Registered as `UFUNCTION(Exec)` on `UPlatformGameInstance`:

| Command | Purpose |
|---------|---------|
| `ExecDoString <lua>` | Run Lua |
| `StartMoveRecord` / `StopMoveRecord` | Record player movement |
| `StartPlayerAutoMove` | Auto-move |
| `ChangeTime <int>` / `ChangeTimeScale <int>` | Time control |
| `ListAllNPCMemoryInfo` | NPC memory dump |

Cheat commands (via `UCheatManager`):

| Command | Purpose |
|---------|---------|
| `ToggleCameraCollision` | — |
| `GhostMode <speed>` | Ghost mode |
| `HideMesh` | Hide player mesh |
| `spawn_no_ai <npc_id>` | Spawn NPC without AI |
| `cast_skill <actor_id> <skill_id>` | Cast skill |
| `del_no_ai <actor_id>` | Delete spawned NPC |
| `RecordXfm` / `RestoreXfm` | Save/restore player transform |
| `PlayAnim <name>` / `StopAnim` | Animation control |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `adb: command not found` | Install Android SDK platform-tools, add to PATH |
| `device unauthorized` | Accept USB debugging prompt on device |
| `device offline` | `adb kill-server && adb start-server`, reconnect USB |
| `Broadcast completed: result=0` but no effect | Game not running, or Shipping build (no receiver) |
| `ExecDoString` no RetVal line | `Log LogTemp verbose` + `Log Log verbose`; verify with canary |
| RetVal intermittent | `adb logcat -G 16M`; always `adb logcat -c` before broadcast |
| Command timeout | Device busy (PSO compile, loading); retry |
| Chinese characters garbled in Lua returns | Console encoding (Windows) — try `chcp 65001` or use `devbridge` (handles UTF-8 explicitly) |

---

For the first-class workflow, see `../SKILL.md` and use `devbridge`.
