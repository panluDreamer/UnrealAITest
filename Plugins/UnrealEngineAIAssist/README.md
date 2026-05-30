# UnrealEngineAIAssist

Lightweight TCP bridge + knowledge graph for AI agent interaction with Unreal Editor.

Fully self-contained — the plugin directory holds all AI client configs, knowledge,
and MCP server setup. No Engine directory modifications required.

## Architecture

```
AI Agent (Claude / Codebuddy / Cursor / Windsurf)
    |  MCP Protocol (stdio)
Python MCP Server (~180 lines)
    |  TCP JSON (:13090)
C++ UnrealEngineAIAssist Plugin
    |  UE API (GameThread)
Unreal Editor
```

## Quick Start

### 1. Build the Plugin

```bash
# Regenerate project files
GenerateProjectFiles.bat    # Windows
GenerateProjectFiles.sh     # Mac/Linux

# Build via IDE (Visual Studio / Xcode / Rider)
```

Verify editor log on startup:
```
UnrealEngineAIAssist: Listening on 127.0.0.1:13090
UnrealEngineAIAssist: Wrote .../plugin.config.json
```

### 2. Run Setup

```bash
cd <ProjectRoot>/Plugins/UnrealEngineAIAssist
python setup.py                      # Auto-detect AI client
python setup.py --client claude      # Or specify explicitly
python setup.py --check              # Verify everything works
```

The setup script creates everything inside the plugin directory:
- `{PluginDir}/.{client}/skills/` with symlinks to Skills/
- `{PluginDir}/.{client}/agents/` with symlinks to Agents/
- `{PluginDir}/.mcp.json` pointing to the MCP server
- Installs Python dependencies (`mcp[cli]>=1.4.1`)
- Merges required permissions into `settings.local.json`

> **Note**: The C++ plugin writes `plugin.config.json` on editor startup.
> This file contains the engine directory path — `setup.py` and the MCP server
> read it automatically. No manual path configuration needed.

### 3. (Optional) Initialize Knowledge Graph

In your AI client, run:
```
/ue-knowledge-init
```

This generates module summaries at `{PluginDir}/Knowledge/`.

## What's Included

| Component | Description |
|-----------|-------------|
| **C++ Editor Module** | TCP server — `exec_python`, `describe_object`, `generate_catalog`, `get_log`, `reflect` + Blueprint graph editing |
| **C++ Runtime Module** | Device-side TCP client — `exec_console`, `exec_unlua`, CVar get/set (Android/iOS, DeveloperTool builds only) |
| **MCP Server** | Python bridge translating MCP tool calls to TCP JSON |
| **Skills** | 7 AI skills for scripting, device debugging, RenderDoc analysis, knowledge graph, and agent building |
| **CLI Tools** | `devbridge` (Android device debugging), `rdc-cli` (RenderDoc frame analysis) |

### Skills

| Skill | Purpose |
|-------|---------|
| `ue-python-script` | Discover & execute UE functions via MCP tools |
| `device-bridge` | Execute console commands, CVars, and Lua on connected Android devices |
| `renderdoc-capture` | Analyze RenderDoc GPU frame captures (.rdc files) |
| `ue-knowledge-init` | Bootstrap the module knowledge graph |
| `ue-knowledge-update` | Incrementally update knowledge after code changes |
| `ue-knowledge-reader` | Navigate & understand UE code using the knowledge graph |
| `ue-agent-builder` | Dynamically create and update Agents and Skills |
| `sync-claude` | Initialize/sync `.claude/` directory (symlinks, settings, MCP config) |

### MCP Tools

| Tool | Description |
|------|-------------|
| `exec_python(code)` | Run Python in the editor |
| `describe_object(class_name)` | UHT reflection introspection |
| `generate_catalog(output_dir?)` | Scan all UClasses -> JSON catalog |
| `get_log(count?, category?, filter?)` | Retrieve editor log entries |
| `reflect(action, ...)` | Raw property access (bypasses permission gates) |

### CLI Tools

| Tool | Install | Purpose |
|------|---------|---------|
| `devbridge` | `cd ThirdParty/DevBridgeCli && uv tool install .` | Android device debugging (console commands, CVars, Lua execution via ADB) |
| `rdc-cli` | `cd ThirdParty/RdcCli && uv tool install .` | RenderDoc capture analysis (draw calls, shaders, pipeline state, GPU timings) |

## Configuration

| Parameter | Default | Override |
|-----------|---------|----------|
| TCP Port | 13090 | `-AgentBridgePort=N` (editor launch arg) or `AGENT_BRIDGE_PORT` env |
| TCP Host | 127.0.0.1 | `AGENT_BRIDGE_HOST` env |
| Agent Dir | .claude | `AGENT_DIR_NAME` env (e.g. `.claude`, `.cursor`) |
| Plugin Dir | Auto-detected | `AGENT_BRIDGE_PLUGIN_DIR` env (for MCP server) |

### plugin.config.json

Written automatically by the C++ plugin on editor startup:
```json
{
  "engine_dir": "<YOUR_ENGINE>/Engine",
  "plugin_dir": "<YOUR_PROJECT>/Plugins/UnrealEngineAIAssist",
  "engine_version": "4.26.2-0+++UE4+Release-4.26"
}
```

This decouples the plugin from any fixed directory layout — it works as an
Engine Plugin, a Project Plugin, or a standalone directory.

### Multiple AI Clients

Run setup for each client:
```bash
python setup.py --client claude
python setup.py --client codebuddy
```

Each gets its own `.{client}/` directory with symlinks to the same Skills.

## Directory Structure

```
UnrealEngineAIAssist/
├── Source/
│   ├── UnrealEngineAIAssist/           # Editor module (TCP listener, exec_python, reflect, etc.)
│   └── UnrealEngineAIAssistRuntime/    # Runtime module (device TCP client, exec_unlua)
├── Skills/
│   ├── ue-python-script/              # MCP server + common-operations reference
│   ├── device-bridge/                  # Android device debugging skill
│   ├── renderdoc-capture/              # RenderDoc analysis skill
│   ├── ue-knowledge-init/              # Bootstrap knowledge graph
│   ├── ue-knowledge-reader/            # Query knowledge graph
│   ├── ue-knowledge-update/            # Incremental update knowledge graph
│   ├── ue-agent-builder/              # Create custom agents/skills
│   └── sync-claude/                    # Initialize .claude/ directory
├── Agents/                             # Example agents + RULE.md (create more via ue-agent-builder)
├── ThirdParty/
│   ├── DevBridgeCli/                   # devbridge CLI (Python, uv tool install)
│   └── RdcCli/                         # rdc-cli (Python, uv tool install)
├── Knowledge/                          # Generated by ue-knowledge-init
├── UnrealEngineAIAssist.uplugin
├── setup.py                            # Run once after clone: python setup.py
├── CLAUDE.md                           # AI agent instructions
└── README.md
```

## For AI Agents

If you are an AI agent reading this file:

1. **MCP tools** are available via the `unreal-agent-bridge` MCP server
2. **Skills** provide structured workflows — invoke them by name (e.g. `/ue-knowledge-init`)
3. **Knowledge graph** lives at `{PluginDir}/Knowledge/` — use `query_module_graph.py` for queries
4. **Catalog** at `{PluginDir}/.{agent}/callable_catalog/` — 3-level discovery: index -> class -> live introspection
5. **plugin.config.json** in the plugin root contains `engine_dir` if you need to locate engine source files
6. **Agents/RULE.md** contains safety rules that must be followed for `exec_python`

## Uninstall

```bash
python setup.py --uninstall
```

This removes symlinks, venv, and MCP config. Knowledge data is preserved.

## Requirements

- Unreal Engine 4.26+
- Python 3.10+ (for setup and MCP server)
- PythonScriptPlugin (optional — `exec_python` requires it, other tools work without)
- Android SDK platform-tools (optional — for `devbridge` device debugging)
- RenderDoc (optional — for `rdc-cli` frame analysis)
