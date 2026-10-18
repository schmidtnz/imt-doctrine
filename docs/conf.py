"""Sphinx configuration for the IMT doctrine site."""
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_ext"))


def _label(described: str) -> tuple[str, str]:
    """Readable version and commit from `git describe --tags --long --always --dirty`.

    v0.2.2-demo-0-gabc1234 gives ("v0.2.2-demo", ""), v0.2.2-demo-3-gabc1234 gives
    ("v0.2.2-demo + 3 changes", "abc1234"), and uncommitted edits add ", modified".
    """
    modified = described.endswith("-dirty")
    described = described.removesuffix("-dirty")
    m = re.fullmatch(r"(.+)-(\d+)-g([0-9a-f]+)", described)
    if m:
        tag, count, commit = m.group(1), int(m.group(2)), m.group(3)
        label = f"{tag} + {count} change{'' if count == 1 else 's'}" if count else tag
    else:  # no tags yet, so describe gives only the commit
        count, commit, label = None, described, "unreleased"
    released = count == 0 and not modified
    if modified:
        label += ", modified"
    return label, "" if released else commit


def _release() -> tuple[str, str]:
    # Tag builds set DOCS_VERSION; otherwise describe the checkout.
    if os.environ.get("DOCS_VERSION"):
        return os.environ["DOCS_VERSION"], ""
    try:
        return _label(subprocess.check_output(
            ["git", "describe", "--tags", "--long", "--always", "--dirty"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip())
    except Exception:
        return "dev", ""


project = "IMT Doctrine"
author = "Doctrine working group"
release, commit = _release()
version = release

# rsvgconverter turns SVG figures into PDF for the LaTeX build (needs rsvg-convert).
extensions = ["myst_parser", "sphinx.ext.githubpages", "sphinxcontrib.rsvgconverter", "traceability",
              "docindex"]
numfig = True
numfig_format = {"figure": "Figure %s"}
myst_enable_extensions = ["colon_fence", "deflist", "substitution", "tasklist"]
myst_heading_anchors = 3
myst_substitutions = {
    "org": "LandSAR",
    "org_full": "Land Search and Rescue New Zealand",
    "release": release,
    "cite_version": f"{release} (commit {commit})" if commit else release,
}

exclude_patterns = ["_build", "_snippets", "Thumbs.db", ".DS_Store"]

html_theme = "furo"
html_title = f"IMT Doctrine {release}"
html_static_path = ["_static"]
html_css_files = ["custom.css", "versions.css"]
html_js_files = ["versions.js"]
html_theme_options = {
    "announcement": "Demonstration only: illustrative content, not agreed doctrine.",
    "source_repository": "https://github.com/schmidtnz/imt-doctrine/",
    "source_branch": "main",
    "source_directory": "docs/",
}

latex_engine = "xelatex"


def _watermark(release: str) -> str:
    # Only an exact final release tag prints clean.
    m = re.fullmatch(r"v\d+\.\d+\.\d+(-rc\.\d+|-demo)?", release)
    if m and m.group(1) == "-demo":
        return "DEMO"
    return "" if m and not m.group(1) else "DRAFT"


_mark = _watermark(release)
# Index in the text font and ragged right, with "(CIMS)" in titles kept upright.
_index_style = (r"\renewcommand{\sphinxstyleindexentry}[1]{#1}"
                r"\renewcommand{\sphinxstyleindexextra}[1]{ (#1)}"
                r"\makeatletter\g@addto@macro\theindex{\raggedright}\makeatother")
latex_elements = {
    # The traceability tree nests principle → concept → guideline → process → form,
    # one level deeper than LaTeX's default limit of four bullet lists.
    "maxlistdepth": "10",
    "preamble": _index_style + ((rf"\usepackage{{draftwatermark}}\SetWatermarkText{{{_mark}}}"
                                 r"\SetWatermarkLightness{0.92}") if _mark else ""),
}
latex_documents = [
    ("index", "imt-doctrine.tex", f"IMT Doctrine {release}",
     "Doctrine working group", "manual"),
]
