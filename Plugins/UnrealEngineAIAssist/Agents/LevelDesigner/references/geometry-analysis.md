# Geometry Analysis Templates

> One-shot scripts for extracting actor transforms, mesh bounds, and spatial relationships.
> Copy-paste into exec_python. All scripts are self-contained.

---

## Extract All Actor Transforms + Mesh Bounds

```python
import unreal

world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.StaticMeshActor)

print(f"=== Scene Geometry Report ({len(actors)} StaticMeshActors) ===\n")
for actor in actors:
    name = actor.get_name()
    t = actor.get_actor_transform()
    loc = t.translation
    rot = t.rotation.rotator()
    scale = t.scale3d

    mesh_comp = actor.static_mesh_component
    mesh = mesh_comp.static_mesh

    if mesh:
        # Get mesh bounds (local space)
        box_min, box_max = mesh.get_bounds().origin, mesh.get_bounds().box_extent
        print(f"{name}:")
        print(f"  Mesh: {mesh.get_path_name()}")
        print(f"  Location: ({loc.x:.1f}, {loc.y:.1f}, {loc.z:.1f})")
        print(f"  Rotation: (P={rot.pitch:.1f}, Y={rot.yaw:.1f}, R={rot.roll:.1f})")
        print(f"  Scale:    ({scale.x:.2f}, {scale.y:.2f}, {scale.z:.2f})")
        print(f"  Bounds Origin: ({box_min.x:.1f}, {box_min.y:.1f}, {box_min.z:.1f})")
        print(f"  Bounds Extent: ({box_max.x:.1f}, {box_max.y:.1f}, {box_max.z:.1f})")
    else:
        print(f"{name}: (no mesh assigned)")
    print()
```

---

## Analyze Mesh Origin & Extent (Single Actor)

```python
import unreal

# Replace 'TargetActorName' with the actual actor name
world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.StaticMeshActor)
target = next((a for a in actors if a.get_name() == "TargetActorName"), None)

if target:
    mesh_comp = target.static_mesh_component
    mesh = mesh_comp.static_mesh
    if mesh:
        bounds = mesh.get_bounds()
        print(f"Mesh: {mesh.get_path_name()}")
        print(f"Bounds Origin: {bounds.origin}")
        print(f"Bounds BoxExtent: {bounds.box_extent}")
        print(f"Bounds SphereRadius: {bounds.sphere_radius}")

        # World-space bounds via component
        comp_bounds_origin, comp_bounds_extent = mesh_comp.get_local_bounds()
        print(f"\nComponent Local Bounds:")
        print(f"  Origin: {comp_bounds_origin}")
        print(f"  Extent: {comp_bounds_extent}")
else:
    print("Actor not found")
```

---

## Scene Spatial Relationships (Distance Matrix)

```python
import unreal
import math

world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.StaticMeshActor)

# Get locations
locs = {}
for a in actors:
    loc = a.get_actor_location()
    locs[a.get_name()] = (loc.x, loc.y, loc.z)

# Print distance matrix (top N closest pairs)
pairs = []
names = list(locs.keys())
for i in range(len(names)):
    for j in range(i+1, len(names)):
        dx = locs[names[i]][0] - locs[names[j]][0]
        dy = locs[names[i]][1] - locs[names[j]][1]
        dz = locs[names[i]][2] - locs[names[j]][2]
        dist = math.sqrt(dx*dx + dy*dy + dz*dz)
        pairs.append((dist, names[i], names[j]))

pairs.sort()
print(f"=== Closest Actor Pairs (top 20 of {len(pairs)}) ===")
for dist, a, b in pairs[:20]:
    print(f"  {dist:8.1f} cm  {a} <-> {b}")
```

---

## Actor Type Census

```python
from collections import Counter
import unreal

world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)

counter = Counter(a.get_class().get_name() for a in actors)
print(f"=== Actor Type Census ({len(actors)} total) ===")
for cls_name, count in counter.most_common():
    print(f"  {count:4d}  {cls_name}")
```

---

## Filter Actors by Bounding Box Region

```python
import unreal

# Define region of interest (world coordinates)
region_min = unreal.Vector(-500, -500, 0)
region_max = unreal.Vector(500, 500, 300)

world = unreal.get_editor_subsystem(unreal.LayersSubsystem).get_world()
actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)

in_region = []
for a in actors:
    loc = a.get_actor_location()
    if (region_min.x <= loc.x <= region_max.x and
        region_min.y <= loc.y <= region_max.y and
        region_min.z <= loc.z <= region_max.z):
        in_region.append(a)

print(f"=== Actors in Region ({len(in_region)}/{len(actors)}) ===")
print(f"Region: ({region_min.x},{region_min.y},{region_min.z}) to ({region_max.x},{region_max.y},{region_max.z})")
for a in in_region:
    loc = a.get_actor_location()
    print(f"  {a.get_name()} ({a.get_class().get_name()}) at ({loc.x:.0f}, {loc.y:.0f}, {loc.z:.0f})")
```
