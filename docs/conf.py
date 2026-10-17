"""Sphinx configuration for the IMT doctrine site."""
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_ext"))


def _release() -> str:
    # Tag builds set DOCS_VERSION; otherwise describe the checkout.
    if os.environ.get("DOCS_VERSION"):
        return os.environ["DOCS_VERSION"]
    try:
        return subprocess.check_output(
            ["git", "describe", "--tags", "--always", "--dirty"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "dev"


project = "IMT Doctrine"
author = "Doctrine working group"
release = version = _release()

# rsvgconverter turns SVG figures into PDF for the LaTeX build (needs rsvg-convert).
extensions = ["myst_parser", "sphinx.ext.githubpages", "sphinxcontrib.rsvgconverter", "traceability"]
numfig = True
numfig_format = {"figure": "Figure %s"}
myst_enable_extensions = ["colon_fence", "deflist", "substitution", "tasklist"]
myst_heading_anchors = 3
myst_substitutions = {
    "org": "LandSAR",
    "org_full": "Land Search and Rescue New Zealand",
    "release": release,
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
latex_elements = {
    # The traceability tree nests principle → concept → guideline → process → form,
    # one level deeper than LaTeX's default limit of four bullet lists.
    "maxlistdepth": "10",
    "preamble": (rf"\usepackage{{draftwatermark}}\SetWatermarkText{{{_mark}}}"
                 r"\SetWatermarkLightness{0.92}") if _mark else "",
}
latex_documents = [
    ("index", "imt-doctrine.tex", f"IMT Doctrine {release}",
     "Doctrine working group", "manual"),
]
