# Lua Debug Patterns for Device Execution

Common Lua one-liners for on-device debugging via `ExecDoString`.
Sourced from project debug tabs under `Content/Script/Modules/System/Debug/Tabs/`.

## Memory & GC

```lua
-- Check Lua memory usage (KB)
return collectgarbage("count")

-- Force Lua garbage collection
collectgarbage("collect"); return "gc done"

-- Force UE garbage collection (blocking)
UE4.UGameStatics.ForceGarbageCollection(true); return "ue gc done"

-- Remove pending-kill objects
UE4.UGameStatics.RemovePendingKillObject(); return "done"
```

## Rendering Control

```lua
-- Disable world rendering (show only UI)
UE4Helper.SetEnableWorldRendering(false); return "world rendering off"

-- Enable world rendering
UE4Helper.SetEnableWorldRendering(true); return "world rendering on"

-- Enable UI-only rendering
UE4.UTUIStatics.SetEnableUIOnlyRendering(true); return "ui only on"

-- Disable UI-only rendering
UE4.UTUIStatics.SetEnableUIOnlyRendering(false); return "ui only off"
```

## Profiling

```lua
-- Enable Lua profiling
UE.UGameStatics.EnableLuaProfile(true); return "lua profile on"

-- Disable Lua profiling
UE.UGameStatics.EnableLuaProfile(false); return "lua profile off"

-- Enable Lua C++ profiling
UE.UGameStatics.EnableLuaCPPProfile(true); return "cpp profile on"

-- Disable Lua C++ profiling
UE.UGameStatics.EnableLuaCPPProfile(false); return "cpp profile off"

-- Print Lua statistics
-- (use console command instead: lua.statistics.print)
```

## Logging

```lua
-- Set log level to fatal only (suppress all other logs)
Log.SetLogLevel(Log.LOG_LEVEL.ELogFatal); UE4.UGameStatics.SetLogLevel(0); return "log fatal only"

-- Show object references
UE4.UGameStatics.ShowRefObject(false); return "showing refs"

-- Show object references by type
UE4.UGameStatics.ShowRefObjectByType(); return "showing refs by type"
```

## Module & Panel System

```lua
-- Get a module instance
local m = ModuleManager:GetModule("LoginModule"); return tostring(m)

-- Execute a module command
ModuleManager:DoCmd(_G.DebugModuleCmd.Open); return "debug panel opened"

-- Deactivate a module
ModuleManager:DeactiveModule("LoginModule"); return "deactivated"
```

## Object Inspection

```lua
-- Get GameInstance name
return UE4.UPlatformGameInstance.GetInstance():GetName()

-- Check if ModuleManager exists
return tostring(_G.ModuleManager)

-- List loaded Lua modules
local count=0; for k,v in pairs(package.loaded) do count=count+1 end; return "loaded modules: "..count

-- Print Lua memory (alternative)
return string.format("%.1f KB", collectgarbage("count"))
```

## Global Debug Flags

```lua
-- Enable auto GC every tick
_G.StartAutoGCByTick = 1; return "auto gc on"

-- Disable auto GC
_G.StartAutoGCByTick = nil; return "auto gc off"

-- Force synchronous image loading
_G.bForceImageLoadAsync = false; return "sync load"

-- Force async image loading
_G.bForceImageLoadAsync = true; return "async load"

-- Don't unload UMG assets (debug only)
_G.DonntUnloadUmgAsset = true; return "umg keep"
```

## Asset Operations

```lua
-- Load an asset for debug (no streaming)
local cls = _G.ResourceManager:LoadForDebugOnly("/Game/ArtRes/SomePath"); return tostring(cls)

-- Release a skill effect
UE4.USkillRecordLibrary.ReleaseSkill("/Game/ArtRes/Effects/G6Skill/Jineng/708002"); return "released"
```

## Debugger Control

```lua
-- Enable Lua debugger on port 5067
UE.UGameStatics.EnableLuaDebugger(5067); return "debugger on :5067"

-- Disable Lua debugger
UE.UGameStatics.EnableLuaDebugger(0); return "debugger off"
```

## Tips

1. **Always return a value** — append `; return "done"` so you can verify execution via logcat
2. **Read results from logcat**: `adb logcat -d -t 50 | grep "ExecDoString RetVal"`
3. **Multi-line scripts**: Use semicolons to separate statements on one line
4. **Complex scripts**: Push a .lua file via `adb push` then `ExecDoString dofile("/sdcard/script.lua")`

## Finding More Patterns

Project Lua debug source files (derive path from `plugin.config.json`):
```
{project_root}/Content/Script/Modules/System/Debug/Tabs/
  DebugTabLua.lua      -- Memory, GC, profiling, module debugging
  DebugTabUI.lua       -- UI panel and widget debugging
  DebugTabBattle.lua   -- Battle system, skills, combat
  DebugTabNPC.lua      -- NPC spawning, behavior
  DebugTabScene.lua    -- Level, environment, scene
  DebugTabNetwork.lua  -- Network, protocol
  DebugTabAvatar.lua   -- Avatar system
  ... (90+ debug tab files)
```

Read these files to discover project-specific debug commands and Lua API patterns.
