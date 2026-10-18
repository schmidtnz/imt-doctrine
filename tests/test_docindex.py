"""Builds a small site with the docindex extension and checks the index, glossary and menu."""
import io
import tempfile
import textwrap
import unittest
from pathlib import Path

try:
    from sphinx.application import Sphinx
except ImportError:  # pragma: no cover
    Sphinx = None

ROOT = Path(__file__).resolve().parents[1]

PAGES = {
    "conf.py": f"""
        import sys
        sys.path.insert(0, {str(ROOT / "docs" / "_ext")!r})
        extensions = ["myst_parser", "traceability", "docindex"]
    """,
    "index.md": """
        # Home

        ```{toctree}
        glossary
        prn-01
        notes
        status/traceability
        Index <genindex>
        ```
    """,
    "glossary.md": """
        # Glossary

        Terms such as {term}`POD`.

        ```{glossary}
        POD
          Probability of Detection.

        MMISSI TD
          Initial response mnemonic.

        LKP
          Last Known Point.
        ```
    """,
    "prn-01.md": """
        ---
        id: PRN-01
        type: principle
        title: The search principle
        index: [MMISSI TD]
        ---

        # PRN-01 The search principle

        Report {term}`POD`, then {term}`POD` again.
    """,
    "notes.md": """
        # Notes

        Lower case {term}`pod`.
    """,
}


@unittest.skipIf(Sphinx is None, "needs Sphinx")
class DocIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        src = Path(cls.tmp.name) / "src"
        for name, text in PAGES.items():
            (src / name).parent.mkdir(parents=True, exist_ok=True)
            (src / name).write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
        cls.out, cls.warnings = {}, {}
        for builder in ("html", "latex"):
            out, warnings = Path(cls.tmp.name) / builder, io.StringIO()
            Sphinx(src, src, out, out / ".doctrees", builder, status=None, warning=warnings).build()
            cls.out[builder], cls.warnings[builder] = out, warnings.getvalue()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def html(self, name):
        return (self.out["html"] / name).read_text(encoding="utf-8")

    def test_items_and_term_uses_are_indexed(self):
        index = self.html("genindex.html")
        self.assertIn("PRN-01 The search principle", index)
        self.assertIn("Search principle", index)
        # One entry per page, however often the term is used there.
        self.assertEqual(index.count('href="prn-01.html#index-'), 4)

    def test_glossary_lists_pages_that_use_each_term(self):
        uses = [line for line in self.html("glossary.html").splitlines() if "term-uses" in line]
        self.assertEqual(len(uses), 2)
        self.assertIn('href="prn-01.html#index-', uses[0])
        self.assertIn("Notes", uses[0])
        self.assertNotIn("glossary.html#", uses[0])
        self.assertIn("PRN-01 The search principle", uses[1])

    def test_index_is_in_the_menu_but_not_the_pdf(self):
        self.assertIn('href="genindex.html"', self.html("index.html"))
        self.assertNotIn("genindex", self.warnings["latex"])
        tex = next(self.out["latex"].glob("*.tex")).read_text(encoding="utf-8")
        self.assertIn(r"\index{MMISSI TD@\spxentry{MMISSI TD}!PRN\sphinxhyphen{}01", tex)

    def test_term_written_in_other_case_warns(self):
        self.assertIn("index entry 'pod' should match the glossary: 'POD'", self.warnings["html"])


if __name__ == "__main__":
    unittest.main()
