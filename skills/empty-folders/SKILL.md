---
name: empty-folders
description: >-
    Find and optionally remove empty folders in an Obsidian vault. Use when asked to
    "find empty folders", "clean up folders", "remove empty directories", or "folder
    cleanup".
---

# Empty Folders

Scan the current Obsidian vault for empty directories. Report-first: present findings,
then confirm before any deletion.

## Vault Detection

```
VAULT_ROOT = the current working directory
```

Use the Read tool to read `.obsidian/app.json`. If the file does not exist, this is not
an Obsidian vault — tell the user and stop.

## Execution

No subagent needed — the orchestrator handles this directly.

### Step 1 — Find empty directories

Run this single Bash command:

```
find "{VAULT_ROOT}" -type d -empty -not -path "*/.*"
```

This finds all empty directories while excluding all hidden directories (`.obsidian/`,
`.claude/`, `.trash/`, `.git/`, etc.) in one pass. Do NOT modify this command or add
additional flags.

### Step 2 — Report

Present any results as a markdown list showing paths relative to the vault root.

If none found, say "No empty folders found."

### Step 3 — Confirm and remove

If empty folders were found, ask:

> "Found N empty folder(s). Remove them? (yes / no / let me review first)"

Only delete after explicit user confirmation. Use `rmdir` for each confirmed folder —
never `rm -rf`.

## Safety Rules

1. **Report before acting.** Always present the full list before offering to delete.
2. **Use `rmdir` only.** This ensures only truly empty directories are removed. Never
   use `rm -rf` or `find -delete`.
3. **Respect user choice.** If the user declines, do nothing.
