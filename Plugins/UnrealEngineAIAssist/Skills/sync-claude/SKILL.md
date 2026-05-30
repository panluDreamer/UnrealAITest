---
name: sync-claude
description: |
  Sync the .claude/ directory structure (skills, agents, settings, mcp config).
  Creates symlinks/junctions from .claude/skills/ and .claude/agents/ back to the
  actual Skills/ and Agents/ directories, plus generates settings.local.json and .mcp.json.
  TRIGGER when:
  - User says "sync claude", "setup claude", "init claude", "initialize"
  - User just cloned the repo and needs to set up Claude Code integration
  - User added a new skill or agent and wants .claude/ updated
  DO NOT TRIGGER when:
  - User is asking about Claude API or Claude models (use claude-api skill)
---

# Sync Claude — Initialize .claude/ Directory

## What This Does

Creates/updates the `.claude/` directory at the plugin root with:
- `skills/{name}/` → symlink to `Skills/{name}/` (junction on Windows)
- `agents/{name}/` → symlink to `Agents/{name}/` (junction on Windows)
- `settings.local.json` — pre-approved MCP tool permissions
- `../.mcp.json` — MCP server configuration (at plugin root)

## Usage

Run this command in your terminal from the plugin directory:

```bash
python setup.py
```

Or invoke this skill in Claude Code:
```
/sync-claude
```

## How It Works (for AI execution)

When this skill is invoked, execute the following:

```bash
python setup.py --client claude
```

That's it. The `setup.py` script handles:
1. Scanning `Skills/` for directories with `SKILL.md` 
2. Scanning `Agents/` for directories with `SKILL.md`
3. Creating `.claude/skills/{name}` → junction/symlink to `Skills/{name}`
4. Creating `.claude/agents/{name}` → junction/symlink to `Agents/{name}`
5. Writing `.claude/settings.local.json` with MCP tool permissions
6. Writing `.mcp.json` with the MCP server path
7. Installing Python dependencies for the MCP server (`mcp[cli]>=1.4.1`)

## After Sync

Verify with:
```bash
python setup.py --check
```

Expected output:
```
[OK] .claude/skills/ue-python-script → Skills/ue-python-script
[OK] .claude/skills/device-bridge → Skills/device-bridge
[OK] .claude/skills/renderdoc-capture → Skills/renderdoc-capture
[OK] .claude/skills/ue-knowledge-init → Skills/ue-knowledge-init
[OK] .claude/skills/ue-knowledge-reader → Skills/ue-knowledge-reader
[OK] .claude/skills/ue-knowledge-update → Skills/ue-knowledge-update
[OK] .claude/skills/ue-agent-builder → Skills/ue-agent-builder
[OK] .claude/skills/sync-claude → Skills/sync-claude
[OK] .claude/agents/ArtTechnician → Agents/ArtTechnician
[OK] .claude/agents/DataDesigner → Agents/DataDesigner
[OK] .claude/agents/GameplayProgrammer → Agents/GameplayProgrammer
[OK] .claude/agents/LevelDesigner → Agents/LevelDesigner
[OK] .claude/settings.local.json
[OK] .mcp.json
[OK] MCP server dependencies installed
```

## When to Re-run

- After `git clone` (first time setup)
- After adding/removing a skill in `Skills/`
- After adding/removing an agent in `Agents/`
- After pulling changes that modified `setup.py` or added new skills

## Uninstall

```bash
python setup.py --uninstall
```

Removes `.claude/`, `.mcp.json`, and MCP server venv. Preserves `Knowledge/` data.
