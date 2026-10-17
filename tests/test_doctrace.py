"""Unit tests for the traceability checker and Sphinx extension helpers."""
import datetime as dt
import json
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import doctrace  # noqa: E402

TODAY = dt.date(2026, 10, 9)


def write(root: Path, name: str, meta: str, body: str = "# Title\n\nText.\n") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{textwrap.dedent(meta).strip()}\n---\n\n{body}", encoding="utf-8")
    return path


PRN = """
    id: PRN-01
    type: principle
    title: Safety
    version: 2
    owner: g
    last_reviewed: 2026-10-01
"""


def con(against: int = 2, extra: str = "") -> str:
    return f"""
    id: CON-01
    type: concept
    title: Hazards
    derives_from:
      PRN-01: {against}
    owner: g
    last_reviewed: 2026-10-01
    {extra}
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self, base=None):
        items, findings = doctrace.load_items(self.root)
        return items, findings + doctrace.check(items, TODAY, base)

    def levels(self, findings):
        return sorted((f.level, f.item_id) for f in findings)


class ParseTests(Base):
    def test_non_item_pages_ignored(self):
        (self.root / "index.md").write_text("# Home\n")
        items, findings = self.run_check()
        self.assertEqual(items, {})
        self.assertEqual(findings, [])

    def test_clean_chain_has_no_findings(self):
        write(self.root, "p.md", PRN + "    requires_children: [concept]\n")
        write(self.root, "c.md", con())
        items, findings = self.run_check()
        self.assertEqual(set(items), {"PRN-01", "CON-01"})
        self.assertEqual(findings, [])

    def test_missing_title_is_error(self):
        write(self.root, "p.md", "id: PRN-01\ntype: principle")
        _, findings = self.run_check()
        self.assertIn(("error", "PRN-01"), self.levels(findings))

    def test_derives_from_list_rejected(self):
        write(self.root, "p.md", PRN)
        write(self.root, "c.md", "id: CON-01\ntype: concept\ntitle: X\nderives_from: [PRN-01]\nowner: g\nlast_reviewed: 2026-10-01")
        _, findings = self.run_check()
        self.assertTrue(any("derives_from must map" in f.message for f in findings))

    def test_duplicate_id(self):
        write(self.root, "a.md", PRN)
        write(self.root, "b.md", PRN)
        _, findings = self.run_check()
        self.assertTrue(any("duplicate ID" in f.message for f in findings))

    def test_bad_yaml_reported(self):
        (self.root / "x.md").write_text("---\nid: [unclosed\n---\n# X\n")
        _, findings = self.run_check()
        self.assertEqual(findings[0].level, "error")


class CheckTests(Base):
    def test_orphan_parent(self):
        write(self.root, "c.md", con())
        _, findings = self.run_check()
        self.assertTrue(any("does not exist" in f.message for f in findings))

    def test_unanchored_non_principle(self):
        write(self.root, "c.md", "id: CON-01\ntype: concept\ntitle: X\nowner: g\nlast_reviewed: 2026-10-01")
        _, findings = self.run_check()
        self.assertTrue(any("must derive from a principle" in f.message for f in findings))

    def test_wrong_parent_type(self):
        write(self.root, "p.md", PRN)
        write(self.root, "g.md", "id: GDL-01\ntype: guideline\ntitle: X\nderives_from:\n  PRN-01: 2\nowner: g\nlast_reviewed: 2026-10-01")
        _, findings = self.run_check()
        self.assertTrue(any("cannot derive from a principle" in f.message for f in findings))

    def test_wrong_prefix_and_unknown_type(self):
        write(self.root, "a.md", "id: X-01\ntype: principle\ntitle: X\nowner: g\nlast_reviewed: 2026-10-01")
        write(self.root, "b.md", "id: Y-01\ntype: policy\ntitle: Y\nowner: g\nlast_reviewed: 2026-10-01")
        _, findings = self.run_check()
        msgs = " ".join(f.message for f in findings)
        self.assertIn("should start with PRN-", msgs)
        self.assertIn("unknown type 'policy'", msgs)

    def test_stale_child_listed_not_failed(self):
        write(self.root, "p.md", PRN)
        write(self.root, "c.md", con(against=1))
        _, findings = self.run_check()
        stale = [f for f in findings if f.level == "stale"]
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0].parent, "PRN-01")
        self.assertFalse(any(f.level == "error" for f in findings))

    def test_child_ahead_of_parent_fails(self):
        write(self.root, "p.md", PRN)
        write(self.root, "c.md", con(against=3))
        _, findings = self.run_check()
        self.assertIn(("error", "CON-01"), self.levels(findings))

    def test_coverage_gap_warns(self):
        write(self.root, "p.md", PRN + "    requires_children: [concept]\n")
        _, findings = self.run_check()
        self.assertEqual(self.levels(findings), [("warning", "PRN-01")])

    def test_overdue_and_never_reviewed(self):
        write(self.root, "p.md", PRN.replace("2026-10-01", "2025-01-01"))
        write(self.root, "c.md", con().replace("last_reviewed: 2026-10-01", ""))
        _, findings = self.run_check()
        overdue = {f.item_id: f.message for f in findings if f.level == "overdue"}
        self.assertEqual(overdue, {"PRN-01": "last reviewed 2025-01-01", "CON-01": "never reviewed"})

    def test_custom_review_interval(self):
        write(self.root, "p.md", PRN.replace("2026-10-01", "2026-09-01") + "    review_days: 30\n")
        _, findings = self.run_check()
        self.assertIn(("overdue", "PRN-01"), self.levels(findings))

    def test_unbumped_text_change_warns_only_for_parents(self):
        write(self.root, "p.md", PRN, body="# Safety\n\nNew wording.\n")
        write(self.root, "c.md", con())
        base = {"PRN-01": (2, "# Safety\n\nOld wording.\n"), "CON-01": (1, "old")}
        _, findings = self.run_check(base)
        unbumped = [f.item_id for f in findings if "not bumped" in f.message]
        self.assertEqual(unbumped, ["PRN-01"])

    def test_whitespace_only_change_ignored(self):
        write(self.root, "p.md", PRN, body="# Safety\n\nSame   words.\n")
        write(self.root, "c.md", con())
        _, findings = self.run_check({"PRN-01": (2, "# Safety\nSame words.")})
        self.assertFalse(any("not bumped" in f.message for f in findings))


class GitTests(Base):
    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def commit(self):
        if not (self.root / ".git").exists():
            self.git("init", "-q")
            self.git("config", "user.email", "t@example.org")
            self.git("config", "user.name", "t")
            self.git("config", "commit.gpgsign", "false")
            self.git("config", "maintenance.auto", "false")
        self.git("add", ".")
        self.git("commit", "-qm", "base")

    def test_git_base_reads_old_version(self):
        write(self.root, "docs/p.md", PRN, body="# Safety\n\nOld.\n")
        write(self.root, "docs/c.md", con())
        self.commit()
        write(self.root, "docs/p.md", PRN, body="# Safety\n\nNew.\n")
        write(self.root, "docs/n.md", PRN.replace("PRN-01", "PRN-02"))
        items, _ = doctrace.load_items(self.root / "docs")
        base = doctrace.git_base(items, "HEAD")
        self.assertEqual(set(base), {"PRN-01", "CON-01"})
        self.assertEqual(base["PRN-01"][0], 2)
        self.assertIn("Old.", base["PRN-01"][1])

    def test_load_items_at_reads_whole_tree_at_ref(self):
        write(self.root, "docs/p.md", PRN)
        write(self.root, "docs/old.md", PRN.replace("PRN-01", "PRN-09"))
        self.commit()
        (self.root / "docs/old.md").unlink()
        write(self.root, "docs/p.md", PRN.replace("version: 2", "version: 3"))
        items, findings = doctrace.load_items_at(self.root / "docs", "HEAD")
        self.assertEqual(set(items), {"PRN-01", "PRN-09"})
        self.assertEqual(items["PRN-01"].version, 2)
        self.assertEqual(findings, [])

    def test_cli_writes_comment_against_base(self):
        write(self.root, "docs/p.md", PRN + "    requires_children: [concept]\n")
        self.commit()
        write(self.root, "docs/c.md", con(against=1))
        comment = self.root / "comment.md"
        doctrace.main(["--root", str(self.root / "docs"), "--today", "2026-10-09",
                       "--base", "HEAD", "--comment", str(comment)])
        text = comment.read_text(encoding="utf-8")
        self.assertIn("Compared with `HEAD`: 1 new, 1 resolved.", text)
        self.assertIn("| new | stale | CON-01 Hazards |", text)
        self.assertIn("| resolved | warning | PRN-01 Safety | no concept derives", text)


class ReportTests(Base):
    def test_report_lists_findings_and_tree(self):
        write(self.root, "p.md", PRN + "    requires_children: [concept]\n")
        write(self.root, "c.md", con(against=1))
        items, findings = self.run_check()
        report = doctrace.render_report(items, findings, TODAY)
        self.assertIn("| stale | CON-01 Hazards |", report)
        self.assertIn("- PRN-01 Safety, v2\n  - CON-01 Hazards, v1 (stale)", report)
        self.assertIn("1 principles, 1 concepts, 0 guidelines, 0 processes, 0 forms", report)

    def test_report_when_clean(self):
        write(self.root, "p.md", PRN)
        items, findings = self.run_check()
        self.assertIn("Nothing needs attention.", doctrace.render_report(items, findings, TODAY))

    def test_overdue_report(self):
        write(self.root, "p.md", PRN.replace("2026-10-01", "2024-01-01"))
        items, findings = self.run_check()
        self.assertIn("- [ ] **PRN-01** Safety", doctrace.overdue_report(items, findings))
        write(self.root, "p.md", PRN)
        items, findings = self.run_check()
        self.assertEqual(doctrace.overdue_report(items, findings), "")

    def test_comment_without_changes_still_lists_findings(self):
        write(self.root, "p.md", PRN)
        write(self.root, "c.md", con(against=1))
        items, findings = self.run_check()
        text = doctrace.comment_report(items, findings, items, findings, "main")
        self.assertIn("No traceability changes compared with `main`.", text)
        self.assertIn("2 items: 0 errors, 0 warnings, 1 stale, 0 overdue.", text)
        self.assertIn("<summary>All findings (1)</summary>", text)

    def test_badge(self):
        write(self.root, "p.md", PRN)
        self.assertEqual(json.loads(doctrace.badge(self.run_check()[1]))["message"], "all clear")
        write(self.root, "c.md", con(against=1))
        data = json.loads(doctrace.badge(self.run_check()[1]))
        self.assertEqual((data["message"], data["color"]), ("1 stale", "yellow"))
        write(self.root, "c.md", con(against=9))
        self.assertEqual(json.loads(doctrace.badge(self.run_check()[1]))["color"], "red")


class CliTests(Base):
    def test_exit_codes_and_outputs(self):
        write(self.root, "p.md", PRN)
        report, overdue = self.root / "r.md", self.root / "o.md"
        args = ["--root", str(self.root), "--today", "2026-10-09"]
        self.assertEqual(doctrace.main(args + ["--report", str(report), "--overdue", str(overdue)]), 0)
        self.assertTrue(report.read_text().startswith("# Traceability status"))
        write(self.root, "c.md", con(against=9))
        self.assertEqual(doctrace.main(args), 1)

    def test_comment_needs_base(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            doctrace.main(["--root", str(self.root), "--comment", str(self.root / "c.md")])

    def test_github_annotation_format(self):
        f = doctrace.Finding("stale", "msg", "CON-01", Path("docs/c.md"))
        self.assertEqual(doctrace._annotate(f), "::notice file=docs/c.md::CON-01 msg")
        self.assertTrue(doctrace._annotate(doctrace.Finding("error", "x")).startswith("::error::"))


class ExtensionTests(Base):
    @classmethod
    def setUpClass(cls):
        # Stub sphinx.util.logging so the extension imports without Sphinx installed.
        if "sphinx" not in sys.modules:
            try:
                import sphinx  # noqa: F401
            except ImportError:
                logging_mod = types.SimpleNamespace(getLogger=lambda name: None)
                sys.modules["sphinx"] = types.ModuleType("sphinx")
                sys.modules["sphinx.util"] = types.SimpleNamespace(logging=logging_mod)
        sys.path.insert(0, str(ROOT / "docs" / "_ext"))
        import traceability
        cls.ext = traceability

    def make_state(self):
        write(self.root, "p.md", PRN)
        write(self.root, "sub/c.md", con(against=1), body="# CON-01 Hazards\n\nBody.\n")
        items, findings = self.run_check()
        src = self.root.resolve()
        items = {k: doctrace.Item(**{**v.__dict__, "path": v.path.resolve()}) for k, v in items.items()}
        docs = {i: self.ext._docname(src, it) for i, it in items.items()}
        return items, findings, docs

    def test_box_shows_stale_parent_and_children(self):
        items, findings, docs = self.make_state()
        child = self.ext._box(items["CON-01"], items, findings, docs)
        self.assertIn(":class: doctrace stale", child)
        self.assertIn("{doc}`PRN-01 </p>` v1 (**review needed:** PRN-01 is now v2)", child)
        parent = self.ext._box(items["PRN-01"], items, findings, docs)
        self.assertIn("**Supports:** {doc}`CON-01 </sub/c>`", parent)

    def test_source_read_strips_frontmatter_and_inserts_box(self):
        items, findings, docs = self.make_state()
        app = types.SimpleNamespace(doctrace={
            "items": items, "findings": findings, "docs": docs,
            "by_doc": {d: i for i, d in docs.items()}})
        original = (self.root / "sub/c.md").read_text()
        source = [original]
        self.ext._source_read(app, "sub/c", source)
        out = source[0]
        self.assertNotIn("derives_from", out)
        lines = out.split("\n")
        h1 = lines.index("# CON-01 Hazards")
        self.assertEqual(h1, original.split("\n").index("# CON-01 Hazards"))
        self.assertTrue(lines[h1 + 2].startswith(":::{admonition} CON-01"))
        untouched = ["# Home"]
        self.ext._source_read(app, "index", untouched)
        self.assertEqual(untouched, ["# Home"])


class RepoContentTests(unittest.TestCase):
    def test_demo_content_has_no_errors(self):
        items, findings = doctrace.load_items(ROOT / "docs")
        findings += doctrace.check(items, TODAY)
        self.assertEqual([f for f in findings if f.level == "error"], [])
        self.assertEqual(sorted((f.level, f.item_id) for f in findings),
                         [("overdue", "GDL-04"), ("stale", "CON-02"), ("warning", "PRN-15")])


if __name__ == "__main__":
    unittest.main()
