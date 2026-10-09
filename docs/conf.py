"""Sphinx configuration for the IMT doctrine site."""
import os
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

extensions = ["myst_parser", "sphinx.ext.githubpages", "traceability"]
myst_enable_extensions = ["colon_fence", "deflist", "substitution"]
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
html_css_files = ["custom.css"]
html_theme_options = {
    "announcement": "Demonstration only: illustrative content, not agreed doctrine.",
    "source_repository": "https://github.com/schmidtnz/imt-doctrine/",
    "source_branch": "main",
    "source_directory": "docs/",
}

latex_engine = "xelatex"
latex_documents = [
    ("index", "imt-doctrine.tex", f"IMT Doctrine {release}",
     "Doctrine working group", "manual"),
]
