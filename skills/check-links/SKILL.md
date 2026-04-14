---
name: check-links
description: >-
    Find broken links in an Obsidian vault: wikilinks, markdown relative links, and
    cross-vault obsidian:// links. Use when asked to "check links", "find broken links",
    "verify links", or "link audit".
---

# Check Links

Scan the current Obsidian vault for broken links and report findings. This skill is
report-only — it never modifies note content.

## Vault Detection

```
VAULT_ROOT = the current working directory
```

Use the Read tool to read `.obsidian/app.json`. If the file does not exist, this is not
an Obsidian vault — tell the user and stop.

### Peer Vaults

Peer vault discovery only happens if `obsidian://` links are found in the vault (see
Subagent 3). Do NOT search for peer vaults proactively — only look outside `VAULT_ROOT`
when cross-vault links need to be resolved.

## Excluded Paths

Skip these directories in all checks:

- `.obsidian/`
- `.claude/`
- `.trash/`

## Tool Usage — MANDATORY

Subagents MUST follow these rules:

1. **Use Glob** to find files. NEVER use `find` in Bash.
2. **Use Grep** to search file contents. NEVER use `grep`, `rg`, or `awk` in Bash.
3. **Use Read** to read file contents. NEVER use `cat`, `head`, or `tail` in Bash.
4. **Bash is allowed ONLY for:** writing/reading temp files and simple `test -f`
   existence checks during the final verification step. No pipelines, no `sed`, no
   `awk`, no `perl`.

Agents that use Bash for file discovery or content search are doing it wrong.

---

## Execution

Dispatch THREE parallel subagents using the Agent tool, one per link format. All use
`model: "sonnet"`.

### Subagent 1: Wikilinks

**Prompt:**

> Search the Obsidian vault at `{VAULT_ROOT}` for broken wikilinks.
>
> **IMPORTANT: Use Glob to find files, Grep to search content, Read to read files. Do
> NOT use Bash for find, grep, sed, awk, or cat. Bash is only allowed for writing temp
> files and running `test -f`.**
>
> **Step 1 — Collect all wikilink targets.** Use the Grep tool:
>
> - Pattern: `\[\[([^\]]+)\]\]` with output_mode `content`, glob `*.md`, path
>   `{VAULT_ROOT}`
> - Manually exclude any results with `.obsidian/`, `.claude/`, or `.trash/` in the path
>
> From the Grep output, parse out all wikilink targets. Handle these forms:
>
> - `[[target]]` → `target`
> - `[[target|alias]]` → `target` (before the first `|`)
> - `[[target\|alias]]` → `target` (the `\|` is an escaped pipe used inside markdown
>   table cells — strip the backslash, then split on `|`)
> - `![[target]]` → `target` (strip `!`)
> - `![[target|size]]` → `target` (before `|`)
> - Frontmatter values like `place: "[[target]]"` → `target`
>
> For targets containing `/`, extract only the last path component (filename). Build a
> list of `source_file → target` pairs.
>
> **Step 2 — Collect all existing filenames.** Use the Glob tool with pattern `**/*` at
> `{VAULT_ROOT}` to get all files. Extract just the filename (last path component) from
> each result. Also build a set of `.md` basenames (filename without `.md` extension).
>
> **Step 3 — Find broken links.** Compare the two lists in memory (or write to temp
> files and use a simple Bash comparison). A wikilink target is broken if no file with
> that exact name exists anywhere in the vault (checking both with and without `.md`
> extension).
>
> **Step 4 — Report.** For each broken target, include which source files reference it.
> Return a markdown table: `Source File | Link Target`. Only broken links. If none, say
> "No broken wikilinks found."

### Subagent 2: Markdown Relative Links

**Prompt:**

> Search the Obsidian vault at `{VAULT_ROOT}` for broken markdown relative links.
>
> **IMPORTANT: Use Glob to find files, Grep to search content, Read to read files. Do
> NOT use Bash for find, grep, sed, awk, or cat. Bash is only allowed for writing temp
> files and running `test -f`.**
>
> **Step 1 — Extract all relative links.** Use the Grep tool:
>
> - Pattern: `\]\([^)]+\)` with output_mode `content`, glob `*.md`, path `{VAULT_ROOT}`
> - Manually exclude any results with `.obsidian/`, `.claude/`, or `.trash/` in the path
> - From the results, parse out the URL portion from `](URL)`
> - Filter OUT any URL that starts with `http://`, `https://`, `obsidian://`, or `#`
> - Build a list of `source_file → relative_target` pairs
>
> **Step 2 — Verify each link.** For each pair:
>
> 1. Resolve the relative path against the source file's directory. Use `test -f` in
>    Bash to check if the resolved path exists.
> 2. If the file is NOT found relative to the source, extract the filename (last path
>    component) and use Glob with pattern `**/{filename}` at `{VAULT_ROOT}` to search
>    vault-wide. Obsidian resolves attachments vault-wide, not just relative to the
>    note's folder.
> 3. Only mark as broken if both the relative check AND the vault-wide search fail.
>
> **Step 3 — Report.** Return a markdown table: `Source File | Target Path`. Only broken
> links. If none, say "No broken relative links found."

### Subagent 3: Cross-Vault Links

**Prompt:**

> Search the Obsidian vault at `{VAULT_ROOT}` for broken cross-vault `obsidian://`
> links.
>
> **IMPORTANT: Use Glob to find files, Grep to search content, Read to read files. Do
> NOT use Bash for find, grep, sed, awk, or cat. Bash is only allowed for `test -f`
> existence checks.**
>
> **Step 1 — Check for obsidian:// links.** Use the Grep tool:
>
> - Pattern: `obsidian://` with output_mode `content`, glob `*.md`, path `{VAULT_ROOT}`
> - Manually exclude any results with `.obsidian/` or `.claude/` in the path
>
> If no results, report "No cross-vault links found." and stop here.
>
> **Step 2 — Discover peer vaults.** Only if Step 1 found links: use the Glob tool with
> pattern `*/.obsidian` in the parent directory of `{VAULT_ROOT}`. Exclude
> `{VAULT_ROOT}` itself. Build a map of `vault_name → path` from any matches.
>
> **Step 3 — Parse and verify.** From the Grep results, parse each `obsidian://` URL to
> extract `vault` and `file` parameters. For each link:
>
> 1. URL-decode the `file` parameter
> 2. If the vault name matches a discovered peer vault, use `test -f` in Bash to check
>    if `{peer_vault_path}/{decoded_file}` or `{peer_vault_path}/{decoded_file}.md`
>    exists
> 3. If vault name doesn't match any peer vault, flag as "unknown vault"
> 4. If URL is malformed, flag as "malformed"
>
> **Step 4 — Report.** Return a markdown table:
> `Source File | Target Vault | Target File | Status`. Only include non-OK rows. If all
> valid, say "All cross-vault links are valid." If no peer vaults were found, note that
> cross-vault links could not be verified.

### After All Subagents Return

Combine the three reports under a `## Broken Links Report` heading with subsections for
each link type. If all three found nothing, say "No broken links found."

Include a summary line: `Found N broken link(s) across M file(s).`

---

## Link Pattern Reference

This reference is included so any model executing this skill understands all link forms
in an Obsidian vault.

| Pattern                  | Example                                           | Resolution                          |
| ------------------------ | ------------------------------------------------- | ----------------------------------- |
| Wikilink                 | `[[Meeting Notes]]`                               | Search vault by filename            |
| Aliased wikilink         | `[[2024-01-15 Project Log\|Q1 Review]]`           | Target is before the `\|`           |
| Aliased wikilink (table) | `[[Jane Smith\|Smith]]`                           | Strip `\` before `\|`, then split   |
| Embedded file            | `![[IMG_6787.jpeg]]`                              | Same as wikilink                    |
| Embedded with size/alias | `![[Untitled 4.png\|Untitled 4.png]]`             | Target is before the `\|`           |
| Markdown relative link   | `[text](relative/path.md)`                        | Resolve relative to source file     |
| Cross-vault link         | `[text](obsidian://open?vault=Workbook&file=...)` | Decode file param, check peer vault |
| External URL             | `[text](https://...)`                             | Not checked                         |
| Frontmatter wikilink     | `place: "[[Meeting Notes]]"`                      | Same as wikilink                    |
| Frontmatter string       | `banner: Sunset Beach Landscape`                  | Implicit reference — not checked    |

## Safety Rules

1. **Never modify note content.** This skill finds broken links — it does not rewrite or
   fix them.
2. **Wikilink resolution is by filename.** A link `[[path/to/file]]` is valid as long as
   `file.md` (or `file` with any extension) exists anywhere in the vault. Do not report
   it as broken just because the path component is wrong.
3. **Attachment resolution is vault-wide.** Obsidian resolves images and attachments
   across the entire vault, not just relative to the referencing note. A relative link
   is only broken if the target file does not exist anywhere in the vault.
4. **Cross-vault links are best-effort.** If a peer vault is not accessible, report the
   links as unverifiable rather than broken.
