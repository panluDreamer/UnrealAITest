---
name: ue-agent-builder
description: >
  Dynamically create and update Agents and Skills for the UnrealEngineAIAssist
  plugin. Use when the user says "create agent", "add agent", "new agent",
  "update agent", "create skill", "add skill", "new skill", "update skill",
  or asks to extend the AI assistant's capabilities. Also use when the user
  describes a new domain specialization (e.g. "I need an agent for audio",
  "add a skill for world partition") or wants to modify an existing agent/skill
  definition.
allowed-tools: Read Write Edit Glob Grep Bash(python*,git*,ls*,mkdir*,cp*) Task
---

# UE Agent Builder — Dynamic Agent & Skill Creator

> Create, update, and validate Agents and Skills for the UnrealEngineAIAssist plugin.

## Overview

This skill scaffolds new Agents (role-based domain specialists) and Skills
(reusable workflow definitions) following the exact conventions of the existing
plugin architecture. It ensures consistency, creates all required files, and
syncs to client directories via `setup.py` (which auto-discovers agents and
auto-syncs SVN externals).

## Terminology

| Term | Meaning | Location |
|------|---------|----------|
| **Agent** | Role-based sub-agent with domain expertise, references, and self-bootstrap | `Agents/{AgentName}/` |
| **Skill** | Reusable workflow with documentation, optional scripts & references | `Skills/{skill-name}/` |
| **SKILL.md** | YAML frontmatter + Markdown definition file (both agents and skills have one) | `{Component}/SKILL.md` |
| **RULE.md** | Shared safety rules loaded by ALL agents | `Agents/RULE.md` |
| **Plugin Dir** | Source of truth for all definitions | `Engine/Plugins/UnrealEngineAIAssist/` |
| **Agent Dir** | Client-specific installation (symlinked from Plugin Dir) | `Engine/.{client}/` |

---

## Workflow: Create Agent

### Step 1 — Gather Requirements

Ask the user (or infer from context):

1. **Agent name** (PascalCase, e.g. `AudioDesigner`, `UIBuilder`, `VFXArtist`)
2. **Domain specialization** — what types of tasks does this agent handle?
3. **Trigger conditions** — when MUST this agent be activated?
4. **Key UE APIs** — which Unreal classes/subsystems does it primarily use?
5. **Initial references** — any known patterns, templates, or failure modes?

### Step 2 — Scaffold Files

Use the template from `references/agent-template.md` to generate:

```
Agents/{AgentName}/
├── SKILL.md               ← filled from agent-template.md
└── references/
    └── known-failures.md  ← empty starter (or pre-filled if user provided failures)
```

**Naming conventions:**
- Directory name: PascalCase (e.g. `AudioDesigner`)
- `name` in YAML frontmatter: `ue-{kebab-case}` (e.g. `ue-audio-designer`)
- Description: starts with role noun, includes MUST-trigger list

### Step 3 — Sync to Client Directories

Run `setup.py` which auto-discovers agents from `Agents/*/SKILL.md` and auto-syncs
SVN externals on all client agent directories (`.codebuddy/agents/`, `.claude/agents/`, etc.):

```bash
python Plugins/UnrealEngineAIAssist/setup.py
```

Then update SVN to pull the new externals:
```bash
svn update .codebuddy/agents .claude/agents
```

> **Note**: `setup.py` no longer requires a manual `AGENTS` list — it scans `Agents/` automatically.
> If the client directories use SVN externals, `setup.py` updates them in place.
> If they use junctions/symlinks (non-SVN), it creates links as before.

### Step 4 — Validate

Run the validation checklist from `references/validation-checklist.md`:

1. SKILL.md has valid YAML frontmatter with `name` and `description`
2. `description` includes "MUST be triggered when:" with bullet list
3. `description` ends with "On activation: reads ../RULE.md"
4. Activation Checklist reads `../RULE.md` as step 1
5. Role section describes 3-5 specializations
6. When to Use Each Tool table is present
7. Self-Bootstrap section references the agent's own `references/` files
8. `references/` directory exists with at least `known-failures.md`

### Step 5 — Verify Registration

After `setup.py` + `svn update`, confirm the agent appears in the client directory:
```bash
ls .codebuddy/agents/{AgentName}/SKILL.md
```

> **User must restart CodeBuddy** (new session) for the agent to appear in the available agents list.

---

## Workflow: Create Skill

### Step 1 — Gather Requirements

Ask the user (or infer from context):

1. **Skill name** (kebab-case, prefixed with `ue-`, e.g. `ue-audio-tools`, `ue-world-partition`)
2. **Purpose** — what workflow does this skill enable?
3. **Trigger phrases** — what user utterances should invoke this skill?
4. **Allowed tools** — which Claude Code tools does this skill need?
5. **Has scripts?** — does it need Python automation scripts?
6. **Has MCP tools?** — does it extend the MCP server with new commands?

### Step 2 — Scaffold Files

Use the template from `references/skill-template.md` to generate:

```
Skills/{skill-name}/
├── SKILL.md               ← filled from skill-template.md
├── references/             ← supporting docs
│   └── (domain-specific references)
└── scripts/                ← only if needed
    └── (Python utilities)
```

**Naming conventions:**
- Directory name: kebab-case with `ue-` prefix (e.g. `ue-audio-tools`)
- `name` in YAML frontmatter: matches directory name exactly
- `allowed-tools`: list only what's needed (principle of least privilege)

### Step 3 — Register in setup.py

Add the skill name to the `SKILLS` list in `setup.py`:

```python
SKILLS = [
    "ue-knowledge-init",
    "ue-knowledge-reader",
    "ue-knowledge-update",
    "ue-python-script",
    "ue-audio-tools",  # ← new
]
```

### Step 4 — Validate

Run the validation checklist from `references/validation-checklist.md`:

1. SKILL.md has valid YAML frontmatter with `name`, `description`, `allowed-tools`
2. `name` matches directory name exactly
3. `description` includes trigger phrases
4. `allowed-tools` lists only required tools
5. Markdown body has clear workflow steps
6. `references/` directory exists (even if empty)
7. Skill name is in `setup.py` SKILLS list
8. If it has scripts: scripts are runnable with `python <script> --help`

### Step 5 — Sync to Engine

```bash
python Plugins/UnrealEngineAIAssist/setup.py
```

> **Note**: Unlike agents, skills still require manual registration in the `SKILLS` list in `setup.py`.

---

## Workflow: Update Existing Agent or Skill

### Step 1 — Identify Target

Read the current SKILL.md:
```
Agents/{AgentName}/SKILL.md   — for agents
Skills/{skill-name}/SKILL.md  — for skills
```

### Step 2 — Determine Change Type

| Change Type | Action |
|-------------|--------|
| Add trigger condition | Edit `description` YAML field — append to MUST-trigger list |
| Add domain knowledge | Edit markdown body — add section under Key Domain Knowledge |
| Add reference file | Write new `.md` to `references/` — update Activation Checklist |
| Change name | Update YAML `name`, directory name; run `setup.py` to re-sync externals |
| Add safety rule | Propose edit to `Agents/RULE.md` (affects ALL agents) |
| Add tool mapping | Edit "When to Use Each Tool" table |

### Step 3 — Apply Changes

Use `Edit` tool for targeted changes to existing files.
Use `Write` tool only for new reference files.

### Step 4 — Re-validate

Run the full validation checklist on the modified component.

---

## Critical Rules

1. **Never modify RULE.md without user confirmation** — it affects ALL agents
2. **Agent names are PascalCase** — `AudioDesigner`, not `audio-designer`
3. **Skill names are kebab-case with ue- prefix** — `ue-audio-tools`, not `AudioTools`
4. **YAML frontmatter name must be ue-kebab-case** — even for agents (`ue-audio-designer`)
5. **Always include Self-Bootstrap section** in agent SKILL.md — agents grow their knowledge
6. **Always sync to engine** after creating/updating — run `setup.py` then `svn update`; user must restart IDE for new agents
7. **Templates are starting points** — customize heavily based on the domain
8. **One agent = one domain** — don't create overlapping agents; extend existing ones instead

---

## Reference Files

| File | Purpose |
|------|---------|
| `references/agent-template.md` | Scaffolding template for new Agent SKILL.md |
| `references/skill-template.md` | Scaffolding template for new Skill SKILL.md |
| `references/validation-checklist.md` | Pre-flight checklist for validating definitions |
