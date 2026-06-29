---
name: file-dedupe
description:
    Use when the vault has byte-identical duplicate files — redundant attachments or
    image copies left by an Apple Notes / Evernote import, iCloud churn, or repeated
    pastes. Triggers on "dedupe", "find duplicate files/images/attachments", "storage
    bloat", "collapse duplicate copies", or noticing copies named `foo-4.png`, `foo
    2.jpeg`.
---

# File Dedupe

## Overview

Imports and sync churn leave **byte-identical copies** of the same file under
disambiguated names (`img.png`, `img-4.png`, `img 2.png`). Each copy may be embedded by
a different note. The job: keep one canonical copy, repoint every backlink to it, and
remove the rest — **repointing and removal in the same commit**, so the git record is
never left with dangling embeds.

**Core principle: never delete a duplicate without first repointing the notes that link
it, and never act before the operator has seen the table.**

This dedupes only **exact byte matches** (SHA-256). It does not touch near-duplicates or
visually-similar images — those are judgment calls a hash can't make.

## Running

Run from inside the target vault — the working directory is the vault root, like the
other skills here. `scripts/dedupe.py` is standalone Python 3 with no third-party
dependencies, so it can also be invoked directly. See the README for plugin
installation.

## When to use

- Storage bloat from an Apple Notes / Evernote / Obsidian import
- A folder full of `name-N.ext` or `name N.ext` copies
- "Find duplicate images/attachments", "collapse duplicate files"

**Not for:** distinct files that merely share a name stem (comic issues
`Tart 12`/`Tart 13`, channels `KB0VJJ 2`, product variants). Those are not
byte-identical and the scanner ignores them. Confirm a suspected duplicate set is truly
the same bytes before treating it as one — a shared _name_ is not a duplicate.

## Procedure

1. **Scan** the scope (a folder, several paths, or the whole vault). The tool hashes
   every non-`.md` file, groups byte-identical sets, resolves backlinks across the
   _entire_ vault, picks a canonical copy per set, classifies each set, and writes a
   JSON plan (including each file's hash, for re-verification at apply time).

    ```
    scripts/dedupe.py [PATH ...] --vault VAULT_ROOT --plan-out PLAN.json
    ```

    No `PATH` → whole vault. `--vault` defaults to the cwd. `.git`, `.obsidian`,
    `.trash`, `.claude` and other dotfolders are always skipped.

    **No duplicates → done.** When the scan finds 0 sets it prints
    `No duplicate sets found in <scope>` and writes no plan. Report the vault is clean
    and stop — there is nothing to confirm or apply.

    **Backlinks (hybrid).** A built-in regex index over every `.md` always runs (fast,
    portable, headless). When the **Obsidian CLI** (`obsidian`) is on PATH, the scanner
    _also_ resolves the duplicate-set members through it — authoritative,
    per-exact-file, and it sees what Obsidian's metadataCache sees (aliases, true
    per-copy attribution). It targets the vault **by name** (`vault=<root folder name>`)
    and first verifies that name resolves to the scanned root — so it can't silently
    answer from whichever vault is active. If the vault isn't open in Obsidian (or the
    CLI is absent), it falls back to the regex index with a notice. It launches the
    desktop app and adds ~1–2s per member, so it runs only for the handful of
    duplicates. Pass `--no-cli` to force regex-only. The table header shows which source
    was used.

2. **Show the operator the table and confirm intent before deleting.** This is a
   required gate, not a courtesy — present the table (tier, keep, drop count,
   linked-from notes) and get an explicit go-ahead. The table groups itself:
   `intra-note`, then plain `cross-note`, then `cross-note ⚠` (the only ones that need
   eyeballing), then any `BLOCKED` sets. Focus the review on the ⚠ sets. **Relay the
   scan's `Removal:` line at this gate** — it states whether the drops will be
   recoverable (`.trash/` or `--use-git`) or **permanently deleted**, so the operator
   approves with the irreversibility in view. The full list of drop filenames for any
   set is in the plan JSON (the table shows counts only); surface it if the operator
   wants to see exactly which copies die.

3. **Apply** the reviewed plan — re-verifies each file's hash, repoints links, then
   removes the dropped files:

    ```
    scripts/dedupe.py --apply PLAN.json --vault VAULT_ROOT [--use-git] [--force]
    ```

    Pass the **same `--vault`** used at scan time (plan paths are vault-relative).
    Before deleting anything, apply re-hashes the keep and each drop and compares
    against the plan. A keep that changed → the whole set is skipped; a drop that
    changed or vanished → that drop is skipped (never deleted on stale bytes). This
    matters because scan→review→apply can straddle an iCloud sync. `BLOCKED` sets
    (referenced from `.canvas`/`.base`) are skipped automatically. Trim the plan first
    if the operator excluded sets (it's plain JSON — drop the unwanted entries).

    **Removal is recoverable by default, and the irreversible path is opt-in.** With
    `--use-git`, drops are `git rm`'d (recoverable from history) — apply _aborts_ if the
    vault isn't a git work tree rather than silently no-op'ing. Otherwise, if the vault
    has a `.trash/` folder, drops are _moved_ there (preserving their subpath, never
    clobbering an existing trashed file). When there is **no `.trash/` and not
    `--use-git`**, apply **refuses** to delete and tells you how to make it recoverable;
    pass `--force` to permanently delete anyway. The scan summary's `Removal:` line
    predicts which of these will happen.

4. **Commit removal + repoints together** as one bundle, so the history never records a
   dangling embed — never delete-then-repoint across two commits.

## Tiers — the judgment the hash can't make

The scanner labels each set so the operator knows where to look:

| Tier             | Meaning                                                                                                                                                        | Action                               |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| **intra-note**   | All copies are embedded by **one** note (base + its `-N` copies). Pure import bloat.                                                                           | Safe to collapse.                    |
| **cross-note**   | 2+ notes, but at most one is a non-daily note — the rest are daily-note captures (the same image logged in a journal entry _and_ filed in its reference home). | Low risk; skim.                      |
| **cross-note ⚠** | **Two or more distinct non-daily notes** share these bytes.                                                                                                    | **Eyeball the actual images first.** |
| **BLOCKED**      | A copy is referenced from a `.canvas`/`.base` file, which `apply` can't repoint.                                                                               | Auto-excluded; resolve by hand.      |

The risk split keys off **daily notes**, whose folder and date format are read from the
vault's own config (`.obsidian/daily-notes.json`) — not assumed — so a vault that files
journals under `Journal/` is recognized just as well as one using `Notes/`. If a vault
has no daily-notes config, nothing is treated as a daily and more sets land in `⚠`
review (the safe direction). An image in a daily note is almost always a capture, so a
journal entry plus one reference home is the benign capture-and-file pattern (plain
`cross-note`). The `⚠` flag fires only when **two real reference/project notes** couple
onto one file — e.g. the same photo in a Winchester ammo note _and_ a Remington ammo
note. Identical bytes across unrelated subjects can mean a **mis-filed attachment**, not
bloat — collapsing would mask the error. Render the image and look before merging. When
two related notes legitimately share an image (a banner reused across a series, a
parent/child note pair), the `⚠` is a false positive and collapse is fine — a two-second
glance confirms it.

The scanner can't tell "shared asset" from "mis-file" — it tells you _where the hash
can't decide_. The eyeballing is yours.

## Canonical selection

Deterministic, in priority order: **un-suffixed name** > **most-referenced** (fewest
repoints, by the authoritative backlink count) > **shortest** > **lexically first**.
This keeps human names (`IMG_8657.jpeg`) over hashes and widely-used originals over
stray copies. Tie-breaks are stable across runs — never let the kept copy depend on
filesystem ordering.

## Link forms handled

Repointing covers wikilinks/embeds (`[[x]]`, `![[x]]`) and markdown links (`[t](x)`,
`![t](x)`), each kept in its original syntax. Markdown targets are matched and rewritten
through their real on-disk name: angle-bracket dests (`[t](<my file.png>)`),
percent-encoded spaces (`my%20file.png`), and quoted titles (`[t](x.png "title")`) are
all resolved and preserved. The one form not handled is a markdown link whose
destination embeds a literal `)` or a parenthesis-style `(title)` — rare, and such a
referrer simply isn't matched (so re-scan or fix it by hand if you use that style).

## Common mistakes

- **Deleting before repointing.** Leaves dangling `![[...]]` embeds. Always `--apply`
  (which repoints first) or repoint by hand in the same commit.
- **Trusting names over bytes.** `Tart 12.md` vs `Tart 13.md` look like dupes but are
  distinct issues. Only hash-identical files are duplicates.
- **Silently collapsing `cross-note ⚠` sets.** A mis-filed photo hides as a "duplicate."
  Eyeball those images first.
- **Skipping the confirmation table.** The operator owns the delete decision.
- **Re-running apply on a stale plan after edits.** Apply re-hashes and skips changed
  files, but a plan whose _backlinks_ are stale (notes moved/renamed since scan) can
  mis-repoint — re-scan if the vault shifted materially.
- **Splitting removal and repoint across commits.** One bundle.

Run `scripts/dedupe.py --help` for all flags.
