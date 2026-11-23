# GRID Skill Library

This folder contains built-in **Agent Skills** (`SKILL.md`) procedures. They are
original MIT-licensed skills for GRID v3.

GRID discovers:

- `skill_library/<name>/SKILL.md` — built-in skills (this folder)
- `skills/<name>/SKILL.md` — user skills; these override a built-in with the
  same name

Only `name` and `description` are injected into the prompt. The body is loaded
on demand with `skill_load`, and referenced files with `skill_read`.

## Importing Anthropic or community skills

1. Copy a skill folder, for example `anthropics/skills/skills/pdf`, into
   `skill_library/pdf`.
2. Keep its `LICENSE` or `NOTICE` file. The Agent Skills spec allows a per-skill
   `license` field.
3. Run `python grid_agent.py --check` and `skill_load pdf` to validate it.
4. Review any `scripts/` before letting GRID run them. Skills are code-like
   supply-chain content; do not auto-install from untrusted repositories.

The loader accepts the standard frontmatter fields: `name`, `description`,
`license`, `compatibility`, `metadata`, and the experimental `allowed-tools`.
