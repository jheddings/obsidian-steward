import os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dedupe import rewrite_links, scan, apply


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
            apply(root, plan, use_git=False)

            self.assertFalse(os.path.exists(os.path.join(root, "drop-2.png")),
                             "dropped duplicate should be removed")
            self.assertTrue(os.path.exists(os.path.join(root, "keep.png")),
                            "canonical copy should remain")
            self.assertEqual(open(note).read(), "See the [diagram](keep.png).\n",
                             "markdown link should be repointed, not left dangling")


if __name__ == "__main__":
    unittest.main()
