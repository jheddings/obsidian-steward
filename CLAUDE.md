# CLAUDE.md

## Project

This is a Claude Code plugin containing vault maintenance skills for Obsidian. Skills
follow the [Agent Skills specification](https://agentskills.io/specification).

Each skill follows the Unix principle — **do one thing, and do it very well.** One
nameable job per skill; when a skill needs a second responsibility, write a new skill
instead of widening it. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full design
philosophy and conventions.

## Skill Structure

Each skill lives in `skills/<skill-name>/SKILL.md` with YAML frontmatter (`name`,
`description`) followed by the skill definition. Additional files go in `references/`,
`scripts/`, or `assets/` subdirectories as needed.

### Naming Rules

- Lowercase letters, numbers, and hyphens only
- Directory name must match the `name` field in frontmatter
- No leading/trailing hyphens, no consecutive hyphens

## Conventions

- Skills should use built-in tools (Glob, Grep, Read) over Bash commands wherever
  possible
- Bash is acceptable only when no built-in tool exists for the task (e.g.,
  `find -type d`, `rmdir`, `stat`)
- Skills that dispatch subagents must repeat tool usage constraints in the subagent
  prompt
- All skills use `.obsidian/app.json` via Read for vault detection
- Prefer the Obsidian CLI (`obsidian unresolved`, `orphans`, `backlinks`, `delete`, …)
  over reimplementing Obsidian's link resolution; keep custom logic only for what the
  CLI can't do
- CLI skills target the vault by name (`vault=<VAULT_NAME>`), fail fast on
  preconditions, and redirect large output to a temp file. Reuse the proven precondition
  block across skills rather than rewording it
- Destructive skills report before acting and route deletes through recoverable trash
  (`obsidian delete`, `.trash/`, or `git rm`); permanent deletion is opt-in only

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>
```

**Types:** `feat`, `fix`, `chore`, `docs`, `refactor`, `test`

**Scope:** Optional but encouraged (e.g., `feat(check-links): ...`,
`fix(orphaned-files): ...`)

## Branches

Use the same type prefixes:

```
<type>/<change-slug>
```

**Examples:** `feat/orphaned-notes`, `fix/wikilink-resolution`, `chore/update-readme`
