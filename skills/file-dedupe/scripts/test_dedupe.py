import os, sys, tempfile, unittest

import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dedupe import (rewrite_links, scan, apply, remove_file, classify,
                    vault_name_for, backlinks_cmd, parse_vault_path,
                    daily_matcher, daily_matcher_from, moment_format_to_regex,
                    removal_warning, apply_hint)
import subprocess


class DailyNoteDetectionFromConfig(unittest.TestCase):
    """The daily-note folder/format is vault config, not a fixed Notes/ path.
    Read .obsidian/daily-notes.json so risk classification works regardless of
    where a vault files its journal."""

    def _vault(self, root, cfg):
        os.makedirs(os.path.join(root, ".obsidian"))
        with open(os.path.join(root, ".obsidian", "daily-notes.json"), "w") as fh:
            json.dump(cfg, fh)

    def test_format_to_regex_matches_dated_path(self):
        rx = moment_format_to_regex("YYYY/MM/YYYY-MM-DD")
        self.assertRegex("Notes/2021/03/2021-03-21.md", rx)
        self.assertNotRegex("Notes/index.md", rx)

    def test_matcher_uses_configured_folder_and_format(self):
        with tempfile.TemporaryDirectory() as root:
            self._vault(root, {"folder": "Journal", "format": "YYYY/YYYY-MM-DD"})
            is_daily = daily_matcher(root)
            self.assertTrue(is_daily("Journal/2011/2011-10-06.md"))
            self.assertFalse(is_daily("Places/Grand Mesa.md"))
            self.assertFalse(is_daily("Journal/Index.md"))  # in folder but not dated

    def test_no_config_treats_nothing_as_daily(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".obsidian"))
            is_daily = daily_matcher(root)
            self.assertFalse(is_daily("Notes/2021/03/2021-03-21.md"))

    def test_classify_low_risk_when_only_one_non_daily_note(self):
        is_daily = daily_matcher_from({"folder": "Journal", "format": "YYYY-MM-DD"})
        tier, risk = classify({"Journal/2011-10-06.md", "Places/Grand Mesa.md"}, is_daily)
        self.assertEqual((tier, risk), ("cross-note", "low"))

    def test_classify_review_when_two_non_daily_notes(self):
        is_daily = daily_matcher_from({"folder": "Journal", "format": "YYYY-MM-DD"})
        tier, risk = classify({"Ammo/A.md", "Ammo/B.md"}, is_daily)
        self.assertEqual((tier, risk), ("cross-note", "review"))


class CliVaultTargeting(unittest.TestCase):
    """The CLI resolves a vault by name and only reliably answers for the
    OPEN/active vault, so dedupe must name the vault explicitly rather than
    trust whichever vault happens to be active."""

    def test_vault_name_is_the_root_folder_name(self):
        self.assertEqual(vault_name_for("/a/b/Lifebook"), "Lifebook")

    def test_vault_name_ignores_trailing_slash(self):
        self.assertEqual(vault_name_for("/a/b/Lifebook/"), "Lifebook")

    def test_backlinks_cmd_includes_vault_when_named(self):
        self.assertIn("vault=Lifebook", backlinks_cmd("Attachments/x.png", "Lifebook"))

    def test_backlinks_cmd_omits_vault_when_unnamed(self):
        self.assertFalse(any(a.startswith("vault=")
                             for a in backlinks_cmd("x.png", None)))

    def test_parse_vault_path_reads_tab_separated_path(self):
        out = "name\tLifebook\npath\t/a/b/Lifebook\nfiles\t10\n"
        self.assertEqual(parse_vault_path(out), "/a/b/Lifebook")

    def test_parse_vault_path_returns_none_when_absent(self):
        self.assertIsNone(parse_vault_path("error: not found\n"))


class RewriteMarkdownLinks(unittest.TestCase):
    """Repointing a dropped duplicate must fix markdown links too, not just
    wikilinks — otherwise apply deletes the file and leaves the link dangling.
    The original markdown format is preserved; only the target is swapped."""

    def setUp(self):
        self.m = {"drop-2.png": "keep.png"}

    def test_markdown_link_target_swapped_preserving_format(self):
        self.assertEqual(
            rewrite_links("See the [diagram](drop-2.png).", self.m),
            "See the [diagram](keep.png).")

    def test_markdown_embed_target_swapped(self):
        self.assertEqual(
            rewrite_links("![shot](drop-2.png)", self.m),
            "![shot](keep.png)")

    def test_markdown_link_with_subfolder_keeps_prefix(self):
        self.assertEqual(
            rewrite_links("[d](Attachments/drop-2.png)", self.m),
            "[d](Attachments/keep.png)")

    def test_non_matching_markdown_link_untouched(self):
        self.assertEqual(
            rewrite_links("[x](other.png)", self.m),
            "[x](other.png)")

    def test_wikilink_still_repointed(self):
        self.assertEqual(
            rewrite_links("![[drop-2.png]]", self.m),
            "![[keep.png]]")

    def test_wikilink_swaps_only_trailing_basename(self):
        # basename appears twice in the path (a folder named like the file);
        # only the final segment should change, not the directory.
        self.assertEqual(
            rewrite_links("[[Logo.png/Logo.png]]", {"Logo.png": "Brand.png"}),
            "[[Logo.png/Brand.png]]")


class MarkdownLinkEdgeCases(unittest.TestCase):
    """Markdown links can carry titles, angle brackets, and percent-encoded
    targets. Indexing and rewriting must agree on the real on-disk basename, or
    a referenced file gets deleted with its link left dangling."""

    def test_url_encoded_target_repointed_and_reencoded(self):
        self.assertEqual(
            rewrite_links("![cap](drop%20img.png)", {"drop img.png": "keep img.png"}),
            "![cap](keep%20img.png)")

    def test_titled_link_preserves_title(self):
        self.assertEqual(
            rewrite_links('[d](drop-2.png "a title")', {"drop-2.png": "keep.png"}),
            '[d](keep.png "a title")')

    def test_angle_bracket_dest_with_space(self):
        self.assertEqual(
            rewrite_links("[d](<drop 2.png>)", {"drop 2.png": "keep 2.png"}),
            "[d](<keep 2.png>)")

    def test_encoded_subfolder_prefix_preserved(self):
        self.assertEqual(
            rewrite_links("[d](Sub%20Dir/drop%20img.png)", {"drop img.png": "keep img.png"}),
            "[d](Sub%20Dir/keep%20img.png)")

    def test_end_to_end_encoded_markdown_referrer(self):
        # canonical keep is the un-suffixed "img.png"; "img 2.png" is the drop,
        # referenced via a percent-encoded markdown link that must be repointed.
        with tempfile.TemporaryDirectory() as root:
            data = b"identical"
            for name in ("img.png", "img 2.png"):
                with open(os.path.join(root, name), "wb") as fh:
                    fh.write(data)
            note = os.path.join(root, "note.md")
            with open(note, "w") as fh:
                fh.write("![x](img%202.png)\n")
            plan = os.path.join(root, "plan.json")
            scan(root, ["."], plan, use_cli=False)
            apply(root, plan, use_git=False, force=True)
            self.assertFalse(os.path.exists(os.path.join(root, "img 2.png")),
                             "suffixed duplicate should be removed")
            self.assertEqual(open(note).read(), "![x](img.png)\n",
                             "encoded markdown link should be repointed to the keep")


class ApplyRepointsMarkdownLinkBeforeDeleting(unittest.TestCase):
    """End-to-end: a duplicate referenced only by a markdown link must be
    repointed to the keep, then deleted — never deleted while the link dangles."""

    def test_markdown_referrer_repointed_then_drop_removed(self):
        with tempfile.TemporaryDirectory() as root:
            data = b"\x89PNG identical bytes"
            for name in ("keep.png", "drop-2.png"):
                with open(os.path.join(root, name), "wb") as fh:
                    fh.write(data)
            note = os.path.join(root, "note.md")
            with open(note, "w") as fh:
                fh.write("See the [diagram](drop-2.png).\n")

            plan = os.path.join(root, "plan.json")
            scan(root, ["."], plan, use_cli=False)
            apply(root, plan, use_git=False, force=True)

            self.assertFalse(os.path.exists(os.path.join(root, "drop-2.png")),
                             "dropped duplicate should be removed")
            self.assertTrue(os.path.exists(os.path.join(root, "keep.png")),
                            "canonical copy should remain")
            self.assertEqual(open(note).read(), "See the [diagram](keep.png).\n",
                             "markdown link should be repointed, not left dangling")


class RemovalPrefersTrash(unittest.TestCase):
    """A removed duplicate should go to the vault's .trash/ when one exists,
    so the operation is recoverable — only hard-delete when there's no trash."""

    def _make(self, root, rel):
        full = os.path.join(root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(b"bytes")
        return full

    def test_moves_to_trash_when_trash_exists(self):
        with tempfile.TemporaryDirectory() as root:
            os.mkdir(os.path.join(root, ".trash"))
            src = self._make(root, "Attachments/drop.png")
            remove_file(root, "Attachments/drop.png", use_git=False)
            self.assertFalse(os.path.exists(src), "original should be gone")
            self.assertTrue(
                os.path.exists(os.path.join(root, ".trash", "Attachments", "drop.png")),
                "file should be moved under .trash/")

    def test_hard_deletes_when_no_trash(self):
        with tempfile.TemporaryDirectory() as root:
            src = self._make(root, "Attachments/drop.png")
            remove_file(root, "Attachments/drop.png", use_git=False)
            self.assertFalse(os.path.exists(src), "original should be gone")
            self.assertFalse(os.path.exists(os.path.join(root, ".trash")),
                             ".trash should not be created when absent")

    def test_trash_collision_keeps_both(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".trash", "Attachments"))
            with open(os.path.join(root, ".trash", "Attachments", "drop.png"), "wb") as fh:
                fh.write(b"older")
            self._make(root, "Attachments/drop.png")
            remove_file(root, "Attachments/drop.png", use_git=False)
            trashed = os.listdir(os.path.join(root, ".trash", "Attachments"))
            self.assertEqual(len(trashed), 2, "existing trashed file must not be clobbered")


def _dup_vault(root, note_text="![x](drop-2.png)\n", names=("keep.png", "drop-2.png")):
    """A minimal vault: two byte-identical files and a note referencing a drop."""
    for name in names:
        with open(os.path.join(root, name), "wb") as fh:
            fh.write(b"identical-bytes")
    with open(os.path.join(root, "note.md"), "w") as fh:
        fh.write(note_text)
    plan = os.path.join(root, "plan.json")
    scan(root, ["."], plan, use_cli=False)
    return plan


class UseGitFailsLoudly(unittest.TestCase):
    """--use-git on a non-git vault must not silently no-op while reporting
    success. The whole point of the skill is that 'removed' means removed."""

    def test_remove_file_raises_when_git_rm_fails(self):
        with tempfile.TemporaryDirectory() as root:  # not a git work tree
            with open(os.path.join(root, "drop.png"), "wb") as fh:
                fh.write(b"x")
            with self.assertRaises(RuntimeError):
                remove_file(root, "drop.png", use_git=True)
            self.assertTrue(os.path.exists(os.path.join(root, "drop.png")),
                            "file must remain when git rm fails")

    def test_apply_refuses_use_git_outside_work_tree(self):
        with tempfile.TemporaryDirectory() as root:  # not a git work tree
            plan = _dup_vault(root)
            apply(root, plan, use_git=True)
            self.assertTrue(os.path.exists(os.path.join(root, "drop-2.png")),
                            "nothing removed when --use-git can't apply")
            self.assertEqual(open(os.path.join(root, "note.md")).read(),
                             "![x](drop-2.png)\n", "no repoint when run is aborted")


class PermanentDeleteIsGated(unittest.TestCase):
    """The irreversible path (no .trash/, no --use-git) must be opt-in via
    --force, and the operator must be warned about it at scan time."""

    def test_refuses_permanent_delete_without_force(self):
        with tempfile.TemporaryDirectory() as root:  # no .trash, not git
            plan = _dup_vault(root)
            apply(root, plan, use_git=False, force=False)
            self.assertTrue(os.path.exists(os.path.join(root, "drop-2.png")),
                            "must not permanently delete without --force")
            self.assertEqual(open(os.path.join(root, "note.md")).read(),
                             "![x](drop-2.png)\n", "no repoint when aborted")

    def test_force_allows_permanent_delete(self):
        with tempfile.TemporaryDirectory() as root:
            plan = _dup_vault(root)
            apply(root, plan, use_git=False, force=True)
            self.assertFalse(os.path.exists(os.path.join(root, "drop-2.png")))
            self.assertEqual(open(os.path.join(root, "note.md")).read(),
                             "![x](keep.png)\n")

    def test_trash_does_not_require_force(self):
        with tempfile.TemporaryDirectory() as root:
            os.mkdir(os.path.join(root, ".trash"))
            plan = _dup_vault(root)
            apply(root, plan, use_git=False, force=False)
            self.assertFalse(os.path.exists(os.path.join(root, "drop-2.png")))
            self.assertTrue(os.path.exists(
                os.path.join(root, ".trash", "drop-2.png")))

    def test_warning_flags_permanent_when_no_trash_no_git(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIn("PERMANENT", removal_warning(root).upper())

    def test_warning_mentions_trash_when_present(self):
        with tempfile.TemporaryDirectory() as root:
            os.mkdir(os.path.join(root, ".trash"))
            self.assertIn(".trash", removal_warning(root))


class CleanResultReporting(unittest.TestCase):
    """A scan that finds nothing should say so plainly, not print an empty
    table the agent has to interpret."""

    def test_scan_reports_no_duplicates_cleanly(self):
        import io, contextlib
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "only.png"), "wb") as fh:
                fh.write(b"unique")
            with open(os.path.join(root, "note.md"), "w") as fh:
                fh.write("hello\n")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                plan = scan(root, ["."], None, use_cli=False)
            out = buf.getvalue()
            self.assertEqual(plan, [])
            self.assertIn("No duplicate sets found", out)
            self.assertNotIn("| Tier |", out)


class ApplyHint(unittest.TestCase):
    """The 'apply with:' hint must echo --vault (plan paths are vault-relative)
    and steer toward the recoverable form when the vault is a git repo."""

    def test_hint_echoes_vault(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIn(f"--vault {root}", apply_hint("dedupe.py", "p.json", root))

    def test_hint_suggests_use_git_in_repo(self):
        with tempfile.TemporaryDirectory() as root:
            subprocess.run(["git", "init", "-q", root], check=True)
            self.assertIn("--use-git", apply_hint("dedupe.py", "p.json", root))

    def test_hint_omits_use_git_outside_repo(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertNotIn("--use-git", apply_hint("dedupe.py", "p.json", root))


if __name__ == "__main__":
    unittest.main()
