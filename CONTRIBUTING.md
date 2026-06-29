# Contributing

Thanks for helping improve **obsidian-steward**. This plugin is a collection of vault
maintenance skills for Obsidian, built around one guiding idea.

## Design philosophy: do one thing well

Each skill follows the Unix principle — **do one thing, and do it very well.** A skill
has a single, nameable job (`check-links` finds broken links; `empty-folders` finds
empty directories) and resists growing a second one. When a skill starts to need a
second responsibility, that is the signal to write a _new_ skill, not to widen an
existing one.

Concretely:

- **One purpose per skill.** If you can't state the job in one sentence, it's two
  skills.
- **Compose, don't conflate.** `check-links` reports; it never fixes. `orphaned-files`
  finds _and_ can remove, but removal is a confirmed, separate phase — not a side effect
  of finding.
- **Focused and efficient.** Keep `SKILL.md` short and scannable. Prefer the
  authoritative tool over hand-rolled logic (see _Prefer the Obsidian CLI_). Aim well
  under 500 words of prose; move heavy reference or reusable code into `references/` or
  `scripts/`.

## Skill structure

Each skill lives in `skills/<skill-name>/SKILL.md` with YAML frontmatter (`name`,
`description`) followed by the skill body. Supporting material goes in `references/`,
`scripts/`, or `assets/` subdirectories.

### Naming

- Lowercase letters, numbers, and hyphens only.
- The directory name must match the `name` field in frontmatter.
- No leading/trailing hyphens, no consecutive hyphens.

### Descriptions

The `description` is what Claude reads to decide whether to load the skill, so it must
describe **when to use it**, not what it does. Start with `Use when…` and pack in the
trigger phrases a user would actually type.

```yaml
# Good — triggering conditions
description: >-
    Use when asked to "find empty folders", "clean up folders", "remove empty
    directories", or "folder cleanup" in an Obsidian vault.

# Avoid — summarizes the workflow; Claude may follow the summary instead of the skill
description: Find empty folders, then confirm, then delete with rmdir.
```

## Conventions

### Prefer built-in tools over Bash

Use the **Glob**, **Grep**, and **Read** tools rather than shelling out to `find`,
`grep`, `rg`, `awk`, `sed`, `cat`, `head`, or `tail`. Bash is acceptable only when no
built-in tool covers the task — invoking the Obsidian CLI, `find -type d -empty`,
`rmdir`, `stat`. Skills that dispatch subagents must **repeat these tool constraints in
the subagent prompt**, since the subagent does not inherit them.

### Prefer the Obsidian CLI over reimplementing Obsidian

When a job is really "what does Obsidian think?", ask Obsidian. The desktop app's CLI
exposes the live link graph and metadata cache, so it resolves links, embeds, aliases,
and attachments exactly as Obsidian does — far more reliably than regex over file text.
Reach for it before hand-rolling resolution logic:

| Need                         | CLI command           | Used by          |
| ---------------------------- | --------------------- | ---------------- |
| Broken internal links        | `obsidian unresolved` | `check-links`    |
| Files with no incoming links | `obsidian orphans`    | `orphaned-files` |
| Backlinks to a file          | `obsidian backlinks`  | `file-dedupe`    |
| Trash-aware delete           | `obsidian delete`     | `orphaned-files` |

Run `obsidian --help` for the full command list.

The custom logic that remains should be only what the CLI _can't_ do — e.g.
`check-links` still searches the filesystem for cross-vault `obsidian://` links because
those reach into peer vaults the CLI cannot see.

### Obsidian CLI rules

Skills that use the CLI follow the same contract:

- **Target the vault by name.** The CLI resolves vaults by name against the running app,
  and several vaults can be open at once. Every call passes `vault=<VAULT_NAME>` — never
  rely on the implicit active vault.
- **Fail fast on preconditions.** Before doing real work, run
  `obsidian vault vault=<VAULT_NAME>` and confirm (a) the CLI exists, (b) the vault is
  open, and (c) the reported `path` equals the working directory. Stop with a clear
  message otherwise. Copy the proven _Preconditions — Obsidian CLI (fail fast)_ block
  from an existing skill rather than inventing new wording.
- **Keep large output out of context.** Redirect list commands to a temp file and Read
  it, rather than letting a thousand-line list flow back through the model.

### Vault detection

Every skill detects the vault the same way: read `.obsidian/app.json` with the Read
tool. If it doesn't exist, the working directory is not a vault — say so and stop.

### Report before acting; deletes must be recoverable

Maintenance skills are destructive by nature, so they share a safety posture:

- **Report first, act second.** Present the full findings (a table), then ask for
  explicit confirmation before any deletion. Never delete as a side effect of scanning.
- **Prefer recoverable removal.** Route deletes through the vault's trash
  (`obsidian delete`, a `.trash/` move, or `git rm`). Permanent deletion is opt-in and
  only on explicit user request.
- **Never modify note content** unless rewriting links _is_ the skill's stated job (only
  `file-dedupe` repoints links, and it does so before — and in the same commit as — any
  removal).

## Testing skills

Treat a skill like code: don't ship it untested. Run it against a real vault and confirm
it does the right thing — and the right _nothing_ when there's nothing to find. For
behavioral changes, verify the new path produces correct results before claiming done.
The `superpowers:writing-skills` skill describes the full test-first methodology.

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>
```

**Types:** `feat`, `fix`, `chore`, `docs`, `refactor`, `test`. **Scope** is optional but
encouraged (e.g. `feat(check-links): ...`, `fix(orphaned-files): ...`).

## Branches

Same type prefixes: `<type>/<change-slug>` — e.g. `feat/orphaned-notes`,
`fix/wikilink-resolution`, `chore/update-readme`.
