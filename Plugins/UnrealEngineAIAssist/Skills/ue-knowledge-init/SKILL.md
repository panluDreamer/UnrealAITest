---
name: ue-knowledge-init
description: >
  Cold-start generator for the Unreal Engine knowledge graph. Uses Python
  scripts for deterministic work (Build.cs parsing, shader mapping) and
  sub-agent dispatch for summary generation. Use when setting up a new
  engine version, switching branches, or when the knowledge directory is
  empty. Also use when the user says "initialize knowledge", "generate
  module graph", "bootstrap knowledge", or asks to set up AI-assisted
  engine understanding.
allowed-tools: Read Write Edit Bash(python*,git*) Glob Grep Task
---

# UE Knowledge Graph — Cold Start Generator

Bootstraps the structured knowledge graph at `Knowledge/`.

## Pre-flight

1. **Locate the engine root** — read `plugin.config.json` in the plugin directory
   to get `engine_dir`. The engine root is the parent of `engine_dir`
   (e.g. if `engine_dir` = `[your_engine_path]/Engine`, engine root = `[your_engine_path]`).
   Verify `{engine_root}/Engine/Source/Runtime/Core/Core.Build.cs` exists.
   If `plugin.config.json` is missing or the path is wrong, **ask the user** for
   the engine root path and pass it via `--engine-root`.
2. Check if `Knowledge/module_graph.json` already exists
   - If yes, ask user: **regenerate** or **resume** (skip to missing summaries)?
3. Ensure Python 3.6+ is available: `python --version`

## Sub-Agent Dispatch Pattern

Phases 2 and 2b use the same dispatch pattern:

1. Run the planner script → it prints a JSON batch plan to stdout
2. Parse the JSON — it contains an array of `batches`
3. For each batch, read the matching prompt template from
   `Skills/ue-knowledge-init/references/summary-generation-prompt.md`
4. Fill in `{placeholders}` with info from the batch plan JSON
5. Launch a **sub-agent** (Task tool) with the filled prompt
6. **Sequential dispatch**: verify `.md` files were created before the next batch

## Phase 1: Module Graph (No LLM)

```bash
python Skills/ue-knowledge-init/scripts/parse_module_graph.py
```

Parses all `*.Build.cs` files, extracts dependencies, classifies module types, computes topological layers.

**Output**: `Knowledge/module_graph.json` (~1200+ modules, ~727KB)
**Query**: Never read this file directly. Use `scripts/query_module_graph.py` (see below).

## Phase 2: Module Summaries (Sub-Agent Dispatch)

### Generate the batch plan

```bash
python Skills/ue-knowledge-init/scripts/generate_summaries.py --resume --tier 1
```

Options: `--tier 1-4`, `--modules Core,Engine,RHI`, `--batch-size 3`, `--resume`

### Dispatch

Use the **Batch-Module Prompt** from `references/summary-generation-prompt.md`.
See [Sub-Agent Dispatch Pattern](#sub-agent-dispatch-pattern) above.

### Tier priority

| Tier | Modules | Description |
|------|---------|-------------|
| 1 | Core, CoreUObject, Engine, RHI, RenderCore, Renderer, ApplicationCore, SlateCore, Slate, InputCore | Core infrastructure |
| 2 | NavigationSystem, AIModule, PhysicsCore, Chaos, AnimationCore, AnimGraphRuntime, Landscape, Niagara, UMG, MovieScene | Key systems |
| 3 | UnrealEd, BlueprintGraph, Kismet, PropertyEditor, GraphEditor, ContentBrowser, Sequencer, Persona | Editor |
| 4 | Everything else | Alphabetical |

**Output**: `Knowledge/modules/{ModuleName}.md`
**Template**: `references/summary-template.md`

## Phase 2b: Submodule Summaries (Sub-Agent Dispatch)

Large modules (100+ files) have internal submodules detected by `scripts/detect_submodules.py`.

### Generate the submodule batch plan

```bash
python Skills/ue-knowledge-init/scripts/generate_summaries.py --submodules --auto --min-files 100 --resume
# Or for a specific module:
python Skills/ue-knowledge-init/scripts/generate_summaries.py --submodules --module Renderer --resume
```

Options: `--module Renderer`, `--auto --min-files 100`, `--only PostProcess,Mobile`, `--batch-size 4`, `--resume`

### Dispatch

Use the **Batch-Submodule Prompt** from `references/summary-generation-prompt.md`.
See [Sub-Agent Dispatch Pattern](#sub-agent-dispatch-pattern) above.

### Submodule detection

Two methods: subdirectories (>=5 files) and filename prefix clusters (>=6 files).

```bash
python Skills/ue-knowledge-init/scripts/detect_submodules.py Renderer
python Skills/ue-knowledge-init/scripts/detect_submodules.py --auto --min-files 100 --save-index
```

`--save-index` writes `Knowledge/submodule_index.json`.

**Output**: `Knowledge/modules/{ModuleName}/{SubmoduleName}.md`
**Template**: `references/submodule-template.md`

## Phase 3: Shader Map (No LLM)

```bash
python Skills/ue-knowledge-init/scripts/generate_shader_map.py
```

**Output**: `Knowledge/shader_map.json`

## Master Script

```bash
python Skills/ue-knowledge-init/scripts/init_all.py            # all phases
python Skills/ue-knowledge-init/scripts/init_all.py --resume   # skip completed
python Skills/ue-knowledge-init/scripts/init_all.py --phase 2 --tier 1
python Skills/ue-knowledge-init/scripts/init_all.py --phase 2b
```

## Manual Fallback

If Python scripts are unavailable:
1. Process **at most 5 modules** per turn, **at most 3 headers** per module (200 lines)
2. Use template from `references/summary-template.md`
3. Write to `Knowledge/modules/{ModuleName}.md`
4. Process tiers in order: 1 → 2 → 3 → 4

## Querying the Module Graph

`module_graph.json` is ~727KB — **never read it directly**. Use the query tool:

```bash
QUERY="python Skills/ue-knowledge-init/scripts/query_module_graph.py"

$QUERY info Core,Engine         # full info for specific modules
$QUERY deps Renderer            # what Renderer depends on
$QUERY rdeps Core               # what depends on Core
$QUERY layer 0                  # all layer-0 modules
$QUERY path Engine/Source/Runtime/Renderer  # find module by path
$QUERY tree RHI --depth 2       # dependency tree
$QUERY stats                    # graph-wide statistics
$QUERY overview                 # compact layer-by-layer view
$QUERY submodules Renderer      # list submodules for a module
```

## Output Structure

```
Knowledge/
├── module_graph.json      ← Phase 1
├── shader_map.json        ← Phase 3
├── submodule_index.json   ← Phase 2b (optional, from --save-index)
├── changelog.md           ← Created by ue-knowledge-update
└── modules/
    ├── Core.md            ← Phase 2
    ├── Renderer.md
    ├── Renderer/           ← Phase 2b
    │   ├── PostProcess.md
    │   ├── Mobile.md
    │   └── HairStrands.md
    └── ...
```
