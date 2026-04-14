---
name: orphaned-files
description: >-
  Find files in a vault folder that are not referenced by any note. By default
  checks the configured attachments folder; the user can specify any folder.
  Use when asked to "find orphaned files", "find orphaned attachments",
  "find abandoned files", "clean up attachments", or "unused files".
---

# Orphaned Files

Scan a folder in the current Obsidian vault for files that no note references. Report-first: present findings, then confirm before any deletion.

## Vault Detection

```
VAULT_ROOT = the current working directory
```

Use the Read tool to read `.obsidian/app.json`. If the file does not exist, this is not an Obsidian vault — tell the user and stop. Parse the JSON to extract vault configuration (used below for target folder detection).

## Target Folder

Determine which folder to scan, in priority order:

1. **User-specified folder** — if the user names a specific folder (e.g., "check the Clippings folder"), use the Glob tool with pattern `**/FolderName/**` (note the trailing `/**` to recurse into subfolders) to find files inside it anywhere in the vault. The Glob tool only matches files, not directories, so you must glob for contents and derive the folder path from the results. If matches exist in multiple parent paths, ask the user which one. If no match, tell the user the folder was not found and stop. Do NOT list directories or suggest alternatives.
2. **Vault config** — use the `attachmentFolderPath` value from `.obsidian/app.json` (already read during vault detection). If the value is `./` or starts with `./`, this vault uses relative attachment paths — ask the user to specify a folder instead.
3. **Ask the user** — if `attachmentFolderPath` is not set in the config, tell the user: "No attachment folder is configured in this vault. Which folder should I check for orphaned files?" Do NOT suggest folder names, offer multiple-choice options, or search for common folder names. Wait for the user to type a folder name.

## Excluded Paths

Skip these directories when grepping for references (not when scanning the target folder):

- `.obsidian/`
- `.claude/`
- `.trash/`

## Tool Usage — MANDATORY

**Bash usage is prohibited** - use internal tools only.

1. **Use Glob** to find files.
2. **Use Grep** to search file contents.
3. **Use Read** to read file contents.

## Execution

Two phases: collect target files, then search for references.

### Phase 1 — Collect target files (orchestrator)

The Glob from the Target Folder step already found the files. Reuse that result — do NOT re-glob. Extract just the filename (last path component) from each path. This is the **target file list**.

### Phase 2 — Search for references (Sonnet subagents)

Dispatch Sonnet subagents to search the vault for references to each target file. Batch the files:

- **≤100 files**: dispatch 1 subagent with all filenames
- **>100 files**: split into batches of 100 and dispatch parallel subagents

**Prompt for each subagent:**

> Search the Obsidian vault at `{VAULT_ROOT}` for references to the following files. For each file, determine whether it is referenced by any note in the vault.
>
> **IMPORTANT: Use Grep to search content. Do NOT use Bash for grep, sed, awk, or cat.**
>
> **Files to check (filename → full path):**
> ```
> {BATCH_LIST}
> ```
>
> **How to search:** For each filename, use the Grep tool to search `*.md` files in `{VAULT_ROOT}` for that name. Use these Grep parameters:
> - `-i: true` for case-insensitive matching
> - `glob: "*.md"` to search only markdown files
> - `output_mode: "files_with_matches"` to get just the filenames that match
>
> **Excluding paths:** The Grep tool does not support exclude globs. After each Grep call, discard any results where the file path contains `.obsidian/`, `.claude/`, or `.trash/`. Also discard **self-references** — if searching for `Song 1`, ignore matches found in the file `Song 1.md` itself (a file's own content referencing its own name is not an inbound link).
>
> **What to search for:** Obsidian resolves links by filename, so searching for the filename is sufficient to catch all link forms:
> - For `.md` files: search for the filename **without** the `.md` extension (e.g., `Song 1`)
> - For all other files: search for the **full filename with extension** (e.g., `IMG_1234.jpeg`)
>
> This catches wikilinks (`[[Song 1]]`, `[[path/to/Song 1|alias]]`), embeds (`![[Song 1]]`), markdown links (`[text](Song 1.md)`), and frontmatter references (`link: "[[Song 1]]"`).
>
> **Search strategy:** One Grep call per file.
>
> **Return format:** Return a result for EVERY file in the batch, one per line:
> ```
> REFERENCED: Song 1.md (found in: Simple Set.md, Setlist.md)
> ORPHANED: Song 3.md
> ```
> This allows the orchestrator to verify results. List the first 5 referencing files for each referenced file.

### Phase 3 — Verify and report (orchestrator)

Collect results from all subagents. Review the `REFERENCED` and `ORPHANED` lines. If any result looks suspect (e.g., a commonly-named file reported as orphaned), spot-check with your own Grep call before including it in the report.

Present findings as a markdown table: `File | Path` followed by a short narrative /
summary of your findings

If no orphaned files found, say "No orphaned files found in {TARGET_FOLDER}."

### After reporting

If orphaned files were found, ask:

> "Found N orphaned file(s) in {TARGET_FOLDER} (total size: X). Would you like to delete them? (yes / no / let me review first)"

Only delete after explicit user confirmation. Move files to the vault's `.trash/` folder if it exists, otherwise use `rm` for confirmed files.

## Link Pattern Reference

This reference is included so the subagent understands all link forms in an Obsidian vault.

| Pattern | Example | Resolution |
|---------|---------|------------|
| Wikilink | `[[Puerto Vallarta, Mexico]]` | Search vault by filename |
| Aliased wikilink | `[[2022-04-18 Travel Log\|Hedd-Quez 2022]]` | Target is before the `\|` |
| Embedded file | `![[IMG_6787.jpeg]]` | Same as wikilink |
| Embedded with size/alias | `![[Untitled 4.png\|Untitled 4.png]]` | Target is before the `\|` |
| Markdown relative link | `[text](relative/path.md)` | Resolve relative to source file |
| Cross-vault link | `[text](obsidian://open?vault=Workbook&file=...)` | Not relevant for orphan detection |
| External URL | `[text](https://...)` | Not checked |
| Frontmatter wikilink | `place: "[[Puerto Vallarta, Mexico]]"` | Same as wikilink |
| Frontmatter string | `banner: Aguada Puerto Rico` | Implicit reference — not checked |

## Safety Rules

1. **Report before acting.** Always present the full list before offering to delete.
2. **Prefer trash over delete.** If `.trash/` exists in the vault root, move files there instead of permanently deleting.
3. **Respect user choice.** If the user declines, do nothing.
4. **Never modify note content.** This skill finds unreferenced files — it does not rewrite links or edit notes.
