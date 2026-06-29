---
name: check-links
description: >-
    Use when asked to "check links", "find broken links", "verify links", or "link
    audit" in an Obsidian vault. Covers wikilinks, embeds, markdown links, attachments,
    and cross-vault obsidian:// links.
---

# Check Links

Report broken links in the current Obsidian vault. This skill is report-only — it never
modifies note content.

Internal links (wikilinks, embeds, markdown links, attachment references) are resolved
with the Obsidian CLI (`obsidian unresolved`), which reads Obsidian's live link graph.
That means path-style links, aliases, frontmatter links, and vault-wide attachment
resolution are all handled authoritatively — no regex parsing of link syntax. Because
the CLI talks to the running app, Obsidian must be **running** with **this vault open**
(see Preconditions).

Cross-vault `obsidian://` links reach into _peer_ vaults the CLI cannot see, so those
are the one form checked separately, with file search.

## Vault Detection

```
VAULT_ROOT = the current working directory
VAULT_NAME = the last path component of VAULT_ROOT (the folder name)
```

Use the Read tool to read `.obsidian/app.json`. If the file does not exist, this is not
an Obsidian vault — tell the user and stop.

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

## Excluded Paths

When checking cross-vault links, skip these directories: `.obsidian/`, `.claude/`,
`.trash/`. (The CLI already ignores them for internal links.)

## Execution

### Phase 1 — Internal broken links (Obsidian CLI)

Run the CLI, redirecting to a temp file to keep the (potentially large) list out of
context:

```
obsidian unresolved vault=<VAULT_NAME> verbose format=json > /tmp/obsidian-unresolved.json
```

`obsidian unresolved` lists every internal link target that does not resolve to a file
in the vault — wikilinks, embeds, markdown links, and attachment references alike. Use
the Read tool to read the temp file. Each entry has:

- `link` — the unresolved target
- `count` — how many times it is referenced
- `sources` — comma-separated source files that reference it

Report as a markdown table: `Source File | Broken Link`. Expand each entry to one row
per source file. If the array is empty, say "No broken internal links found."

### Phase 2 — Cross-vault `obsidian://` links

Dispatch ONE subagent using the Agent tool with `model: "sonnet"`.

**Tool usage — the subagent MUST follow these rules:** Use **Glob** to find files and
verify existence, **Grep** to search content, **Read** to read files. Do NOT use Bash
for `find`, `grep`, `sed`, `awk`, or `cat`. Bash is only allowed for writing temp files.

**Prompt:**

> Search the Obsidian vault at `{VAULT_ROOT}` for broken cross-vault `obsidian://`
> links.
>
> **IMPORTANT: Use Glob to find files, Grep to search content, Read to read files. Do
> NOT use Bash for find, grep, sed, awk, or cat. Bash is only allowed for writing temp
> files. Use Glob to check if files exist.**
>
> **Step 1 — Check for obsidian:// links.** Use the Grep tool with pattern
> `obsidian://`, output_mode `content`, glob `*.md`, path `{VAULT_ROOT}`. Manually
> exclude any results with `.obsidian/`, `.claude/`, or `.trash/` in the path. If no
> results, report "No cross-vault links found." and stop here.
>
> **Step 2 — Discover peer vaults.** Only if Step 1 found links: use the Glob tool with
> pattern `*/.obsidian` in the parent directory of `{VAULT_ROOT}`. Exclude
> `{VAULT_ROOT}` itself. Build a map of `vault_name → path` from any matches. Also add
> the current vault to this map (name = `{VAULT_ROOT}` directory name → `{VAULT_ROOT}`),
> since files can migrate back into the source vault.
>
> **Step 3 — Parse and verify.** From the Grep results, parse each `obsidian://` URL to
> extract `vault` and `file` parameters. For each link:
>
> 1. URL-decode the `file` parameter.
> 2. If the vault name matches a known vault, use Glob to check if
>    `{vault_path}/{decoded_file}` or `{vault_path}/{decoded_file}.md` exists.
> 3. If the vault name doesn't match any known vault, flag as "unknown vault".
> 4. If the URL is malformed, flag as "malformed".
>
> **Step 4 — Report.** Return a markdown table:
> `Source File | Target Vault | Target File | Status`. Only include non-OK rows. If all
> valid, say "All cross-vault links are valid." If no peer vaults were found, note that
> cross-vault links could not be verified.

### Combine reports

Present results under a `## Broken Links Report` heading, with an **Internal Links**
subsection (Phase 1) and a **Cross-Vault Links** subsection (Phase 2). If both found
nothing, say "No broken links found." Include a summary line:
`Found N broken link(s) across M file(s).`

## Link Pattern Reference

| Pattern              | Example                                           | Resolution                         |
| -------------------- | ------------------------------------------------- | ---------------------------------- |
| Wikilink             | `[[Meeting Notes]]`                               | CLI (`unresolved`)                 |
| Aliased wikilink     | `[[2024-01-15 Log\|Q1 Review]]`                   | CLI (`unresolved`)                 |
| Embedded file        | `![[IMG_6787.jpeg]]`                              | CLI (`unresolved`)                 |
| Markdown link        | `[text](relative/path.md)`                        | CLI (`unresolved`)                 |
| Frontmatter wikilink | `place: "[[Meeting Notes]]"`                      | CLI (`unresolved`)                 |
| Cross-vault link     | `[text](obsidian://open?vault=Workbook&file=...)` | File search (Phase 2)              |
| External URL         | `[text](https://...)`                             | Not checked (not an internal link) |

## Safety Rules

1. **Never modify note content.** This skill finds broken links — it does not rewrite or
   fix them.
2. **Internal resolution is the CLI's job.** Trust `obsidian unresolved` for wikilinks,
   embeds, markdown links, and attachments — do not second-guess it with regex.
3. **Cross-vault links are best-effort.** If a peer vault is not accessible, report the
   links as unverifiable rather than broken.
