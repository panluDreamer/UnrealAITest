# Common UE Editor Operations — Quick Reference

> 高频操作速查。AI 应优先查阅此文件，不够再走 catalog 3-level 发现流程。
> 所有代码均可直接传入 `exec_python`。
>
> **兼容性**: UE 4.26+，不依赖 Editor Scripting Utilities 插件。
> 若目标项目启用了该插件，`EditorLevelLibrary` / `EditorAssetLibrary` 也可用，
> 但本文件使用的 API 在任何配置下都能工作。

---

## ⚠️ 延迟执行（必读）

MCP 同步上下文中**直接调用以下操作会崩溃**（Tick 周期冲突）：
- 地图加载/切换（`load_map`, `new_blank_map`, `new_map_from_template` 等）
- Spawn 带 TickFunction 的 Actor（`DirectionalLight`, `PointLight`, `SkyLight`, `CameraActor` 等）

**解法**：用 `register_slate_post_tick_callback` 延迟到下一帧：
```python
def _deferred(dt):
    unreal.unregister_slate_post_tick_callback(h)
    # 危险操作放这里
h = unreal.register_slate_post_tick_callback(_deferred)
```
> `StaticMeshActor` 无 TickFunction，可直接 spawn。
>
> ⚠️ `unreal.Rotator` 位置参数顺序为 **(roll, pitch, yaw)**，不是 (pitch, yaw, roll)。
> **务必使用关键字参数**：`unreal.Rotator(pitch=0, yaw=90, roll=0)`。

---

## World & Level

### 获取当前 World
```python
world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
```

### 获取当前关卡名称
```python
world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
level_name = world.get_name()
print(f"Current level: {level_name}")
```

### 获取当前关卡路径（Map 路径）
```python
world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
map_path = world.get_path_name()
print(f"Map path: {map_path}")
```

### 获取所有 Actor
```python
world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)
print(f"Total actors: {len(actors)}")
for a in actors:
    print(f"  {a.get_name()} ({a.get_class().get_name()})")
```

### 按类型查找 Actor
```python
# 替换 unreal.StaticMeshActor 为目标类型
world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.StaticMeshActor)
print(f"Found {len(actors)} actors")
```

### 按标签查找 Actor
```python
world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
actors = unreal.GameplayStatics.get_all_actors_with_tag(world, "MyTag")
print(f"Found {len(actors)} actors with tag")
```

### 获取 Streaming Level
```python
world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
streaming = unreal.GameplayStatics.get_streaming_level(world, "/Game/Maps/SubLevel")
print(f"Streaming level loaded: {streaming is not None}")
```

---

## Selection

### 获取选中的 Actor（视口中）
```python
actors = unreal.EditorUtilityLibrary.get_selection_set()
for a in actors:
    print(f"Selected: {a.get_name()} ({a.get_class().get_name()})")
```

### 获取选中的 Asset（Content Browser 中）
```python
assets = unreal.EditorUtilityLibrary.get_selected_assets()
for asset in assets:
    print(f"Selected asset: {asset.get_name()} ({asset.get_class().get_name()})")
```
> 轻量版（不加载 UObject）：`unreal.EditorUtilityLibrary.get_selected_asset_data()`

### 设置 Actor 选中状态
```python
# 通过 GEditor 或 exec_python 执行选中操作
# 目前无稳定的纯 Python API，建议用 describe_object 查询当前版本可用方法
```

---

## Asset Management

### 加载资产
```python
asset = unreal.load_asset("/Game/Path/To/Asset")
print(f"Loaded: {asset.get_name()}" if asset else "Asset not found")
```

### 检查资产是否存在
```python
registry = unreal.AssetRegistryHelpers.get_asset_registry()
results = registry.get_assets_by_package_name("/Game/Path/To/Asset")
exists = len(results) > 0
print(f"Exists: {exists}")
```

### 列出目录下所有资产
```python
registry = unreal.AssetRegistryHelpers.get_asset_registry()
assets = registry.get_assets_by_path("/Game/SomeFolder", recursive=True)
for a in assets:
    print(f"{a.package_name} ({a.asset_class})")
```

### 按类型列出资产（如找所有 DataTable）
```python
registry = unreal.AssetRegistryHelpers.get_asset_registry()
assets = registry.get_assets_by_class("DataTable")
for a in assets:
    print(f"{a.package_name}")
```

### 保存资产（加载后标脏再保存）
```python
asset = unreal.load_asset("/Game/Path/To/Asset")
if asset:
    unreal.EditorLoadingAndSavingUtils.save_packages([asset.get_outer()], only_dirty=True)
```

### 保存所有脏资产
```python
unreal.EditorLoadingAndSavingUtils.save_dirty_packages(save_map_packages=True, save_content_packages=True)
```

### 复制资产
```python
source_asset = unreal.load_asset("/Game/Path/To/SourceAsset")
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
# 签名: duplicate_asset(new_name, new_package_path, original_object)
new_asset = asset_tools.duplicate_asset("DestAssetName", "/Game/Dest/Path", source_asset)
print(f"Duplicated: {new_asset.get_name()}" if new_asset else "Duplicate failed")
```

### 重命名/移动资产
```python
asset = unreal.load_asset("/Game/OldPath/Asset")
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
# rename_assets 接受 AssetRenameData 数组
rename_data = unreal.AssetRenameData(asset=asset, new_package_path="/Game/NewPath", new_name="NewName")
asset_tools.rename_assets([rename_data])
```

### 删除资产
```python
# ⚠️ destructive — 需用户确认
# 注意: ObjectTools / EditorAssetLibrary 在部分引擎版本未暴露给 Python
# 如果不可用，需要通过文件系统删除 .uasset 文件（不推荐，内存引用不会清除）
import unreal
asset = unreal.load_asset("/Game/Path/To/Asset")
if asset:
    try:
        unreal.ObjectTools.delete_assets([asset])
    except AttributeError:
        print("ObjectTools not available — use EditorAssetLibrary or manual file deletion")
```

### 查找资产引用
```python
registry = unreal.AssetRegistryHelpers.get_asset_registry()
dep_options = unreal.AssetRegistryDependencyOptions(
    include_soft_package_references=True,
    include_hard_package_references=True,
    include_searchable_names=False,
    include_soft_management_references=False
)
referencers = registry.get_referencers("/Game/Path/To/Asset", dep_options)
for r in referencers:
    print(f"Referenced by: {r}")
```

---

## Actor & Transform

### Spawn Actor
```python
world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
gs = unreal.GameplayStatics.get_default_object()
transform = unreal.Transform(
    location=unreal.Vector(0, 0, 100),
    rotation=unreal.Rotator(pitch=0, yaw=90, roll=0),
    scale=unreal.Vector(1, 1, 1)
)
# Begin → 配置 → Finish（通过 call_method，Python 层未直接暴露）
actor = gs.call_method('BeginDeferredActorSpawnFromClass',
    args=(world, unreal.StaticMeshActor.static_class(), transform,
          unreal.SpawnActorCollisionHandlingMethod.ALWAYS_SPAWN, None))
actor.static_mesh_component.set_static_mesh(unreal.load_asset("/Game/Path/To/Mesh"))
gs.call_method('FinishSpawningActor', args=(actor, transform))
```
> ⚠️ `PointLight`、`DirectionalLight`、`SkyLight`、`CameraActor` 等带 TickFunction
> 的 Actor 必须通过延迟执行 spawn（见上方「延迟执行」）。`StaticMeshActor` 可直接 spawn。

### 获取 Actor 位置/旋转/缩放
```python
transform = actor.get_actor_transform()
loc = transform.translation
rot = transform.rotation.rotator()
scale = transform.scale3d
print(f"Location: {loc}\nRotation: {rot}\nScale: {scale}")
```

### 设置 Actor 位置
```python
actor.set_actor_location(unreal.Vector(100, 200, 300), sweep=False, teleport=True)
```

### 设置 Actor 旋转
```python
actor.set_actor_rotation(unreal.Rotator(pitch=0, yaw=90, roll=0), teleport_physics=True)
```

### 设置 Actor 缩放
```python
actor.set_actor_scale3d(unreal.Vector(2, 2, 2))
```

### 获取 Actor 的所有组件
```python
components = actor.get_components_by_class(unreal.ActorComponent)
for c in components:
    print(f"  {c.get_name()} ({c.get_class().get_name()})")
```

### 通过名称查找 Actor
```python
world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)
target = next((a for a in actors if a.get_name() == "MyActorName"), None)
print(f"Found: {target}" if target else "Not found")
```

### 删除 Actor
```python
# ⚠️ destructive — 需用户确认
actor.destroy_actor()
```

---

## Material

### 获取 Material Instance Scalar 参数
```python
mi = unreal.load_asset("/Game/Materials/MI_Example")
value = unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(mi, "Metallic")
print(f"Metallic = {value}")
```

### 设置 Material Instance Scalar 参数
```python
mi = unreal.load_asset("/Game/Materials/MI_Example")
unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(mi, "Metallic", 0.8)
```

### 获取/设置 Material Instance Vector 参数
```python
mi = unreal.load_asset("/Game/Materials/MI_Example")
# Get
color = unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(mi, "BaseColor")
print(f"BaseColor = {color}")
# Set
new_color = unreal.LinearColor(r=1.0, g=0.0, b=0.0, a=1.0)
unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(mi, "BaseColor", new_color)
```

### 设置 Material Instance Texture 参数
```python
mi = unreal.load_asset("/Game/Materials/MI_Example")
tex = unreal.load_asset("/Game/Textures/T_MyTexture")
unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(mi, "DiffuseTexture", tex)
```

### 创建 Material Expression 节点
```python
mat = unreal.load_asset("/Game/Materials/M_Example")
node = unreal.MaterialEditingLibrary.create_material_expression(
    mat,
    unreal.MaterialExpressionTextureSample,
    node_pos_x=-300,
    node_pos_y=0
)
```

### 连接 Material Expression
```python
# 连接 node_a 的输出 "RGB" 到 node_b 的输入 "B"
unreal.MaterialEditingLibrary.connect_material_expressions(node_a, "RGB", node_b, "B")
```

### 重编译 Material
```python
mat = unreal.load_asset("/Game/Materials/M_Example")
unreal.MaterialEditingLibrary.recompile_material(mat)
```

---

## Blueprint

### 加载 Blueprint
```python
bp = unreal.load_asset("/Game/Blueprints/BP_Example")
print(f"Blueprint: {bp.get_name()}, Class: {bp.get_class().get_name()}")
```

### 获取 Blueprint 的默认对象 (CDO)
```python
bp = unreal.load_asset("/Game/Blueprints/BP_Example")
# generated_class() 在部分版本不可用，使用 reflect 获取 GeneratedClass 路径
# reflect(action="get", object="<bp_path>", property="GeneratedClass") → 得到 _C 类路径
# 然后:
gen_class = unreal.load_object(name="/Game/Blueprints/BP_Example.BP_Example_C", outer=None)
if gen_class:
    cdo = unreal.get_default_object(gen_class)
    print(f"CDO: {cdo}")
```
> 如果 `bp.generated_class()` 可用则直接使用；否则通过 `reflect` 工具读取 `GeneratedClass` 属性。

### 编译 Blueprint
```python
# ⚠️ Blueprint 编译 API 在 UE 4.26 Python 中未暴露
# KismetSystemLibrary.compile_blueprint、BlueprintEditorLibrary 均不可用
# 建议: 在编辑器 UI 中手动编译，或通过 describe_object 查找当前版本可用方法
```

---

## Static Mesh

### 获取 Static Mesh Actor 的 Mesh 引用
```python
# actor 是一个 StaticMeshActor
mesh_comp = actor.static_mesh_component
mesh = mesh_comp.static_mesh
print(f"Mesh: {mesh.get_path_name()}" if mesh else "No mesh assigned")
```

### 设置 Static Mesh
```python
new_mesh = unreal.load_asset("/Game/Meshes/SM_NewMesh")
actor.static_mesh_component.set_static_mesh(new_mesh)
```

### 获取 Mesh 的材质插槽
```python
mesh_comp = actor.static_mesh_component
num_materials = mesh_comp.get_num_materials()
for i in range(num_materials):
    mat = mesh_comp.get_material(i)
    print(f"Slot {i}: {mat.get_name() if mat else 'None'}")
```

---

## Editor Utility

### 执行控制台命令
```python
world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
unreal.SystemLibrary.execute_console_command(world, "stat fps")
```

> ⚠️ **`execute_console_command` 安全规则** — Python 脚本运行在 World Tick 帧内部。
> 凡会**销毁/重建 UObject、触发 GC、阻塞渲染线程**的命令，必须加 `DEFER` 前缀，
> 延迟到帧末 `TickDeferredCommands()` 执行，否则会破坏 TickFunction 状态导致崩溃。
>
> ```python
> # ❌ 危险：在 tick 帧内直接执行
> unreal.SystemLibrary.execute_console_command(world, 'MAP REBUILD')
> unreal.SystemLibrary.execute_console_command(world, 'obj gc')
>
> # ✅ 安全：延迟到帧末
> unreal.SystemLibrary.execute_console_command(world, 'DEFER MAP REBUILD')
> unreal.SystemLibrary.execute_console_command(world, 'DEFER obj gc')
> ```
>
> **需要 DEFER 的命令**：`MAP REBUILD`、`MAP REBUILD ALLVISIBLE`、`obj gc`，以及任何涉及 Actor/Component 删除重建的命令。
> **可直接执行**：`r.XXX`、`stat XXX` 等 CVar/统计命令，`INVALIDATELIGHTINGCACHES`、`CLEAN BSPELEMENTS` 等只修改标记的命令。

### 获取项目设置路径
```python
paths = unreal.Paths
content_dir = paths.project_content_dir()
project_dir = paths.project_dir()
print(f"Content: {content_dir}\nProject: {project_dir}")
```

---

## 常用模式

### World Context 获取
许多 `GameplayStatics` / `KismetSystemLibrary` 函数需要 `WorldContextObject` 参数。
在编辑器 Python 中，使用：
```python
world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
# 然后传入 world 作为第一个参数
actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.StaticMeshActor)
```

### 批量处理模式
```python
import unreal
registry = unreal.AssetRegistryHelpers.get_asset_registry()
asset_data_list = registry.get_assets_by_path("/Game/Materials", recursive=True)
with unreal.ScopedSlowTask(len(asset_data_list), "Processing...") as slow_task:
    slow_task.make_dialog(True)
    for asset_data in asset_data_list:
        if slow_task.should_cancel():
            break
        slow_task.enter_progress_frame(1, f"Processing {asset_data.package_name}")
        asset = unreal.load_asset(str(asset_data.package_name))
        # ... 处理 asset ...
```

### 错误处理模式
```python
import unreal
try:
    asset = unreal.load_asset("/Game/Path/To/Asset")
    if asset is None:
        print("ERROR: Asset not found")
    else:
        # 处理 asset
        print(f"Loaded: {asset.get_name()}")
except Exception as e:
    print(f"ERROR: {e}")
```

### 类型转换 (Cast)
```python
world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)
if actors:
    static_mesh_actor = unreal.StaticMeshActor.cast(actors[0])  # 返回 None 如果类型不匹配
    if static_mesh_actor:
        print(f"Cast succeeded: {static_mesh_actor.get_name()}")
    else:
        print("Cast failed — not a StaticMeshActor")
```

### 属性读取
```python
# get_editor_property 可读取任意 BlueprintVisible 属性
hidden = actor.get_editor_property("hidden")
tags = actor.get_editor_property("tags")
print(f"hidden={hidden}, tags={tags}")
```

### 属性设置
```python
actor.set_editor_property("hidden", True)
actor.set_editor_property("tags", ["MyTag", "AnotherTag"])
```

### 按类型统计 Actor（分组计数）
```python
from collections import Counter
world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)
counter = Counter(a.get_class().get_name() for a in actors)
for cls_name, count in counter.most_common():
    print(f"  {cls_name}: {count}")
```

---

## ⛔ Known Failures & Crashes

> 以下操作已验证会导致崩溃或静默失败。**在写任何 exec_python 脚本前务必检查此清单。**

### 1. EditorLevelLibrary 在 UE 4.26 不可用
`unreal.EditorLevelLibrary` 需要 "Editor Scripting Utilities" 插件（默认未启用）。
**替代方案**：使用 `unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()` + `GameplayStatics`。

### 2. ACTOR ADD 控制台命令会崩溃
`execute_console_command(world, "ACTOR ADD ...")` 尝试交互式视口放置，与 Python/MCP 上下文冲突。
**替代方案**：使用 `BeginDeferredActorSpawnFromClass` + `FinishSpawningActor`（见上方 Spawn Actor 部分）。

### 3. 直接 Spawn 带 TickFunction 的 Actor 会崩溃
`PointLight`、`DirectionalLight`、`SkyLight`、`CameraActor` 等在构造时注册 TickFunction，
与 MCP 同步执行上下文冲突（Tick 周期碰撞）。
**替代方案**：使用 `register_slate_post_tick_callback` 延迟执行（见上方「延迟执行」部分）。

### 4. find_object() 无法访问 PIE World
`unreal.find_object()` / `unreal.load_object()` 只搜索持久化编辑器世界。PIE 创建的临时世界不可访问。
**替代方案**：在进入 PIE 前操作编辑器世界 Actor。

### 5. PIE 期间修改编辑器 Actor 导致 Tick 崩溃
PIE 引用编辑器世界 Actor。在 PIE 运行时修改它们会导致 Tick 管线状态不一致。
**替代方案**：退出 PIE 后再通过 Python 修改 Actor。

### 6. Rotator 位置参数顺序反直觉
`unreal.Rotator(a, b, c)` 位置参数顺序为 `(roll, pitch, yaw)`，不是 `(pitch, yaw, roll)`。
**替代方案**：**务必使用关键字参数** `unreal.Rotator(pitch=0, yaw=90, roll=0)`。

### 7. save_packages 需要 Package 而非 Asset
`EditorLoadingAndSavingUtils.save_packages()` 需要 `UPackage` 对象，不是 asset UObject。
**替代方案**：`save_packages([asset.get_outer()], only_dirty=True)`。
