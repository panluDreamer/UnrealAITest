# Validation Checklist — Agent & Skill Definitions

> Run this checklist after creating or updating any Agent or Skill.
> All items must pass before syncing to the engine.

---

## Agent Validation

### SKILL.md Structure

- [ ] **YAML frontmatter** exists and is delimited by `---`
- [ ] **`name`** field is `ue-{kebab-case}` (e.g. `ue-audio-designer`)
- [ ] **`description`** field is present and non-empty
- [ ] **`description`** includes `MUST be triggered when:` with at least 3 bullet items
- [ ] **`description`** includes `On activation: reads ../RULE.md`
- [ ] **`description`** ends with `Loads shared RULE.md on activation.`

### Markdown Body

- [ ] **`# {Name} Agent`** heading matches the agent display name
- [ ] **Activation Checklist** section exists
- [ ] Activation Checklist step 1 reads `../RULE.md`
- [ ] Activation Checklist step 2+ reads agent-specific `references/*.md`
- [ ] **Role** section lists 3-5 bold specializations with descriptions
- [ ] **Key Domain Knowledge** section exists with at least one subsection
- [ ] **When to Use Each Tool** table exists with columns: Task | Tool | Notes
- [ ] Tool table references at least: `exec_python`, one skill, one MCP tool
- [ ] **Self-Bootstrap** section exists
- [ ] Self-Bootstrap references the agent's own `references/` files
- [ ] Self-Bootstrap mentions proposing updates to `../RULE.md` for general safety issues

### File System

- [ ] Directory is PascalCase: `Agents/{AgentName}/`
- [ ] `SKILL.md` exists at `Agents/{AgentName}/SKILL.md`
- [ ] `references/` directory exists at `Agents/{AgentName}/references/`
- [ ] `references/known-failures.md` exists (may be empty starter)
- [ ] No stale or orphaned files in the directory

### Registration

- [ ] Agent name is in `setup.py` `AGENTS` list (exact PascalCase match)
- [ ] Agent name is alphabetically sorted in the list (convention, not required)

---

## Skill Validation

### SKILL.md Structure

- [ ] **YAML frontmatter** exists and is delimited by `---`
- [ ] **`name`** field matches directory name exactly (e.g. `ue-audio-tools`)
- [ ] **`description`** field is present and non-empty
- [ ] **`description`** includes trigger phrases (when to invoke)
- [ ] **`allowed-tools`** field lists only required tools

### Markdown Body

- [ ] **`# {Title}`** heading is descriptive
- [ ] **Overview** or introductory section explains purpose
- [ ] **Workflow steps** are numbered and actionable
- [ ] Each step has enough detail for autonomous execution
- [ ] **Output** section describes what gets created and where (if applicable)
- [ ] No references to non-existent files or tools

### File System

- [ ] Directory is kebab-case with `ue-` prefix: `Skills/{skill-name}/`
- [ ] `SKILL.md` exists at `Skills/{skill-name}/SKILL.md`
- [ ] `references/` directory exists (even if empty)
- [ ] If `scripts/` exists: scripts have proper shebang and are executable
- [ ] No stale or orphaned files

### Registration

- [ ] Skill name is in `setup.py` `SKILLS` list (exact kebab-case match)
- [ ] Skill name is alphabetically sorted in the list (convention, not required)

---

## Cross-Component Checks

- [ ] **No name collisions** — new name doesn't conflict with existing agents/skills
- [ ] **No domain overlap** — if the domain overlaps with an existing agent, consider extending it instead
- [ ] **RULE.md unchanged** — unless the user explicitly approved a change
- [ ] **setup.py is valid Python** — no syntax errors after editing

---

## Sync Verification

After running `python setup.py`:

- [ ] Symlink/junction created at `Engine/.{client}/agents/{AgentName}/` (for agents)
- [ ] Symlink/junction created at `Engine/.{client}/skills/{skill-name}/` (for skills)
- [ ] `SKILL.md` readable via the symlink: `cat Engine/.{client}/agents/{AgentName}/SKILL.md`
- [ ] `python setup.py --check` passes with no FAIL items

---

## Quick Validation Script

Run this one-liner to verify YAML frontmatter is parseable:

```bash
python -c "
import re, sys
text = open(sys.argv[1]).read()
m = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
if not m: print('FAIL: no YAML frontmatter'); sys.exit(1)
yaml_text = m.group(1)
if 'name:' not in yaml_text: print('FAIL: missing name field'); sys.exit(1)
if 'description:' not in yaml_text: print('FAIL: missing description field'); sys.exit(1)
print('OK: frontmatter valid')
" path/to/SKILL.md
```
