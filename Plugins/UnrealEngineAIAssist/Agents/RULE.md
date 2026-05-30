# UE Editor Agent — Shared Rules

> All Agents under `Agents/` MUST follow these rules.
> Loaded by each Agent's SKILL.md on activation.

---

## Mandatory Pre-Read (BEFORE First exec_python)

Before your **first** `exec_python` call in any task, you MUST:

1. **Read** `Skills/ue-python-script/references/common-operations.md`
   - Pay special attention to the `## ⛔ Known Failures & Crashes` section
   - Pay special attention to the `## ⚠️ Deferred Execution` section
2. **Read** your Agent's `references/known-failures.md` (if it exists)
3. If the Plan or task references specific API class names, **verify** them in
   `catalog_index.json` before assuming they exist in the Python binding

> **Why?** UE Python bindings differ significantly from C++ API.
> "Looking like you know" is the #1 cause of wasted MCP calls.
> In one session, 69% of MCP calls (~38/55) were wasted because the AI
> skipped discovery and went straight to exec_python with incorrect API assumptions.

---

## Progressive Disclosure Path (ALWAYS Start from L0)

```
L0: common-operations.md          ← covers 80% of tasks, read FIRST
L1: catalog_index.json             ← find the right class/category
L2: classes/{ClassName}.json       ← get exact function signatures
L3: describe_object / reflect      ← live introspection (last resort)
```

**Even if you believe you know the API**, start from L0 and verify.

- If L0 covers your need → use it directly, skip L1–L3
- If L0 doesn't cover it → proceed to L1, then L2, then L3
- **Never jump to L3** (describe_object) without checking L0–L2 first

---

## API Feasibility Batch Validation Template

When implementing a Plan that references multiple APIs, validate them ALL
in a single exec_python call before writing the real script:

```python
import unreal

apis = {
    "EditorLevelLibrary": lambda: unreal.EditorLevelLibrary,
    "GameplayStatics.get_all_actors_of_class": lambda: hasattr(unreal.GameplayStatics, 'get_all_actors_of_class'),
    "StaticMeshActor.static_mesh_component": lambda: hasattr(unreal.StaticMeshActor, 'static_mesh_component'),
    # Add all APIs referenced in the Plan
}

for name, check in apis.items():
    try:
        result = check()
        print(f"  OK  {name}: {result}")
    except Exception as e:
        print(f"  FAIL {name}: {e}")
```

> Run this ONCE before writing the real implementation script.
> Adjust your approach based on which APIs are actually available.

---

## Script History (Optional)

Successful `exec_python` calls are automatically saved to
`mcp_output/script_history/` with a summary header.

- **Before starting a new task**, if `mcp_output/script_history/index.json` exists,
  scan the recent entries' `summary` fields for scripts related to your current task.
- Particularly useful for **project-specific context** (asset paths, BP structures,
  level layouts) that was discovered in a previous session.
- Use `Read` on a history file to see the full code + what it returned.

---

## Safety Rules

1. **No PIE mutation**: Do NOT modify editor world actor properties while PIE (Play-In-Editor) is running — causes Tick crashes
2. **No ACTOR ADD console command**: `ACTOR ADD` crashes the editor — use `BeginDeferredActorSpawnFromClass` instead
3. **Rotator keyword args**: Always use `unreal.Rotator(pitch=0, yaw=90, roll=0)` — positional arg order is `(roll, pitch, yaw)` which is unintuitive
4. **Deferred spawn for Tick actors**: `PointLight`, `DirectionalLight`, `SkyLight`, `CameraActor`, and any Actor with TickFunction must be spawned via `register_slate_post_tick_callback`
5. **find_object() scope**: `unreal.find_object()` / `unreal.load_object()` cannot access PIE world objects — only persistent editor world
6. **Save before test**: Always save modified assets before entering PIE to avoid losing changes
7. **One script, one task**: Prefer a single comprehensive script over multiple small exec_python calls — each MCP round-trip is expensive

---

## Error Recovery

If an exec_python call fails:
1. **Read the error message carefully** — UE Python errors often contain the correct API name
2. **Check common-operations.md** for the correct pattern
3. **Check your Agent's known-failures.md** for known workarounds
4. **Do NOT retry the same code** — investigate and fix the root cause first
5. If the API doesn't exist, fall back to the discovery path (L1 → L2 → L3)
