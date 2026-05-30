# Blueprint Graph Construction Templates

> Templates for building Blueprint graphs via Python exec_python.
> BlueprintEdGraphUtils is built into the UnrealEngineAIAssist plugin — no engine patches required.
> All scripts are self-contained — copy-paste into exec_python.

---

## Prerequisites

### Check BlueprintEdGraphUtils Availability

```python
import unreal

# Verify the utility class is available (built into UnrealEngineAIAssist plugin)
try:
    utils = unreal.BlueprintEdGraphUtils
    print("BlueprintEdGraphUtils available")
    # List available methods
    for attr in dir(utils):
        if not attr.startswith('_'):
            print(f"  {attr}")
except AttributeError:
    print("ERROR: BlueprintEdGraphUtils not available.")
    print("Ensure UnrealEngineAIAssist plugin is enabled and the editor is rebuilt.")
```

### K2Node Class Discovery

```python
import unreal

# Common K2Node classes — verify availability
k2_classes = [
    "/Script/BlueprintGraph.K2Node_CallFunction",
    "/Script/BlueprintGraph.K2Node_Event",
    "/Script/BlueprintGraph.K2Node_CustomEvent",
    "/Script/BlueprintGraph.K2Node_IfThenElse",
    "/Script/BlueprintGraph.K2Node_FunctionEntry",
    "/Script/BlueprintGraph.K2Node_FunctionResult",
    "/Script/BlueprintGraph.K2Node_VariableGet",
    "/Script/BlueprintGraph.K2Node_VariableSet",
    "/Script/BlueprintGraph.K2Node_DynamicCast",
    "/Script/BlueprintGraph.K2Node_SpawnActorFromClass",
]

for path in k2_classes:
    cls = unreal.find_object(None, path)
    name = path.split('.')[-1]
    print(f"  {'OK' if cls else 'MISSING':7s}  {name}")
```

---

## BlueprintEdGraphUtils API Reference

| Function | Signature | Description |
|----------|-----------|-------------|
| `add_node` | `(graph, node_class, x, y) → node` | Add a K2Node to the graph |
| `connect_pins` | `(graph, src_node, src_pin, dst_node, dst_pin) → bool` | Connect two pins by name |
| `set_call_function_target` | `(node, function_name) → bool` | Set the target function for a K2Node_CallFunction |
| `compile_blueprint` | `(blueprint) → bool` | Compile a Blueprint |
| `describe_pins` | `(node) → str` | List all pins on a node (name, type, direction) |
| `find_event_node` | `(graph, event_name) → node` | Find an event node by name |

---

## Complete BP Graph Construction Template

```python
import unreal

# === 1. Load Blueprint ===
bp_path = "/Game/Blueprints/BP_MyActor"
bp = unreal.load_asset(bp_path)
if not bp:
    print(f"ERROR: Blueprint not found at {bp_path}")
else:
    utils = unreal.BlueprintEdGraphUtils

    # === 2. Get the Event Graph ===
    # UbergraphPages[0] is typically the main EventGraph
    graphs = bp.get_editor_property("ubergraph_pages")
    if not graphs:
        print("ERROR: No UbergraphPages found")
    else:
        graph = graphs[0]
        print(f"Graph: {graph.get_name()}")

        # === 3. Find or Create Event Node ===
        # Find existing BeginPlay event
        begin_play = utils.find_event_node(graph, "ReceiveBeginPlay")
        if begin_play:
            print(f"Found BeginPlay node")
        else:
            print("BeginPlay not found — may need to add it")

        # === 4. Add a CallFunction Node ===
        call_node = utils.add_node(
            graph,
            unreal.find_object(None, "/Script/BlueprintGraph.K2Node_CallFunction"),
            300, 0  # x, y position in graph
        )
        utils.set_call_function_target(call_node, "PrintString")

        # === 5. Inspect Pins ===
        pin_info = utils.describe_pins(call_node)
        print(f"Pins on CallFunction node:\n{pin_info}")

        # === 6. Connect Pins ===
        # Connect BeginPlay exec → CallFunction exec
        if begin_play:
            success = utils.connect_pins(graph, begin_play, "then", call_node, "execute")
            print(f"Connected BeginPlay → PrintString: {success}")

        # === 7. Set Pin Default Values ===
        # For PrintString's "InString" pin
        # Note: use node.call_method if SetPinDefaultValue is available
        # Pin default format depends on the type:
        #   - String: "Hello World"
        #   - FRotator: "P=0.0,Y=90.0,R=0.0"  (Pitch, Yaw, Roll)
        #   - FVector: "X=1.0,Y=2.0,Z=3.0"
        #   - Bool: "true" / "false"
        #   - Enum: "EnumValue"

        # === 8. Compile ===
        compile_ok = utils.compile_blueprint(bp)
        print(f"Compile: {'OK' if compile_ok else 'FAILED'}")

        # === 9. Save ===
        unreal.EditorLoadingAndSavingUtils.save_packages(
            [bp.get_outer()], only_dirty=True
        )
        print("Saved.")
```

---

## Pin Default Value Formats

| Type | Format | Example |
|------|--------|---------|
| `String` | Plain text | `"Hello World"` |
| `Int` | Integer | `"42"` |
| `Float` | Decimal | `"3.14"` |
| `Bool` | Lowercase | `"true"` or `"false"` |
| `FVector` | Named components | `"X=1.0,Y=2.0,Z=3.0"` |
| `FRotator` | Named components | `"P=0.0,Y=90.0,R=0.0"` |
| `FLinearColor` | Named components | `"R=1.0,G=0.0,B=0.0,A=1.0"` |
| `Enum` | Enum value name | `"ECollisionChannel::ECC_WorldStatic"` |
| `Object Reference` | Full path | `"/Game/Path/To/Asset.Asset"` |
| `Class Reference` | Class path | `"/Script/Engine.StaticMeshActor"` |

> **Critical**: FRotator text format uses `P,Y,R` (Pitch, Yaw, Roll) — different from
> the `unreal.Rotator` constructor which is `(roll, pitch, yaw)` positionally.

---

## Add Overlap Event Handler

```python
import unreal

bp_path = "/Game/Blueprints/BP_TriggerBox"
bp = unreal.load_asset(bp_path)
utils = unreal.BlueprintEdGraphUtils

graphs = bp.get_editor_property("ubergraph_pages")
graph = graphs[0]

# Find or create ActorBeginOverlap event
overlap_event = utils.find_event_node(graph, "ReceiveActorBeginOverlap")
if not overlap_event:
    # Add the event node
    overlap_event = utils.add_node(
        graph,
        unreal.find_object(None, "/Script/BlueprintGraph.K2Node_Event"),
        0, 200
    )
    # Configure it for ActorBeginOverlap
    # (implementation depends on available APIs — check describe_pins)

# Add PrintString to log the overlap
call_node = utils.add_node(
    graph,
    unreal.find_object(None, "/Script/BlueprintGraph.K2Node_CallFunction"),
    300, 200
)
utils.set_call_function_target(call_node, "PrintString")

if overlap_event:
    utils.connect_pins(graph, overlap_event, "then", call_node, "execute")

utils.compile_blueprint(bp)
unreal.EditorLoadingAndSavingUtils.save_packages([bp.get_outer()], only_dirty=True)
print("Done: Added overlap event handler")
```

---

## Known Gotchas

1. **K2Node classes are in `/Script/BlueprintGraph.*`**, not `/Script/Engine.*`
2. **Pin names are case-sensitive** — use `describe_pins()` to get exact names
3. **Compile after every change** — uncommitted graph changes may be lost on editor restart
4. **FRotator text format** is `P=,Y=,R=` — NOT the same order as the constructor
5. **Self pin**: For member function calls, the "self" pin must be connected to provide the target object
6. **SCS parent-child: 用 `add_child_node`，不要用 `set_parent`** — `set_parent()` 只更新元数据（`ParentComponentOrVariableName`），不更新 `ChildNodes` 树结构，编译时 `ValidateSceneRootNodes` 检测到不一致会触发 ensure 失败。`add_child_node()` 是原子操作，同时更新两者：
   ```python
   # ❌ 错误：只更新元数据，树结构未同步
   sm_node.set_parent(root_node)

   # ✅ 正确：原子更新元数据 + ChildNodes 树
   root_node.add_child_node(sm_node)

   # 如需重新挂父，先移除再添加
   old_parent.remove_child_node(sm_node)
   new_parent.add_child_node(sm_node)
   ```
