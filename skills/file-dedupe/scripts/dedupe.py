#!/usr/bin/env python3
"""Find byte-identical duplicate files in an Obsidian vault, map their
backlinks, and (optionally) collapse each duplicate set onto one canonical
copy while repointing every wikilink.

Two modes:
  scan   (default) — hash files in scope, group byte-identical sets, classify
                     each set, print a review table, and write a JSON plan.
  apply  --plan P  — execute a plan: re-verify each file's hash, repoint
                     backlinks, then remove the redundant copies. Never
                     deletes without an explicit plan, never deletes a file
                     whose bytes changed since the scan.

Backlinks are indexed across the WHOLE vault (links resolve by basename, so a
duplicate in a scanned subfolder may be referenced from anywhere). Scan SCOPE
only limits which files are hashed for duplicates.

Two backlink sources, used together (hybrid):
  * A built-in regex index over every .md file — fast, portable, always runs.
  * The Obsidian CLI (`obsidian backlinks`), when installed — authoritative,
    resolves each EXACT file through Obsidian's metadataCache (catches aliases
    and per-copy attribution the regex can't), but requires the desktop app
    and launches it. Used only for the handful of duplicate-set members, with
    silent fallback to the regex index when unavailable. --no-cli forces the
    regex-only path.

Usage:
  dedupe.py [PATH ...]                 # scan scope (default: whole vault)
  dedupe.py --vault DIR [PATH ...]     # vault root (default: cwd)
  dedupe.py --plan-out FILE            # where to write the JSON plan
  dedupe.py --no-cli                   # skip the Obsidian CLI, regex only
  dedupe.py --apply PLAN [--use-git]   # execute a reviewed plan
"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys
from collections import defaultdict

# Folders that are vault machinery, never content. Any dotfolder is skipped too.
IGNORE_DIRS = {".git", ".obsidian", ".trash", ".claude", ".smart-env"}
# Binary/media we care about deduping; None = hash everything except .md.
LINK_RE = re.compile(r"(!?)\[\[([^\]]+?)\]\]")          # wikilinks / embeds
MD_LINK_RE = re.compile(r"\]\(([^)]+?)\)")               # markdown links (index)
MD_REWRITE_RE = re.compile(r"(!?)\[([^\]]*)\]\(([^)]+?)\)")  # markdown links (rewrite)


def walk_files(root, scope):
    """Yield files under each scope path, skipping ignored dirs."""
    for base in scope:
        base = os.path.join(root, base) if not os.path.isabs(base) else base
        if os.path.isfile(base):
            yield base
            continue
        for dp, dirs, fs in os.walk(base):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
            for f in fs:
                yield os.path.join(dp, f)


def file_hash(path):
    """SHA-256 of a file. SHA over MD5: a false merge is effectively
    unrecoverable, and MD5 collisions are cheaply constructible."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def build_backlinks(root):
    """basename -> set(note relpaths) for every wikilink/md-link in the vault."""
    refs = defaultdict(set)
    for dp, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        for f in fs:
            if not f.endswith(".md"):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root)
            txt = open(p, encoding="utf-8", errors="replace").read()
            for _, tgt in LINK_RE.findall(txt):
                bn = os.path.basename(tgt.split("|")[0].split("#")[0].strip())
                refs[bn].add(rel)
            for tgt in MD_LINK_RE.findall(txt):
                bn = os.path.basename(tgt.split("#")[0].strip())
                refs[bn].add(rel)
    return refs


def cli_available():
    """True if the Obsidian CLI is on PATH (does not launch the app)."""
    return shutil.which("obsidian") is not None


def obsidian_backlinks(relpath, vault_name=None):
    """Authoritative referrers for an EXACT file via the Obsidian CLI.
    Returns a set of referrer relpaths, or None if the CLI is unavailable or
    errored (caller falls back to the regex index). An empty set means the CLI
    answered and found no backlinks — distinct from None."""
    cmd = ["obsidian", "backlinks", f"path={relpath}", "format=json"]
    if vault_name:
        cmd.append(f"vault={vault_name}")
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if out.returncode != 0:
        return None
    # The CLI interleaves banner lines ("Loading…", "installer out of date")
    # with output; slice the JSON array out of stdout.
    txt = out.stdout
    i, j = txt.find("["), txt.rfind("]")
    if i == -1 or j == -1 or j < i:
        return None
    try:
        data = json.loads(txt[i:j + 1])
    except json.JSONDecodeError:
        return None
    return {d["file"] for d in data if isinstance(d, dict) and "file" in d}


DAILY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def is_daily(rel):
    """A daily/journal note under Notes/ — an image appearing in one is almost
    always a capture, not a deliberate cross-note reuse."""
    parts = rel.replace("\\", "/").split("/")
    return parts[0] == "Notes" and bool(DAILY_RE.search(os.path.basename(rel)))


def nonmd_refs(root, basenames):
    """basename -> sorted[non-markdown referrers] for any .canvas/.base file
    that names one of `basenames`. apply only rewrites markdown links, so a
    duplicate referenced from canvas/base must NOT be auto-collapsed — the
    embed there would dangle. Cheap: only scans for the duplicate basenames."""
    hits = defaultdict(set)
    if not basenames:
        return {}
    for dp, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        for f in fs:
            if not (f.endswith(".canvas") or f.endswith(".base")):
                continue
            p = os.path.join(dp, f)
            try:
                txt = open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            rel = os.path.relpath(p, root)
            for bn in basenames:
                if bn in txt:
                    hits[bn].add(rel)
    return {bn: sorted(v) for bn, v in hits.items()}


SUFFIX_RE = re.compile(r"(-\d+|\s\d+)$")  # iCloud/import disambiguators
# Canonical keep, in priority order: un-suffixed name > most-referenced
# (fewest repoints) > shortest > lexically first. Applied inline in scan() so
# "most-referenced" can use authoritative CLI link counts when available.


def classify(notes):
    """tier + risk from the union of referrer notes for a duplicate set.
      intra-note            : <=1 referring note. Pure import bloat — safe.
      cross-note (low)      : 2+ notes, but <=1 of them is a non-daily note —
                              the rest are daily-note captures (capture+file).
      cross-note (review)   : 2+ distinct NON-daily notes share these bytes —
                              could be a legit shared asset or a mis-file. Look.
    """
    notes = set(notes)
    if len(notes) <= 1:
        return "intra-note", "n/a"
    non_daily = {n for n in notes if not is_daily(n)}
    return "cross-note", ("review" if len(non_daily) >= 2 else "low")


def resolve_links(root, paths, refs, vault_name, use_cli):
    """basename -> sorted[referrer notes] for each duplicate-set member.
    Prefers the Obsidian CLI (authoritative, per-exact-file) and falls back to
    the regex index per file when the CLI is absent or can't answer."""
    out, used_cli = {}, False
    for p in sorted(set(paths)):
        bn = os.path.basename(p)
        rel = os.path.relpath(p, root)
        got = obsidian_backlinks(rel, vault_name) if use_cli else None
        if got is None:
            out[bn] = sorted(refs.get(bn, set()))      # regex fallback
        else:
            used_cli = True
            out[bn] = sorted(got)
    return out, used_cli


def scan(root, scope, plan_out, use_cli=True):
    refs = build_backlinks(root)
    byhash = defaultdict(list)
    for p in walk_files(root, scope):
        if p.endswith(".md"):
            continue
        try:
            byhash[file_hash(p)].append(p)
        except OSError:
            pass
    groups = {h: v for h, v in byhash.items() if len(v) > 1}

    # Authoritative backlinks only for duplicate-set members (keeps CLI calls
    # to a handful). Falls back to the regex index file-by-file.
    members = [p for paths in groups.values() for p in paths]
    cli = use_cli and cli_available()
    if cli:
        print(f"Resolving backlinks via Obsidian CLI for {len(members)} "
              f"file(s) (launches the app)…", file=sys.stderr)
    linked, used_cli = resolve_links(root, members, refs, None, cli)

    # Canvas/base references can't be auto-repointed — guard against them.
    member_bns = {os.path.basename(p) for p in members}
    blockers = nonmd_refs(root, member_bns)

    plan = []
    for h, paths in sorted(groups.items(), key=lambda kv: os.path.basename(min(kv[1])).lower()):
        def nlinks(p):
            return len(linked.get(os.path.basename(p), ()))
        # Canonical pick uses authoritative link counts when we have them.
        keep = min(paths, key=lambda p: (
            1 if SUFFIX_RE.search(os.path.splitext(os.path.basename(p))[0]) else 0,
            -nlinks(p), len(os.path.basename(p)), os.path.basename(p)))
        keep_bn = os.path.basename(keep)
        notes = set()
        for p in paths:
            notes |= set(linked.get(os.path.basename(p), ()))
        tier, risk = classify(notes)
        blocked = sorted({b for p in paths
                          for b in blockers.get(os.path.basename(p), ())})
        drops, repoint = [], defaultdict(list)  # note -> [(from_bn, to_bn)]
        for p in paths:
            if p == keep:
                continue
            bn = os.path.basename(p)
            for note in linked.get(bn, ()):
                if note.endswith(".md"):
                    repoint[note].append([bn, keep_bn])
            drops.append({"path": os.path.relpath(p, root), "basename": bn,
                          "sha256": h, "linked_from": sorted(linked.get(bn, ()))})
        plan.append({
            "tier": tier,
            "risk": risk,
            "backlink_source": "obsidian-cli" if used_cli else "regex",
            "blocked_nonmd": blocked,
            "keep": {"path": os.path.relpath(keep, root), "basename": keep_bn,
                     "sha256": h, "linked_from": sorted(linked.get(keep_bn, ()))},
            "drops": drops,
            "repoint": {n: r for n, r in repoint.items()},
        })

    print_report(plan)
    if plan_out:
        json.dump(plan, open(plan_out, "w"), indent=2)
        print(f"\nPlan written to {plan_out}")
        print(f"Review the table above, then apply with:\n  {sys.argv[0]} --apply {plan_out}")
    return plan


def tier_label(g):
    if g["blocked_nonmd"]:
        return "BLOCKED"
    if g["tier"] == "cross-note":
        return "cross-note ⚠" if g["risk"] == "review" else "cross-note"
    return g["tier"]


def print_report(plan):
    # intra → cross-low → cross-review, with blocked sets surfaced last.
    rank = {"intra-note": 0, "cross-note": 1}
    plan = sorted(plan, key=lambda g: (
        2 if g["blocked_nonmd"] else rank.get(g["tier"], 9),
        0 if g["risk"] != "review" else 1))
    n_drop = sum(len(g["drops"]) for g in plan if not g["blocked_nonmd"])
    notes = {n for g in plan if not g["blocked_nonmd"] for n in g["repoint"]}
    src = "Obsidian CLI" if any(g["backlink_source"] == "obsidian-cli" for g in plan) else "regex index"
    print(f"Duplicate sets: {len(plan)} | files to remove: {n_drop} | "
          f"notes to repoint: {len(notes)} | backlinks: {src}\n")
    print("| Tier | Keep | Drop (count) | Linked from |")
    print("|------|------|--------------|-------------|")
    for g in plan:
        kept = g["keep"]["basename"]
        dn = len(g["drops"])
        where = sorted({n for d in g["drops"] for n in d["linked_from"]} |
                       set(g["keep"]["linked_from"]))
        where_disp = "; ".join(where) if where else "—(unreferenced)"
        print(f"| {tier_label(g)} | `{kept}` | {dn} | {where_disp} |")
    review = [g for g in plan if g["tier"] == "cross-note" and g["risk"] == "review" and not g["blocked_nonmd"]]
    if review:
        print("\n⚠  cross-note ⚠ sets couple 2+ distinct non-daily notes onto one file.")
        print("   Eyeball the actual images before collapsing — unrelated notes sharing")
        print("   bytes can mean a mis-filed attachment, not bloat:")
        for g in review:
            print(f"     `{g['keep']['basename']}`")
    blocked = [g for g in plan if g["blocked_nonmd"]]
    if blocked:
        print("\n⛔ BLOCKED sets are referenced from .canvas/.base files, which apply")
        print("   cannot repoint — collapsing would dangle those embeds. Excluded from")
        print("   apply; resolve by hand or trim from the plan:")
        for g in blocked:
            print(f"     `{g['keep']['basename']}` ← {', '.join(g['blocked_nonmd'])}")


def rewrite_links(text, mapping):
    """Replace link targets whose basename matches a mapping key. Both
    wikilinks/embeds and markdown links are rewritten; each keeps its original
    syntax — only the target's basename is swapped, so a vault that uses
    markdown links stays in markdown form."""
    def wl(m):
        bang, tgt = m.group(1), m.group(2)
        head = tgt.split("|", 1)
        core = head[0].split("#", 1)
        bn = os.path.basename(core[0].strip())
        if bn in mapping:
            newcore = core[0].replace(bn, mapping[bn])
            rebuilt = newcore + ("#" + core[1] if len(core) > 1 else "")
            rebuilt += ("|" + head[1] if len(head) > 1 else "")
            return f"{bang}[[{rebuilt}]]"
        return m.group(0)

    def ml(m):
        bang, cap, tgt = m.group(1), m.group(2), m.group(3)
        core = tgt.split("#", 1)
        path = core[0].strip()
        bn = os.path.basename(path)
        if bn in mapping:
            newpath = path[: len(path) - len(bn)] + mapping[bn]
            rebuilt = newpath + ("#" + core[1] if len(core) > 1 else "")
            return f"{bang}[{cap}]({rebuilt})"
        return m.group(0)

    text = LINK_RE.sub(wl, text)        # wikilinks/embeds first
    return MD_REWRITE_RE.sub(ml, text)  # then markdown links (won't match [[..]])


def verify_hash(root, rel, want):
    """None if file matches `want`; else a reason string (missing/changed)."""
    p = os.path.join(root, rel)
    if not os.path.exists(p):
        return "missing"
    if not want:
        return None  # legacy plan without stored hash — nothing to check
    try:
        return None if file_hash(p) == want else "CHANGED since scan"
    except OSError as e:
        return f"unreadable ({e})"


def remove_file(root, rel, use_git):
    if use_git:
        subprocess.run(["git", "rm", "--quiet", "--", rel], cwd=root, check=False)
    else:
        os.remove(os.path.join(root, rel))


def apply(root, plan_path, use_git):
    plan = json.load(open(plan_path))
    removed = repointed = skipped = 0
    for g in plan:
        keep = g["keep"]
        tag = f"[{keep['basename']}]"
        if g.get("blocked_nonmd"):
            print(f"{tag} SKIP — referenced from {', '.join(g['blocked_nonmd'])} "
                  f"(canvas/base can't be repointed)")
            skipped += 1
            continue
        # The keep must still be the bytes we planned around before we delete
        # anything that points at it.
        bad = verify_hash(root, keep["path"], keep.get("sha256"))
        if bad:
            print(f"{tag} SKIP — keep copy {bad}: {keep['path']}")
            skipped += 1
            continue
        # Re-verify each drop; only collapse the ones that still match.
        live = [d for d in g["drops"] if not verify_hash(root, d["path"], d.get("sha256"))]
        for d in g["drops"]:
            why = verify_hash(root, d["path"], d.get("sha256"))
            if why == "missing":
                print(f"{tag} (already gone) {d['path']}")
            elif why:
                print(f"{tag} SKIP drop — {why}: {d['path']}")
        if not live:
            continue
        # Repoint only the notes whose drops survived verification.
        live_bns = {d["basename"] for d in live}
        per_note = defaultdict(dict)
        for note, pairs in g["repoint"].items():
            for frm, to in pairs:
                if frm in live_bns:
                    per_note[note][frm] = to
        for note, mapping in per_note.items():
            p = os.path.join(root, note)
            txt = open(p, encoding="utf-8", errors="replace").read()
            new = rewrite_links(txt, mapping)
            if new != txt:
                open(p, "w", encoding="utf-8").write(new)
                repointed += 1
                print(f"{tag} repointed {len(mapping)} link(s) in {note}")
        for d in live:
            remove_file(root, d["path"], use_git)
            removed += 1
            print(f"{tag} removed {d['path']}")
    print(f"\nDone: {removed} file(s) removed, {repointed} note(s) repointed, "
          f"{skipped} set(s) skipped.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scope", nargs="*", help="files/folders to scan (default: whole vault)")
    ap.add_argument("--vault", default=".", help="vault root (default: cwd)")
    ap.add_argument("--plan-out", help="write JSON plan to this path")
    ap.add_argument("--no-cli", action="store_true",
                    help="skip the Obsidian CLI; use the regex index only")
    ap.add_argument("--apply", metavar="PLAN", help="execute a reviewed JSON plan")
    ap.add_argument("--use-git", action="store_true", help="remove via 'git rm' (apply mode)")
    a = ap.parse_args()
    root = os.path.abspath(a.vault)
    if a.apply:
        apply(root, a.apply, a.use_git)
    else:
        scan(root, a.scope or ["."], a.plan_out, use_cli=not a.no_cli)


if __name__ == "__main__":
    main()
