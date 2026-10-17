"""Unit tests for the version label and watermark in the Sphinx configuration."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("docs_conf", ROOT / "docs" / "conf.py")
conf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conf)


class LabelTests(unittest.TestCase):
    def test_release_and_drafts(self):
        self.assertEqual(conf._label("v0.2.2-demo-0-gabc1234"), ("v0.2.2-demo", ""))
        self.assertEqual(conf._label("v0.2.2-demo-1-gabc1234"), ("v0.2.2-demo + 1 change", "abc1234"))
        self.assertEqual(conf._label("v1.0.0-rc.1-3-gabc1234"), ("v1.0.0-rc.1 + 3 changes", "abc1234"))

    def test_uncommitted_edits_and_no_tags(self):
        self.assertEqual(conf._label("v0.2.2-demo-0-gabc1234-dirty"), ("v0.2.2-demo, modified", "abc1234"))
        self.assertEqual(conf._label("v0.2.2-demo-2-gabc1234-dirty"),
                         ("v0.2.2-demo + 2 changes, modified", "abc1234"))
        self.assertEqual(conf._label("abc1234"), ("unreleased", "abc1234"))

    def test_only_exact_final_releases_print_clean(self):
        self.assertEqual(conf._watermark("v1.0.0"), "")
        self.assertEqual(conf._watermark("v0.2.2-demo"), "DEMO")
        self.assertEqual(conf._watermark("v0.2.2-demo + 3 changes"), "DRAFT")
        self.assertEqual(conf._watermark("v1.0.0, modified"), "DRAFT")


if __name__ == "__main__":
    unittest.main()
