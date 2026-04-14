# CLAUDE.md

## Project

This is a Claude Code plugin containing vault maintenance skills for Obsidian. Skills
follow the [Agent Skills specification](https://agentskills.io/specification).

## Skill Structure

Each skill lives in `skills/<skill-name>/SKILL.md` with YAML frontmatter (`name`,
`description`) followed by the skill definition. Additional files go in `references/`,
`scripts/`, or `assets/` subdirectories as needed.

### Naming Rules

- Lowercase letters, numbers, and hyphens only
- Directory name must match the `name` field in frontmatter
- No leading/trailing hyphens, no consecutive hyphens

## Conventions

- Skills should use built-in tools (Glob, Grep, Read) over Bash commands wherever possible
- Bash is acceptable only when no built-in tool exists for the task (e.g., `find -type d`,
  `rmdir`, `stat`)
- Skills that dispatch subagents must repeat tool usage constraints in the subagent prompt
- All skills use `.obsidian/app.json` via Read for vault detection

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>
```

**Types:** `feat`, `fix`, `chore`, `docs`, `refactor`, `test`

**Scope:** Optional but encouraged (e.g., `feat(check-links): ...`, `fix(orphaned-files): ...`)

## Branches

Use the same type prefixes:

```
<type>/<change-slug>
```

**Examples:** `feat/orphaned-notes`, `fix/wikilink-resolution`, `chore/update-readme`
