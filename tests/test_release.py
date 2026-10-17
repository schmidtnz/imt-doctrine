"""Unit tests for the release tooling."""
import datetime as dt
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import doctrace  # noqa: E402
import release  # noqa: E402
from release import Version as V  # noqa: E402

TODAY = dt.date(2026, 10, 20)


def tags(*names):
    return [V.parse(n) for n in names]


class VersionTests(unittest.TestCase):
    def test_parse_round_trip(self):
        for name in ("v0.1.0", "v1.2.3", "v2.0.0-rc.1", "v10.20.30-rc.12", "v0.2.0-demo"):
            self.assertEqual(str(V.parse(name)), name)

    def test_rejects_malformed(self):
        for name in ("V1.2.0", "v12", "v12.2", "v12.03.0", "v1.2.03", "1.2.0", "v1.0.0-rc",
                     "v1.0.0-rc.0", "v1.0.0-beta.1", "v1.0.0-demo.2", "v1.2.0 "):
            self.assertIsNone(V.parse(name), name)

    def test_semver_order(self):
        order = ["v0.2.0-demo", "v0.2.0-rc.1", "v0.2.0-rc.2", "v0.2.0", "v0.10.0", "v1.0.0"]
        self.assertEqual([str(v) for v in sorted(tags(*reversed(order)), key=V.key)], order)


class NextVersionTests(unittest.TestCase):
    def nxt(self, existing, level, channel="final"):
        return str(release.next_version(tags(*existing), level, channel))

    def test_first_release(self):
        self.assertEqual(self.nxt([], "minor"), "v0.1.0")

    def test_levels(self):
        self.assertEqual(self.nxt(["v1.4.2"], "patch"), "v1.4.3")
        self.assertEqual(self.nxt(["v1.4.2"], "minor"), "v1.5.0")
        self.assertEqual(self.nxt(["v1.4.2"], "major"), "v2.0.0")

    def test_release_candidates_then_final(self):
        self.assertEqual(self.nxt(["v1.4.2"], "major", "rc"), "v2.0.0-rc.1")
        self.assertEqual(self.nxt(["v1.4.2", "v2.0.0-rc.1"], "patch", "rc"), "v2.0.0-rc.2")
        self.assertEqual(self.nxt(["v1.4.2", "v2.0.0-rc.1", "v2.0.0-rc.2"], "major"), "v2.0.0")

    def test_bigger_change_during_candidates_moves_on(self):
        self.assertEqual(self.nxt(["v1.4.2", "v1.5.0-rc.1"], "major", "rc"), "v2.0.0-rc.1")

    def test_demo_releases_count_like_finals(self):
        self.assertEqual(self.nxt(["v0.1.0-demo"], "minor", "demo"), "v0.2.0-demo")

    def test_cannot_go_backwards(self):
        with self.assertRaises(release.ReleaseError):
            release.next_version(tags("v1.4.2", "v2.0.0-rc.1"), "major", "demo")


class SuccessorTests(unittest.TestCase):
    def problem(self, existing, candidate):
        return release.successor_problem(tags(*existing), V.parse(candidate))

    def test_valid_successors(self):
        for candidate in ("v1.4.3", "v1.5.0", "v2.0.0", "v2.0.0-rc.1", "v1.5.0-demo"):
            self.assertIsNone(self.problem(["v1.4.2"], candidate), candidate)
        self.assertIsNone(self.problem(["v1.4.2", "v2.0.0-rc.1"], "v2.0.0"))

    def test_skipped_versions(self):
        self.assertIn("skips", self.problem(["v5.0.0"], "v12.0.0"))
        self.assertIn("skips", self.problem(["v1.4.2"], "v1.6.0"))
        self.assertIn("skips", self.problem([], "v1.1.0"))

    def test_not_newer_or_wrong_candidate_number(self):
        self.assertIn("after", self.problem(["v1.4.2"], "v1.4.2"))
        self.assertIn("should be v2.0.0-rc.2", self.problem(["v1.4.2", "v2.0.0-rc.1"], "v2.0.0-rc.3"))


def item(iid, version=1, body="Text.", path="docs/x.md"):
    return doctrace.Item(id=iid, type="principle", title=iid, path=Path(path), version=version, body=body)


class ChangeTests(unittest.TestCase):
    owned = staticmethod(lambda p: p.startswith("docs/part-2/"))

    def test_kinds_and_tier(self):
        old = {"PRN-01": item("PRN-01", 1, path="docs/part-2/a.md"), "GDL-01": item("GDL-01"),
               "GDL-02": item("GDL-02"), "GDL-03": item("GDL-03")}
        new = {"PRN-01": item("PRN-01", 2, path="docs/part-2/a.md"), "GDL-01": item("GDL-01", body="Other."),
               "GDL-03": item("GDL-03"), "FRM-01": item("FRM-01")}
        changes = {c.id: (c.kind, c.doctrine) for c in release.item_changes(old, new, self.owned)}
        self.assertEqual(changes, {"PRN-01": ("changed", True), "GDL-01": ("wording", False),
                                   "GDL-02": ("removed", False), "FRM-01": ("new", False)})

    def test_levels(self):
        c = lambda kind, doctrine: release.Change("X", "X", kind, 1, 2, doctrine)  # noqa: E731
        self.assertEqual(release.level_for([c("changed", True)], False), "major")
        self.assertEqual(release.level_for([c("new", False), c("wording", True)], False), "minor")
        self.assertEqual(release.level_for([c("wording", True)], False), "patch")
        self.assertEqual(release.level_for([c("changed", True)], True), "minor")
        self.assertEqual(release.level_for([c("removed", False)], True), "patch")


class OwnersTests(unittest.TestCase):
    def test_repo_codeowners(self):
        owned = release.owners((ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8"))
        self.assertTrue(owned("docs/part-2/prn-01-unified.md"))
        self.assertTrue(owned("docs/part-3/3-1-concepts/con-01-hierarchy.md"))
        self.assertTrue(owned("docs/glossary.md"))
        self.assertFalse(owned("docs/part-3/3-3-guidelines/gdl-01-managing-imt.md"))
        self.assertFalse(owned("docs/forms/frm-01-team-debrief.md"))

    def test_patterns_and_last_rule_wins(self):
        owned = release.owners(textwrap.dedent("""
            *.md        @a
            docs/*      @b
            /docs/free/
            **/keep.md  @c
        """))
        self.assertTrue(owned("README.md"))
        self.assertTrue(owned("docs/x.txt"))
        self.assertFalse(owned("docs/sub/x.txt"))
        self.assertFalse(owned("docs/free/x.md"))
        self.assertTrue(owned("docs/free/deep/keep.md"))


class SummaryTests(unittest.TestCase):
    def test_parse(self):
        p = release.parse_summary
        self.assertEqual(p("Intro\r\n\r\n## Changelog summary\r\n\r\nAdds PRN-16.\r\n"), "Adds PRN-16.")
        self.assertEqual(p("### changelog SUMMARY\nLine one.\nLine two.\n## Other\nx"), "Line one.\nLine two.")
        self.assertEqual(p("## Changelog summary\n<!-- hint -->\nNone.\n"), "")
        self.assertIsNone(p("## Changelog summary\n<!-- One or two sentences -->\n"))
        self.assertIsNone(p("No section here"))
        self.assertIsNone(p(None))

    def test_group_for(self):
        owned = lambda p: p.startswith("docs/part-2/")  # noqa: E731
        self.assertEqual(release.group_for(["docs/part-2/a.md", "docs/forms/f.md"], owned), "Doctrine")
        self.assertEqual(release.group_for(["docs/forms/f.md"], owned), "Guidance and forms")
        self.assertEqual(release.group_for(["tools/x.py", "docs/changelog.md"], owned), "Site and tooling")
        self.assertEqual(release.group_for(["docs/licence.md", "docs/contributors.md"], owned), "Site and tooling")
        owned = lambda p: p == "docs/glossary.md"  # noqa: E731
        self.assertEqual(release.group_for(["docs/glossary.md"], owned), "Doctrine")

    def test_github_prs_fetches_commits_only_for_merged_in_range(self):
        listed = [{"number": 1, "mergeCommit": {"oid": "a"}}, {"number": 2, "mergeCommit": {"oid": "old"}},
                  {"number": 3, "mergeCommit": None}]
        calls = []

        def gh(args, **kwargs):
            calls.append(args)
            if args[1:3] == ["pr", "list"]:
                self.assertNotIn("commits", args[-1].split(","))
                return json.dumps(listed)
            return json.dumps({"commits": [{"authors": [{"login": "amy"}]}]})

        with mock.patch.object(release.subprocess, "check_output", gh):
            prs = release.github_prs("o/r", "main", {"a"})
        self.assertEqual([(p["number"], p["commits"]) for p in prs], [(1, [{"authors": [{"login": "amy"}]}])])
        self.assertEqual(calls[1], ["gh", "pr", "view", "1", "-R", "o/r", "--json", "commits"])
        self.assertEqual(len(calls), 2)

    def test_entries_from(self):
        commits = [{"authors": [{"login": "amy", "name": "amy-git"}, {"login": "ben", "name": "b"}]},
                   {"authors": [{"login": "", "name": "Offline Olga"}, {"login": "github-actions[bot]"}]}]
        prs = [
            {"number": 3, "title": "T3", "body": "## Changelog summary\nS3", "author": {"login": "amy", "name": ""},
             "mergeCommit": {"oid": "a"}, "files": [{"path": "docs/forms/f.md"}], "headRefName": "x",
             "commits": commits},
            {"number": 4, "title": "Old", "body": "", "author": {"login": "bob"},
             "mergeCommit": {"oid": "zzz"}, "files": [], "headRefName": "y"},
            {"number": 5, "title": "Release", "body": "", "author": {"login": "app/github-actions", "is_bot": True},
             "mergeCommit": {"oid": "b"}, "files": [], "headRefName": "release/next"},
            {"number": 6, "title": "Bump x", "body": "", "author": {"login": "app/dependabot", "is_bot": True},
             "mergeCommit": {"oid": "c"}, "files": [], "headRefName": "dependabot/pip/x"},
        ]
        names = {"amy": "Amy Ng"}
        entries = release.entries_from(prs, {"a", "b", "c"}, lambda p: False, names.get)
        P = release.Person
        self.assertEqual([(e.number, e.author, e.summary, e.group) for e in entries],
                         [(3, P("amy", "Amy Ng"), "S3", "Guidance and forms"), (6, None, None, "Site and tooling")])
        self.assertEqual(entries[0].people, [P("amy", "Amy Ng"), P("ben", None), P(None, "Offline Olga")])
        self.assertFalse(release.in_changelog(entries[1]))
        self.assertEqual([p.markdown for p in release.contributors(entries)],
                         ["[Amy Ng](https://github.com/amy)", "[@ben](https://github.com/ben)", "Offline Olga"])

    def test_add_contributors(self):
        P = release.Person
        page = "# Contributors\n\nIntro.\n\n- [Amy Ng](https://github.com/amy)\n- Zed Hand\n\nFooter.\n"
        text, added = release.add_contributors(page, [P("AMY", "Amy N."), P("bo", "Bo Li"), P(None, "Zed Hand")])
        self.assertEqual(added, [P("bo", "Bo Li")])
        self.assertEqual(text, "# Contributors\n\nIntro.\n\n- [Amy Ng](https://github.com/amy)\n"
                               "- [Bo Li](https://github.com/bo)\n- Zed Hand\n\nFooter.\n")
        self.assertEqual(release.add_contributors(text, [P("bo", None)]), (text, []))
        text, _ = release.add_contributors("# Contributors\n", [P("cy", None)])
        self.assertEqual(text, "# Contributors\n\n- [@cy](https://github.com/cy)\n")


CHANGELOG = """# Changelog

## v0.2.0 — 2026-10-01

- Two.

## v0.1.0

- One.
"""


class ChangelogTests(unittest.TestCase):
    def test_consistent(self):
        self.assertEqual(release.changelog_problems(CHANGELOG, tags("v0.1.0", "v0.2.0")), [])
        self.assertEqual(release.changelog_problems(CHANGELOG, tags("v0.1.0")), [])
        self.assertEqual(release.pending(CHANGELOG, tags("v0.1.0")), V.parse("v0.2.0"))
        self.assertIsNone(release.pending(CHANGELOG, tags("v0.1.0", "v0.2.0")))

    def test_problems(self):
        p = release.changelog_problems
        self.assertIn("not a version heading", p(CHANGELOG.replace("v0.2.0 —", "V0.2.0 —"), tags("v0.1.0"))[0])
        self.assertIn("skips", p(CHANGELOG.replace("v0.2.0", "v0.12.0"), tags("v0.1.0"))[0])
        self.assertIn("has no tag", p(CHANGELOG, [])[0])
        swapped = "# Changelog\n\n## v0.1.0\n\n## v0.2.0\n"
        self.assertIn("not newer", p(swapped, tags("v0.1.0", "v0.2.0"))[0])

    def test_notes_and_insert(self):
        self.assertEqual(release.notes(CHANGELOG, "v0.2.0"), "- Two.\n")
        with self.assertRaises(release.ReleaseError):
            release.notes(CHANGELOG, "v9.0.0")
        text = release.insert_section(CHANGELOG, "## v0.3.0 — 2026-10-20\n\n- Three.\n")
        self.assertEqual([h for h, _ in release.sections(text)][:2], ["v0.3.0 — 2026-10-20", "v0.2.0 — 2026-10-01"])

    def test_render_section(self):
        amy, bob, cy = release.Person("amy", None), release.Person("bob", "Bob"), release.Person("Cy", "Cy Ro")
        entries = [release.Entry(1, "Title one", amy, "Adds a form.\nSecond line.", "Guidance and forms", [amy]),
                   release.Entry(2, "Fix typo", bob, "", "Doctrine", [bob]),
                   release.Entry(3, "Doctrine change", cy, None, "Doctrine", [cy, amy])]
        changes = [release.Change("PRN-03", "Partnerships", "changed", 1, 2, True),
                   release.Change("FRM-04", "Log", "new", None, 1, False),
                   release.Change("GDL-01", "Managing", "wording", 1, 1, False)]
        findings = [doctrace.Finding("stale", "written against PRN-03 v1; PRN-03 is now v2", "CON-03"),
                    doctrace.Finding("overdue", "last reviewed 2025-01-01", "GDL-01")]
        text = release.render_section(V.parse("v1.1.0"), TODAY, entries, changes, findings, "o/r")
        self.assertTrue(text.startswith("## v1.1.0 — 2026-10-20\n"))
        self.assertLess(text.index("### Doctrine"), text.index("### Guidance and forms"))
        self.assertIn("- Doctrine change ([#3](https://github.com/o/r/pull/3), [Cy Ro](https://github.com/Cy))", text)
        self.assertIn("- Adds a form.\n  Second line. ([#1]", text)
        self.assertNotIn("Fix typo", text)
        self.assertIn("- **PRN-03** Partnerships: v1 → v2\n- **FRM-04** Log: new, v1\n", text)
        self.assertIn("Wording only, meaning unchanged: GDL-01", text)
        self.assertIn("- **CON-03** written against PRN-03 v1", text)
        self.assertNotIn("GDL-01 last reviewed", text)
        self.assertIn("Traceability at release: 1 stale, 1 overdue.\n", text)
        self.assertIn("Contributors: [@amy](https://github.com/amy), [Cy Ro](https://github.com/Cy)\n", text)
        self.assertIn("Traceability at release: all clear.",
                      release.render_section(V.parse("v1.1.0"), TODAY, entries, changes, [], "o/r"))


def write(root: Path, name: str, meta: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{textwrap.dedent(meta).strip()}\n---\n\n# T\n\nText.\n", encoding="utf-8")


class PrepareTests(unittest.TestCase):
    """End to end in a scratch repository: tag, change items, prepare the next release."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@example.org"],
                     ["config", "user.name", "t"], ["config", "commit.gpgsign", "false"],
                     ["config", "tag.gpgsign", "false"]):
            self.git(*args)
        (self.root / ".github").mkdir()
        (self.root / ".github" / "CODEOWNERS").write_text("/docs/part-2/ @owner\n", encoding="utf-8")
        write(self.root, "docs/part-2/prn-01.md", "id: PRN-01\ntype: principle\ntitle: Safety")
        write(self.root, "docs/part-3/con-01.md",
              "id: CON-01\ntype: concept\ntitle: Hazards\nderives_from:\n  PRN-01: 1")
        (self.root / "docs" / "changelog.md").write_text("# Changelog\n\n## v1.0.0\n\n- First.\n", encoding="utf-8")
        (self.root / "docs" / "contributors.md").write_text(
            "# Contributors\n\n- [Old Hand](https://github.com/old)\n", encoding="utf-8")
        self.commit("first")
        self.git("tag", "v1.0.0")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, text=True).stdout

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD").strip()

    def prepare(self, prs, channel="final", bump="auto", **kwargs):
        return release.prepare(self.root, channel, bump, "o/r", TODAY, lambda shas: prs, {"amy": "Amy Ng"}.get,
                               **kwargs)

    def pr(self, sha, summary="Clarifies hazards."):
        return {"number": 7, "title": "Concept", "body": f"## Changelog summary\n{summary}",
                "author": {"login": "amy"}, "mergeCommit": {"oid": sha},
                "files": [{"path": "docs/part-3/notes.md"}], "headRefName": "edit"}

    def test_guidance_change_is_minor_with_entries(self):
        write(self.root, "docs/part-3/con-01.md",
              "id: CON-01\ntype: concept\ntitle: Hazards\nversion: 2\nderives_from:\n  PRN-01: 1")
        sha = self.commit("change concept")
        prs = [{"number": 7, "title": "Concept", "body": "## Changelog summary\nClarifies hazards.",
                "author": {"login": "amy"}, "mergeCommit": {"oid": sha},
                "files": [{"path": "docs/part-3/con-01.md"}], "headRefName": "edit"},
               {"number": 1, "title": "Before", "body": "", "author": {"login": "old"},
                "mergeCommit": {"oid": "not-in-range"}, "files": [], "headRefName": "x"}]
        version, files, body = self.prepare(prs)
        text = files[release.CHANGELOG]
        self.assertEqual(str(version), "v1.1.0")
        self.assertIn("- [Amy Ng](https://github.com/amy)\n- [Old Hand]", files[release.CONTRIBUTORS])
        self.assertIn("**New contributors**, added to `docs/contributors.md`: Amy Ng", body)
        self.assertIn("## v1.1.0 — 2026-10-20\n\n### Guidance and forms\n\n- Clarifies hazards. ([#7]", text)
        self.assertIn("- **CON-01** Hazards: v1 → v2", text)
        self.assertNotIn("Before", text)
        self.assertIn("**Version:** minor. Since v1.0.0: guidance or form items changed (CON-01).", body)
        self.assertEqual(release.changelog_problems(text, release.repo_tags(self.root)), [])

    def test_nothing_to_release(self):
        with self.assertRaises(release.ReleaseError):
            self.prepare([])
        with self.assertRaises(release.NothingToRelease):
            self.prepare([], skip_empty=True)

    def test_skip_empty_needs_a_summary_or_item_change(self):
        (self.root / "docs" / "part-3" / "notes.md").write_text("# Notes\n", encoding="utf-8")
        sha = self.commit("page")
        with self.assertRaises(release.NothingToRelease):
            self.prepare([self.pr(sha, summary="none")], skip_empty=True)
        self.assertEqual(str(self.prepare([self.pr(sha)], skip_empty=True)[0]), "v1.0.1")

    def test_keep_carries_open_release_channel_and_higher_bump(self):
        (self.root / "docs" / "part-3" / "notes.md").write_text("# Notes\n", encoding="utf-8")
        sha = self.commit("page")
        keep = release.Version.parse
        self.assertEqual(str(self.prepare([self.pr(sha)], channel="demo", keep=keep("v1.1.0-rc.1"))[0]),
                         "v1.1.0-rc.1")
        self.assertEqual(str(self.prepare([self.pr(sha)], channel="demo", keep=keep("v1.0.1"))[0]), "v1.0.1")
        write(self.root, "docs/part-2/prn-01.md", "id: PRN-01\ntype: principle\ntitle: Safety\nversion: 2")
        self.commit("doctrine")
        self.assertEqual(str(self.prepare([], keep=keep("v1.1.0"))[0]), "v2.0.0")

    def test_doctrine_change_is_major_and_bump_cannot_go_lower(self):
        write(self.root, "docs/part-2/prn-01.md", "id: PRN-01\ntype: principle\ntitle: Safety\nversion: 2")
        self.commit("doctrine")
        self.assertEqual(str(self.prepare([])[0]), "v2.0.0")
        with self.assertRaises(release.ReleaseError):
            self.prepare([], bump="minor")
        files = self.prepare([])[1]
        self.assertIn("Needs review", files[release.CHANGELOG])
        self.assertNotIn(release.CONTRIBUTORS, files)

    def test_wording_only_is_patch_and_waiting_release_blocks(self):
        (self.root / "docs" / "part-3" / "con-01.md").write_text(
            "---\nid: CON-01\ntype: concept\ntitle: Hazards\nderives_from:\n  PRN-01: 1\n---\n\nNew words.\n",
            encoding="utf-8")
        self.commit("wording")
        version, files, _ = self.prepare([], channel="rc")
        self.assertEqual(str(version), "v1.0.1-rc.1")
        (self.root / "docs" / "changelog.md").write_text(files[release.CHANGELOG], encoding="utf-8")
        with self.assertRaises(release.ReleaseError):
            self.prepare([])
        with self.assertRaises(release.NothingToRelease):
            self.prepare([], skip_empty=True)

    def test_cli_pending_and_notes(self):
        out = subprocess.run([sys.executable, str(ROOT / "tools" / "release.py"), "--top", str(self.root),
                              "notes", "v1.0.0"], capture_output=True, text=True, check=True).stdout
        self.assertEqual(out.strip(), "- First.")
        rc = release.main(["--top", str(self.root), "pending"])
        self.assertEqual(rc, 0)


class RepoContentTests(unittest.TestCase):
    def test_changelog_matches_tags(self):
        try:
            found = release.repo_tags(ROOT)
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.skipTest("not a git checkout")
        if not found:
            self.skipTest("no tags fetched")
        text = (ROOT / release.CHANGELOG).read_text(encoding="utf-8")
        self.assertEqual(release.changelog_problems(text, found), [])


if __name__ == "__main__":
    unittest.main()
