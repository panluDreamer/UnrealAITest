# Project-specific ADB protocol reference

> **For day-to-day workflows use `devbridge` — see `../SKILL.md`.**
> For raw ADB command syntax when `devbridge` is unavailable, see `adb-raw-fallback.md`.
> This file documents the **protocol-level invariants** of the game runtime:
> what `ExecDoString` does, what RetVal lines look like, which categories are
> silent by default. Tool-agnostic — true for `devbridge`, raw `adb`, or any
> future wrapper.

---

## The BroadcastReceiver contract

UE4 Android builds (non-Shipping) register a `BroadcastReceiver` for
`android.intent.action.RUN`. The `cmd` extra is piped through
`GEngine->Exec()`.

```
adb shell "am broadcast -a android.intent.action.RUN -e cmd '<command>'"
```

Anything `GEngine->Exec()` accepts is fair game:
- CVars: `r.ShadowQuality 0`
- `stat` commands: `stat fps`
- `UFUNCTION(Exec)`: `ExecDoString`, `GhostMode`, `spawn_no_ai`
- `showflag` / `show`
- The `Log <Category> <Level>` command (used for category enablement)

Broadcast return is **fire-and-forget**. You get `Broadcast completed: result=0`
at the adb layer, but not the command's output — that's in logcat.

Stripped in Shipping builds — the receiver is excluded from the manifest.

---

## ExecDoString semantics

`ExecDoString` is a `UFUNCTION(Exec)` on `UPlatformGameInstance`. Signature:

```cpp
UFUNCTION(Exec) void ExecDoString(const FString& Code);
```

The UE console parser passes **the entire rest of the line** as a single
`FString` argument. So there's no internal tokenisation — you don't need to
worry about Lua keywords colliding with shell word-splitting (but do mind
shell-level quoting).

Internally, `ExecDoString` calls:
```
UnLua::CallTableFunc(L, "AutoTestModule", "DoString", Code);
```
which does `load(Code)()` under `xpcall`. The result (or the error) is logged
to `LogTemp`:

```
[PlatformGameInstance]ExecDoString RetVal:<stringified-result>
```

On xpcall failure the RetVal begins with `Error:[Error]`, followed by a stack
trace in adjacent log lines. Parse as a failure, not a success.

---

## Log category suppression (game default)

By default, game builds silence:

- `LogTemp` (where ExecDoString writes its RetVal)
- `Log` (generic script log)

Without enablement, `ExecDoString` RetVal lines **do not reach logcat at all**.
Every game session needs a one-time enablement:

```
Log LogTemp verbose
Log Log verbose
```

(as console commands — so broadcast them.)

Levels: `off` | `error` | `warning` | `display` | `log` | `verbose` | `all`.
Use `verbose` for debugging; `display` if you want less noise.

**`devbridge preflight` automates this and caches the result per-device for 24h.**
When using raw adb, remember to re-enable after every game restart.

---

## RetVal line format

Example:
```
04-21 12:18:13.551 17440 17590 D UE4 : [2026.04.21-12.18.13:551][206]LogTemp: [PlatformGameInstance]ExecDoString RetVal:2
```

Fields:
- `04-21 12:18:13.551` — logcat timestamp
- `17440 17590` — PID / TID (the first is the game process, cache it for `--pid=`)
- `D UE4` — priority (D/V/I/W/E) and tag (always `UE4` for UE output)
- `[2026.04.21-12.18.13:551][206]` — UE4 engine timestamp + frame number
- `LogTemp:` — the log category (must be enabled, see above)
- `[PlatformGameInstance]` — the class prefix
- `ExecDoString RetVal:` — the literal marker
- `2` — the stringified return value (everything after the colon to EOL)

UE4 often logs the same line twice back-to-back (dispatcher idiosyncrasy);
parsers should de-duplicate adjacent identical lines.

---

## Common UE console commands available via broadcast

Performance stats:
```
stat fps / stat unit / stat gpu / stat memory
stat scenerendering / stat initviews / stat particles / stat streaming
stat none   # disable all
```

Rendering CVars (typical usage):
```
r.ShadowQuality 0..3
r.MobileContentScaleFactor <float>
r.ScreenPercentage <0-100>
sg.PostProcessQuality 0..3
sg.EffectsQuality 0..3
r.MobileMSAA 0/1/2/4
r.MobileHDR 0/1
r.ViewDistanceScale <float>
```

Display:
```
DisableAllScreenMessages / EnableAllScreenMessages
showflag.PostProcessing 0/1
show collision
```

## Project-specific commands

Registered as `UFUNCTION(Exec)` on `UPlatformGameInstance`:

| Command | Description |
|---------|-------------|
| `ExecDoString <lua_code>` | Execute Lua (see above) |
| `StartMoveRecord` / `StopMoveRecord` | Record player movement |
| `StartPlayerAutoMove` | Auto-move player |
| `ChangeTime <int>` | Change in-game time |
| `ChangeTimeScale <int>` | Change time scale |
| `ListAllNPCMemoryInfo` | List NPC memory info |

Cheat commands (via `UCheatManager`):

| Command | Description |
|---------|-------------|
| `ToggleCameraCollision` | Toggle camera collision |
| `GhostMode <speed>` | Ghost mode |
| `HideMesh` | Hide player mesh |
| `spawn_no_ai <npc_id>` | Spawn NPC without AI |
| `cast_skill <actor_id> <skill_id>` | Cast skill |
| `del_no_ai <actor_id>` | Delete spawned NPC |
| `RecordXfm` / `RestoreXfm` | Save/restore player transform |
| `PlayAnim <name>` / `StopAnim` | Animation control |

---

## Where this knowledge is used

- `devbridge`'s `preflight`/`lua`/`logcat` implementations encode these invariants
  (see [ThirdParty/DevBridgeCli/](../../../ThirdParty/DevBridgeCli/))
- `references/adb-raw-fallback.md` — uses these as a fallback when devbridge isn't available
- `references/debug-module.md` — extensive catalogue of the in-game Debug panel (GM items, module commands)
- `references/lua-patterns.md` — common one-liners for `ExecDoString`
