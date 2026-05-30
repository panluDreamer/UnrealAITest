# Level Designer — Known Failures & Workarounds

> Verified failure cases from real sessions. Check this BEFORE writing any exec_python script.
> Append new discoveries at the bottom.

---

## 1. EditorLevelLibrary Does Not Exist (UE 4.26)

**Symptom**: `AttributeError: module 'unreal' has no attribute 'EditorLevelLibrary'`

**Cause**: `EditorLevelLibrary` requires the "Editor Scripting Utilities" plugin, which is not enabled by default in UE 4.26.

**Workaround**: Use `unreal.GameplayStatics` + `unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()` instead:
```python
# DON'T: unreal.EditorLevelLibrary.get_editor_world()
# DO:
world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.StaticMeshActor)
```

---

## 2. ACTOR ADD Console Command Crashes Editor

**Symptom**: Editor hangs or crashes when executing `ACTOR ADD` via `execute_console_command`.

**Cause**: `ACTOR ADD` attempts interactive viewport placement, which conflicts with the Python/MCP execution context.

**Workaround**: Use `BeginDeferredActorSpawnFromClass` + `FinishSpawningActor`:
```python
# DON'T: unreal.SystemLibrary.execute_console_command(world, "ACTOR ADD ...")
# DO:
gs = unreal.GameplayStatics.get_default_object()
actor = gs.call_method('BeginDeferredActorSpawnFromClass',
    args=(world, unreal.StaticMeshActor.static_class(), transform,
          unreal.SpawnActorCollisionHandlingMethod.ALWAYS_SPAWN, None))
gs.call_method('FinishSpawningActor', args=(actor, transform))
```

---

## 3. Spawning Tick Actors Directly Causes Crash

**Symptom**: Editor crashes when spawning `PointLight`, `DirectionalLight`, `SkyLight`, `CameraActor` via direct Python call.

**Cause**: These actors register TickFunctions during construction, which conflicts with the MCP synchronous execution context (Tick cycle collision).

**Workaround**: Use deferred execution:
```python
def _deferred(dt):
    unreal.unregister_slate_post_tick_callback(h)
    # Spawn the Tick actor here
    gs = unreal.GameplayStatics.get_default_object()
    actor = gs.call_method('BeginDeferredActorSpawnFromClass',
        args=(world, unreal.PointLight.static_class(), transform,
              unreal.SpawnActorCollisionHandlingMethod.ALWAYS_SPAWN, None))
    gs.call_method('FinishSpawningActor', args=(actor, transform))
h = unreal.register_slate_post_tick_callback(_deferred)
```

> `StaticMeshActor` does NOT have TickFunction and can be spawned directly.

---

## 4. find_object() Cannot Access PIE World

**Symptom**: `unreal.find_object()` returns `None` for actors that visibly exist in PIE.

**Cause**: `find_object()` / `load_object()` only search the persistent editor world package. PIE creates a separate transient world that is not accessible via these functions.

**Workaround**: Do NOT try to find PIE actors via Python. Either:
- Operate on editor world actors before entering PIE
- Use `GameplayStatics.get_all_actors_of_class()` with the editor world context

---

## 5. Modifying Editor Actors During PIE Causes Tick Crash

**Symptom**: Editor crashes with Tick-related assertion when modifying editor world actor properties while PIE is running.

**Cause**: PIE references editor world actors. Modifying them during PIE creates state inconsistencies in the Tick pipeline.

**Workaround**: Always exit PIE before modifying actors via Python. Check PIE state:
```python
# There's no reliable Python API to check PIE state in 4.26.
# Best practice: inform the user to exit PIE before running modification scripts.
```

---

## 6. Rotator Positional Argument Order is Unintuitive

**Symptom**: Actor faces wrong direction after setting rotation.

**Cause**: `unreal.Rotator(a, b, c)` positional order is `(roll, pitch, yaw)`, NOT `(pitch, yaw, roll)`.

**Workaround**: ALWAYS use keyword arguments:
```python
# DON'T: unreal.Rotator(0, 90, 0)  — this sets roll=0, pitch=90, yaw=0
# DO:    unreal.Rotator(pitch=0, yaw=90, roll=0)
```

---

## 7. save_packages Requires Package (Outer), Not Asset

**Symptom**: `save_packages` silently fails or throws when passed an asset UObject.

**Cause**: `EditorLoadingAndSavingUtils.save_packages()` expects `UPackage` objects, not the assets themselves.

**Workaround**: Use `get_outer()` to get the package:
```python
asset = unreal.load_asset("/Game/Path/To/Asset")
unreal.EditorLoadingAndSavingUtils.save_packages([asset.get_outer()], only_dirty=True)
```
