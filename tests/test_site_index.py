"""Unit tests for the versioned site layout."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import site_index  # noqa: E402
from release import Version as V  # noqa: E402


def versions(*names):
    return site_index.versions_in(list(names))


class LayoutTests(unittest.TestCase):
    def test_versions_in_ignores_other_folders_and_sorts_newest_first(self):
        found = versions("next", "latest", "pr-preview", "v0.2.0-demo", "v1.0.0", "v1.1.0-rc.1", "v0.10.0")
        self.assertEqual([str(v) for v in found], ["v1.1.0-rc.1", "v1.0.0", "v0.10.0", "v0.2.0-demo"])

    def test_latest_prefers_final_then_falls_back(self):
        self.assertEqual(str(site_index.site_latest(versions("v1.0.0", "v1.1.0-rc.1"))), "v1.0.0")
        self.assertEqual(str(site_index.site_latest(versions("v0.2.0-demo", "v0.2.1-demo"))), "v0.2.1-demo")
        self.assertIsNone(site_index.site_latest([]))

    def test_base_path(self):
        self.assertEqual(site_index.base_path("o/imt-doctrine"), "/imt-doctrine/")
        self.assertEqual(site_index.base_path("o/o.github.io"), "/")

    def test_root_files(self):
        found = versions("v0.2.0-demo", "v1.0.0")
        data = json.loads(site_index.versions_json(found))
        self.assertEqual(data["latest"], "v1.0.0")
        self.assertEqual(data["versions"][0], {"version": "v1.0.0", "channel": "final"})
        self.assertIn('url=latest/"', site_index.index_html(found))
        self.assertIn('url=next/"', site_index.index_html([]))
        page = site_index.not_found_html(found, "/imt-doctrine/")
        self.assertIn('const base = "/imt-doctrine/", fallback = "latest";', page)
        self.assertIn(r"v\d+\.\d+\.\d+(-rc\.\d+|-demo)?", page)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for args in (["init", "-q", "-b", "gh-pages"], ["config", "user.email", "t@example.org"],
                     ["config", "user.name", "t"], ["config", "commit.gpgsign", "false"],
                     ["config", "maintenance.auto", "false"]):
            self.git(*args)
        for folder in ("next", "v0.2.0-demo", "pr-preview"):
            (self.root / folder).mkdir()
            (self.root / folder / "index.html").write_text("x", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "site")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "tools" / "site_index.py"), "--top", str(self.root),
                               "--pages-ref", "gh-pages", *args], capture_output=True, text=True)

    def test_is_latest(self):
        self.assertEqual(self.run_cli("is-latest", "v0.2.1-demo").stdout.strip(), "true")
        self.assertEqual(self.run_cli("is-latest", "v0.1.0-demo").stdout.strip(), "false")
        self.assertEqual(self.run_cli("is-latest", "nonsense").returncode, 1)

    def test_root_writes_files(self):
        out = self.root / "_root"
        self.assertEqual(self.run_cli("root", "--out", str(out), "--base-path", "/x/").returncode, 0)
        self.assertEqual(json.loads((out / "versions.json").read_text())["latest"], "v0.2.0-demo")
        self.assertTrue((out / ".nojekyll").exists())
        self.assertIn('"/x/"', (out / "404.html").read_text())

    def test_missing_branch_means_no_versions(self):
        self.assertEqual(site_index.folders_at("no-such-branch", self.root), [])


if __name__ == "__main__":
    unittest.main()
