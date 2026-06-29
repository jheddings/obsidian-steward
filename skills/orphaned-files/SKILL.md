---
name: orphaned-files
description: >-
    Use when asked to "find orphaned files", "find orphaned attachments", "find
    abandoned files", "clean up attachments", or "unused files" in an Obsidian vault —
    files in a folder that no note references. Defaults to the configured attachments
    folder; the user can name any folder.
---

# Orphaned Files

Scan a folder in the current Obsidian vault for files that no note references.
Report-first: present findings, then confirm before any deletion.

References are resolved with the Obsidian CLI (`obsidian orphans`), which uses
Obsidian's live link graph — including embeds and frontmatter links — rather than text
matching. This is authoritative, but it requires Obsidian to be **running** with **this
vault open**. See Preconditions.

## Vault Detection

```
VAULT_ROOT = the current working directory
VAULT_NAME = the last path component of VAULT_ROOT (the folder name)
```

Use the Read tool to read `.obsidian/app.json`. If the file does not exist, this is not
an Obsidian vault — tell the user and stop. Parse the JSON to extract vault
configuration (used below for target folder detection).

## Preconditions — Obsidian CLI (fail fast)

The CLI talks to the running Obsidian app and resolves a vault by **name**, not by the
current directory. Multiple vaults can be open at once, so every CLI call MUST pass
`vault=<VAULT_NAME>` to target this vault explicitly — never rely on the implicit active
vault.

Confirm the vault is reachable before doing anything else:

```
obsidian vault vault=<VAULT_NAME>
```

This prints `name` and `path` (tab-separated). Handle three failure cases, each by
stopping with the matching message:

1. **`obsidian` command not found** — the Obsidian CLI is unavailable. Tell the user
   this skill requires the Obsidian desktop app's CLI (`/Applications/Obsidian.app`) and
   stop.
2. **Errors / "not found" / hangs** — the vault is not open (or Obsidian is not
   running). Tell the user to open `{VAULT_NAME}` in Obsidian and retry, then stop.
3. **`path` ≠ `VAULT_ROOT`** — the name resolves to a different vault on disk. Tell the
   user: "`{VAULT_NAME}` resolves to `{path}` in Obsidian, but this skill is running in
   `{VAULT_ROOT}`." Then stop.

Only proceed once `obsidian vault vault=<VAULT_NAME>` reports a `path` equal to
`VAULT_ROOT`.

## Target Folder

Determine which folder to scan, in priority order. The result is a **vault-relative
folder path** (e.g. `Attachments` or `Meta/Files`).

1. **User-specified folder** — if the user names a specific folder (e.g., "check the
   Clippings folder"), use the Glob tool with pattern `**/FolderName/**` (note the
   trailing `/**` to recurse into subfolders) to find files inside it anywhere in the
   vault. The Glob tool only matches files, not directories, so you must glob for
   contents and derive the folder path from the results. If matches exist in multiple
   parent paths, ask the user which one. If no match, tell the user the folder was not
   found and stop. Do NOT list directories or suggest alternatives.
2. **Vault config** — use the `attachmentFolderPath` value from `.obsidian/app.json`
   (already read during vault detection). If the value is `./` or starts with `./`, this
   vault uses relative attachment paths — ask the user to specify a folder instead.
3. **Ask the user** — if `attachmentFolderPath` is not set in the config, tell the user:
   "No attachment folder is configured in this vault. Which folder should I check for
   orphaned files?" Do NOT suggest folder names, offer multiple-choice options, or
   search for common folder names. Wait for the user to type a folder name.

## Tool Usage — MANDATORY

- **Use Bash** only to invoke the `obsidian` CLI (`obsidian vault`, `obsidian orphans`,
  `obsidian delete`), always with `vault=<VAULT_NAME>`. Do NOT use Bash for `grep`,
  `sed`, `awk`, `cat`, or file searching.
- **Use Glob** to list files in the target folder.
- **Use Read** to read file contents (including the orphans output file).

## Execution

### Phase 1 — List the folder's files

Use the Glob tool with pattern `**/<target-folder>/**` to list every file inside the
target folder. Convert each result to a **vault-relative path** by stripping the
`VAULT_ROOT/` prefix. This is the **folder file set**. (For a user-specified folder, the
Glob from the Target Folder step already produced this — reuse it.)

### Phase 2 — List the vault's orphans

Run the Obsidian CLI, redirecting to a temp file to keep the (potentially large) list
out of context:

```
obsidian orphans vault=<VAULT_NAME> > /tmp/obsidian-orphans.txt
```

`obsidian orphans` lists every file in the vault with no incoming links — attachments
and notes alike — one vault-relative path per line. Use the Read tool to read the temp
file. This is the **orphan set**.

### Phase 3 — Intersect and report

The orphaned files in the target folder are the **intersection** of the folder file set
(Phase 1) and the orphan set (Phase 2): paths that appear in both. No reference
searching is needed — `orphans` already accounts for all link forms.

Present findings as a markdown table: `File | Path` followed by a short narrative /
summary of your findings.

If the intersection is empty, say "No orphaned files found in {TARGET_FOLDER}."

### After reporting

If orphaned files were found, ask:

> "Found N orphaned file(s) in {TARGET_FOLDER} (total size: X). Would you like to delete
> them? (yes / no / let me review first)"

Only delete after explicit user confirmation. Delete each confirmed file with the
Obsidian CLI:

```
obsidian delete path=<vault-relative-path> vault=<VAULT_NAME>
```

`obsidian delete` honors the vault's own "Deleted files" setting (system trash, the
vault's local `.trash/` folder, or permanent) — so deletions follow whatever recovery
behavior the user configured in Obsidian, instead of this skill guessing. Pass the
`permanent` flag only if the user explicitly asks to skip the trash.

## Safety Rules

1. **Report before acting.** Always present the full list before offering to delete.
2. **Deletion goes through Obsidian.** Use `obsidian delete`, which routes through the
   vault's configured trash. Never `rm` files directly, and never pass `permanent`
   unless the user explicitly asks for it.
3. **Respect user choice.** If the user declines, do nothing.
4. **Never modify note content.** This skill finds unreferenced files — it does not
   rewrite links or edit notes.
