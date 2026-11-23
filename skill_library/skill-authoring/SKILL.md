---
name: skill-authoring
description: Create or review a portable SKILL.md procedure for GRID, Claude Code, Codex or another Agent Skills runtime. Use when the user wants to capture a repeatable workflow as a skill.
license: MIT
metadata:
  author: GRID
  version: "1.0"
---
# Skill Authoring

A skill is a folder containing `SKILL.md` plus optional `scripts/`,
`references/` and `assets/`. The format is the Agent Skills open standard.

## Required frontmatter

```yaml
---
name: lowercase-hyphen-name
description: What it does and when to use it. Include trigger words.
---
```

- `name` must match the folder, use lowercase letters/digits/single hyphens,
  and be 64 characters or fewer.
- `description` must be 1-1024 characters and should say both **what** and
  **when**.
- Optional: `license`, `compatibility`, `metadata`, `allowed-tools`.

## Writing the body

1. State when to use the skill and when not to.
2. Give ordered steps with exact tool names or commands.
3. Include one short example and the expected output.
4. Put long reference material in `references/`, not in SKILL.md.
5. Keep SKILL.md under 500 lines.
6. Never put secrets, tokens or private data in a skill.
7. Treat scripts as code: document dependencies and require user approval
   before running anything downloaded from the internet.

## Validation

- The folder name and `name` must match.
- Frontmatter must parse as YAML.
- `skill_load <name>` must return the body.
- `skill_read <name>/references/...` must stay inside the skill folder.
- Test the workflow once with a real task before publishing.

## Output

Return the full folder layout and the SKILL.md content. If the skill needs a
script, keep it self-contained and show the exact command to run it.
