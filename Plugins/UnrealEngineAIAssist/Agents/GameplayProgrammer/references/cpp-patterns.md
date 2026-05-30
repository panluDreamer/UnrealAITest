# C++ Gameplay Patterns

> Reference for understanding and navigating C++ gameplay code using the ue-knowledge-reader skill.
> This file focuses on patterns; for actual code navigation, invoke `ue-knowledge-reader`.

---

## Using ue-knowledge-reader for C++ Understanding

When you need to understand a C++ gameplay system:

1. **Invoke the `ue-knowledge-reader` skill** — it has the knowledge graph
2. **Query the module graph** — find which module contains the class/system
3. **Read module summaries** — understand the module's purpose and key classes
4. **Read source files** with module context — the reader provides context headers

### Example: Understanding a Trigger System
```
1. /ue-knowledge-reader → "Find the module that handles trigger volumes"
2. Module: Engine (submodule: Components/PrimitiveComponent)
3. Key classes: UShapeComponent, UBoxComponent, USphereComponent
4. Read: Engine/Source/Runtime/Engine/Classes/Components/ShapeComponent.h
```

---

## Common Gameplay C++ Patterns

### Actor Component Architecture

```
AActor
├── USceneComponent (RootComponent)
│   ├── UStaticMeshComponent
│   ├── USkeletalMeshComponent
│   ├── UShapeComponent (collision)
│   │   ├── UBoxComponent
│   │   ├── USphereComponent
│   │   └── UCapsuleComponent
│   ├── ULightComponent
│   └── UChildActorComponent
└── UActorComponent (non-scene)
    ├── UMovementComponent
    └── UInputComponent
```

### Event Dispatch Pattern

```cpp
// Delegate declaration (in .h)
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnOverlapSignature, AActor*, OtherActor);

// Property declaration
UPROPERTY(BlueprintAssignable)
FOnOverlapSignature OnActorBeginOverlap;

// Binding in Blueprint = K2Node_Event for "ReceiveActorBeginOverlap"
// Binding in C++ = AddDynamic(this, &AMyActor::HandleOverlap)
```

### Overlap/Hit Events

The standard overlap/hit chain:
```
UPrimitiveComponent::OnComponentBeginOverlap  (component level)
    → AActor::NotifyActorBeginOverlap          (actor level, internal)
    → AActor::ReceiveActorBeginOverlap         (BlueprintImplementableEvent)
```

For Python/Blueprint scripting, bind to:
- `ReceiveActorBeginOverlap` — actor-level overlap
- `ReceiveActorEndOverlap` — actor-level end overlap
- `ReceiveHit` — hit events

### Collision Setup Pattern

For trigger volumes, the collision settings must be:
```
CollisionEnabled = QueryOnly (or QueryAndPhysics)
CollisionObjectType = WorldDynamic (or custom)
CollisionResponses = Overlap for relevant channels
GenerateOverlapEvents = true
```

Both the trigger AND the overlapping actor must have `GenerateOverlapEvents = true`.

---

## Module Dependency Hints

| Gameplay Feature | Key Module(s) | Key Classes |
|-----------------|---------------|-------------|
| Trigger/Overlap | Engine | UShapeComponent, UPrimitiveComponent |
| Navigation | NavigationSystem | UNavigationSystemV1, ANavMeshBoundsVolume |
| AI Behavior | AIModule | UAIController, UBehaviorTree |
| Animation | Engine (Anim) | UAnimInstance, UAnimMontage |
| Physics | Engine (Physics) | UBodySetup, FBodyInstance |
| Input | Engine (Input) | UInputComponent, UPlayerInput |
| Widgets/UI | UMG | UUserWidget, UWidgetTree |
| Data Tables | Engine | UDataTable, FTableRowBase |

> For deeper exploration of any module, use `/ue-knowledge-reader` with the module name.

---

## Gameplay Interaction Patterns

### Door Trigger (Common Pattern)

```
Components:
  - UBoxComponent (trigger volume, GenerateOverlapEvents=true)
  - UStaticMeshComponent (door mesh)
  - UTimelineComponent (for smooth open/close animation)

Events:
  - ReceiveActorBeginOverlap → Start open timeline
  - ReceiveActorEndOverlap → Start close timeline

Blueprint Graph:
  BeginOverlap → Branch (IsOpen?) → PlayTimeline(OpenDoor)
  EndOverlap → Branch (!IsOpen?) → PlayTimeline(CloseDoor)
```

### Pickup Item Pattern

```
Components:
  - USphereComponent (pickup radius)
  - UStaticMeshComponent (item visual)
  - URotatingMovementComponent (optional spin)

Events:
  - ReceiveActorBeginOverlap → Check if overlapping actor is player
    → Add item to inventory → DestroyActor()
```
