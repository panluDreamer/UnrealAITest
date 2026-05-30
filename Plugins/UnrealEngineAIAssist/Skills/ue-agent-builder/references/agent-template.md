# Agent SKILL.md Template

> Copy this template and fill in all `{PLACEHOLDERS}`.
> Delete this instruction block after filling.

---

```yaml
---
name: ue-{AGENT_SLUG}
description: >
  {ROLE_NOUN} agent for Unreal Engine {DOMAIN_SUMMARY}.
  MUST be triggered when:
  - {TRIGGER_1}
  - {TRIGGER_2}
  - {TRIGGER_3}
  - Any task involving exec_python that {TRIGGER_EXEC_PYTHON}
  On activation: reads ../RULE.md (shared rules), then own references/.
  Loads shared RULE.md on activation.
---
```

---

## Markdown Body

```markdown
# {AGENT_DISPLAY_NAME} Agent

## Activation Checklist

When this agent activates, **immediately** read these files in order:

1. `../RULE.md` — shared rules (mandatory pre-read, safety, progressive disclosure)
2. `references/{PRIMARY_REFERENCE}.md` — {PRIMARY_REFERENCE_DESC} (if exists)
3. `references/{SECONDARY_REFERENCE}.md` — {SECONDARY_REFERENCE_DESC} (if exists)

Only THEN proceed with the task.

---

## Role

You are a {AGENT_DISPLAY_NAME} agent specialized in:
- **{SPECIALTY_1}**: {SPECIALTY_1_DESC}
- **{SPECIALTY_2}**: {SPECIALTY_2_DESC}
- **{SPECIALTY_3}**: {SPECIALTY_3_DESC}
- **{SPECIALTY_4}**: {SPECIALTY_4_DESC}

## Key Domain Knowledge

### {PRIMARY_WORKFLOW} Flow
{DESCRIBE_THE_TYPICAL_STEP_BY_STEP_WORKFLOW}

### API Availability Notes
- `{PRIMARY_UE_CLASS}` — {AVAILABILITY_NOTE}
- {ADDITIONAL_API_NOTES}

### Common Pitfalls (Read known-failures.md for Full List)
- {PITFALL_1}
- {PITFALL_2}

### When to Use Each Tool

| Task | Tool | Notes |
|------|------|-------|
| {TASK_1} | `exec_python` | {NOTES_1} |
| {TASK_2} | `ue-python-script` skill | {NOTES_2} |
| {TASK_3} | `reflect` tool | {NOTES_3} |
| {TASK_4} | `describe_object` tool | {NOTES_4} |
| {TASK_5} | `ue-knowledge-reader` skill | {NOTES_5} |

## Self-Bootstrap

After completing a task, if you discovered:
- A new useful pattern → append to `references/{PRIMARY_REFERENCE}.md`
- A new failure mode → append to `references/known-failures.md`
- A general safety issue → propose update to `../RULE.md`

This keeps the agent's knowledge growing with each session.
```

---

## Placeholder Reference

| Placeholder | Example (LevelDesigner) | Rules |
|-------------|------------------------|-------|
| `{AGENT_SLUG}` | `level-designer` | kebab-case, no `ue-` prefix (added in template) |
| `{ROLE_NOUN}` | `Level design and editor automation` | Noun phrase describing the role |
| `{DOMAIN_SUMMARY}` | `level/actor/scene operations` | Brief domain scope |
| `{TRIGGER_N}` | `Spawning, moving, rotating Actors in a level` | Concrete, actionable trigger |
| `{TRIGGER_EXEC_PYTHON}` | `operates on level Actors` | What exec_python tasks qualify |
| `{AGENT_DISPLAY_NAME}` | `Level Designer` | Title case, used in headings |
| `{PRIMARY_REFERENCE}` | `known-failures` | Filename without extension |
| `{SPECIALTY_N}` | `Scene layout` | Bold keyword for the specialization |
| `{SPECIALTY_N_DESC}` | `Placing, moving, rotating, scaling Actors` | 1-line description |
| `{PRIMARY_WORKFLOW}` | `Actor Operations` | Name of the main workflow |
| `{PRIMARY_UE_CLASS}` | `EditorLevelLibrary` | Most-used UE class |

## Required Files After Scaffolding

```
Agents/{AgentName}/
├── SKILL.md                          ← generated from this template
└── references/
    └── known-failures.md             ← starter file (can be empty with header)
```

### known-failures.md Starter Content

```markdown
# Known Failures — {AGENT_DISPLAY_NAME}

> Append failure modes discovered during sessions here.
> Format: `### {Short Title}` + description + workaround.

(No failures recorded yet. This file grows with each session.)
```

