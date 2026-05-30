# Skill SKILL.md Template

> Copy this template and fill in all `{PLACEHOLDERS}`.
> Delete this instruction block after filling.

---

```yaml
---
name: ue-{SKILL_NAME}
description: >
  {SKILL_SUMMARY}. Use when the user says {TRIGGER_PHRASES}.
  Also use when {ADDITIONAL_TRIGGER_CONTEXT}.
allowed-tools: {TOOL_LIST}
---
```

---

## Markdown Body

```markdown
# {SKILL_TITLE}

> {ONE_LINE_TAGLINE}

## Overview

{2-3_SENTENCES_DESCRIBING_PURPOSE_AND_VALUE}

## Pre-flight

1. {PRECONDITION_1}
2. {PRECONDITION_2}
3. {PRECONDITION_3}

## Workflow

### Step 1 — {STEP_1_NAME}

{STEP_1_DESCRIPTION}

### Step 2 — {STEP_2_NAME}

{STEP_2_DESCRIPTION}

### Step N — {STEP_N_NAME}

{STEP_N_DESCRIPTION}

## Output

{DESCRIBE_WHAT_THE_SKILL_PRODUCES_AND_WHERE_IT_GOES}

## Error Recovery

If a step fails:
1. {RECOVERY_STEP_1}
2. {RECOVERY_STEP_2}
```

---

## Placeholder Reference

| Placeholder | Example (ue-knowledge-init) | Rules |
|-------------|---------------------------|-------|
| `{SKILL_NAME}` | `knowledge-init` | kebab-case, no `ue-` prefix (added in template) |
| `{SKILL_SUMMARY}` | `Cold-start generator for the UE knowledge graph` | 1-2 sentences |
| `{TRIGGER_PHRASES}` | `"initialize knowledge", "generate module graph"` | Quoted, comma-separated |
| `{ADDITIONAL_TRIGGER_CONTEXT}` | `the knowledge directory is empty` | Contextual trigger |
| `{TOOL_LIST}` | `Read Write Edit Bash(python*,git*) Glob Grep Task` | Space-separated, use patterns |
| `{SKILL_TITLE}` | `UE Knowledge Graph — Cold Start Generator` | Display title |
| `{ONE_LINE_TAGLINE}` | `Bootstraps the structured knowledge graph at Knowledge/` | Concise |

## Allowed-Tools Reference

Common tool patterns:
- `Read` — always allowed (read files)
- `Write` — create new files
- `Edit` — modify existing files
- `Glob` — find files by pattern
- `Grep` — search file contents
- `Bash(python*,git*)` — restricted shell (only python and git commands)
- `Bash(python*,git*,ls*,mkdir*,cp*)` — shell with filesystem ops
- `Task` — dispatch sub-agents (for complex multi-step skills)

**Principle of least privilege**: only list tools the skill actually needs.

## Required Files After Scaffolding

```
Skills/{skill-name}/
├── SKILL.md                ← generated from this template
├── references/             ← supporting documentation
│   └── (quick-ref.md, templates.md, etc.)
└── scripts/                ← optional, only if Python automation needed
    └── (utilities.py, etc.)
```

## Skill vs Agent — When to Use Which

| Create a... | When... |
|-------------|---------|
| **Skill** | It's a reusable workflow that any agent (or the main conversation) can invoke |
| **Agent** | It's a domain specialist role that needs persistent context, self-bootstrap, and references |
| **Both** | The domain needs a specialist agent AND a standalone workflow (e.g. knowledge-reader + knowledge-init) |
