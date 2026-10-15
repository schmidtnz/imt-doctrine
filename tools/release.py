"""Release tooling: work out the next version, draft its changelog section, check release metadata.

Versions are vMAJOR.MINOR.PATCH (edition, amendment, editorial correction), optionally -rc.N for a
release candidate or -demo. Nobody types a version: `prepare` works it out from item changes since
the last release, so numbers can't be skipped or mistyped.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

sys.path.insert(0, str(Path(__file__).parent))
import doctrace  # noqa: E402

TAG = re.compile(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(?:rc\.([1-9]\d*)|(demo)))?")
HEADING = re.compile(r"^## +(.+?)[ \t]*$", re.M)
HEADING_PARTS = re.compile(r"(\S+)(?:\s+[—-]\s+(\d{4}-\d{2}-\d{2}))?")
SUMMARY = re.compile(r"^#{1,6}[ \t]*Changelog summary[ \t]*#*[ \t]*$", re.M | re.I)
NEXT_HEADING = re.compile(r"^#{1,6}\s", re.M)
LEVELS = ("patch", "minor", "major")
CHANNELS = ("final", "rc", "demo")
GROUPS = ("Doctrine", "Guidance and forms", "Site and tooling")
NONE_WORDS = {"none", "n/a", "na", "no", "-"}
CHANGELOG = "docs/changelog.md"
CONTRIBUTORS = "docs/contributors.md"
RELEASE_BRANCH = "release/next"


class ReleaseError(Exception):
    pass


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    channel: str = "final"  # final | rc | demo
    rc: int = 0

    @classmethod
    def parse(cls, text: str) -> Version | None:
        m = TAG.fullmatch(text)
        if not m:
            return None
        major, minor, patch, rc, demo = m.groups()
        return cls(int(major), int(minor), int(patch),
                   "rc" if rc else "demo" if demo else "final", int(rc or 0))

    @property
    def core(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def key(self) -> tuple[int, ...]:
        # SemVer precedence: pre-releases sort before their final, and "demo" before "rc".
        return (*self.core, {"demo": 0, "rc": 1, "final": 2}[self.channel], self.rc)

    def __str__(self) -> str:
        suffix = {"final": "", "rc": f"-rc.{self.rc}", "demo": "-demo"}[self.channel]
        return "v{}.{}.{}".format(*self.core) + suffix


def bump(core: tuple[int, int, int], level: str) -> tuple[int, int, int]:
    major, minor, patch = core
    return {"major": (major + 1, 0, 0), "minor": (major, minor + 1, 0),
            "patch": (major, minor, patch + 1)}[level]


def latest(tags: Iterable[Version]) -> Version | None:
    return max(tags, key=Version.key, default=None)


def anchor(tags: Iterable[Version]) -> Version | None:
    """The tag the next number is counted from: the latest one that isn't a release candidate."""
    return latest(t for t in tags if t.channel != "rc")


def _next_rc(tags: Iterable[Version], core: tuple[int, int, int]) -> int:
    return 1 + max((t.rc for t in tags if t.channel == "rc" and t.core == core), default=0)


def next_version(tags: list[Version], level: str, channel: str) -> Version:
    prev, base = latest(tags), anchor(tags)
    core = bump(base.core if base else (0, 0, 0), level)
    if prev and prev.channel == "rc" and prev.core > core:
        core = prev.core  # carry on the release candidate series, or promote it to final
    version = Version(*core, channel, _next_rc(tags, core) if channel == "rc" else 0)
    if prev and version.key() <= prev.key():
        raise ReleaseError(f"{version} would not come after the latest tag {prev}")
    return version


def successor_problem(tags: list[Version], version: Version) -> str | None:
    """Why version can't be the next release, or None if it can."""
    prev, base = latest(tags), anchor(tags)
    if prev and version.key() <= prev.key():
        return f"{version} must come after the latest tag {prev}"
    cores = {bump(base.core if base else (0, 0, 0), level) for level in LEVELS}
    if prev and prev.channel == "rc":
        cores.add(prev.core)
    if version.core not in cores:
        allowed = ", ".join("v{}.{}.{}".format(*c) for c in sorted(cores))
        return f"{version} skips a version; after {prev or 'no releases'} the next can be {allowed}"
    if version.channel == "rc" and version.rc != _next_rc(tags, version.core):
        return f"{version} should be {dataclasses.replace(version, rc=_next_rc(tags, version.core))}"
    return None


# --- what changed --------------------------------------------------------------------------------

@dataclass
class Change:
    id: str
    title: str
    kind: str  # new | changed | removed | wording
    old: int | None
    new: int | None
    doctrine: bool


def item_changes(old: dict[str, doctrace.Item], new: dict[str, doctrace.Item],
                 owned: Callable[[str], bool]) -> list[Change]:
    out = []
    for iid in sorted(set(old) | set(new)):
        o, n = old.get(iid), new.get(iid)
        item = n or o
        if o is None:
            kind = "new"
        elif n is None:
            kind = "removed"
        elif n.version != o.version:
            kind = "changed"
        elif doctrace._norm(n.body) != doctrace._norm(o.body) or n.title != o.title:
            kind = "wording"
        else:
            continue
        out.append(Change(iid, item.title, kind, o and o.version, n and n.version,
                          owned(Path(item.path).as_posix())))
    return out


def level_for(changes: list[Change], zero_major: bool) -> str:
    """Doctrine-tier meaning change: major; other item meaning change: minor; otherwise patch."""
    meaning = [c for c in changes if c.kind != "wording"]
    level = "major" if any(c.doctrine for c in meaning) else "minor" if meaning else "patch"
    if zero_major:  # before 1.0.0 everything moves down one step
        level = LEVELS[max(LEVELS.index(level) - 1, 0)]
    return level


def owners(codeowners: str) -> Callable[[str], bool]:
    """Return a test for 'has a code owner', i.e. is in the doctrine review tier."""
    rules = []
    for line in codeowners.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            pattern, *names = line.split()
            rules.append((_pattern(pattern), bool(names)))

    def owned(path: str) -> bool:
        result = False
        for rx, has_owner in rules:  # the last matching rule wins
            if rx.fullmatch(path):
                result = has_owner
        return result
    return owned


def _pattern(pattern: str) -> re.Pattern[str]:
    anchored = "/" in pattern.rstrip("/")
    body = pattern.strip("/")
    rx, i = "", 0
    while i < len(body):
        if body.startswith("**/", i):
            rx, i = rx + "(?:.*/)?", i + 3
        elif body.startswith("**", i):
            rx, i = rx + ".*", i + 2
        else:
            rx, i = rx + {"*": "[^/]*", "?": "[^/]"}.get(body[i], re.escape(body[i])), i + 1
    descends = pattern.endswith("/") or not any(c in body.rsplit("/", 1)[-1] for c in "*?")
    return re.compile(("" if anchored else "(?:.*/)?") + rx + ("(?:/.*)?" if descends else ""))


# --- pull requests -------------------------------------------------------------------------------

@dataclass(frozen=True)
class Person:
    login: str | None
    name: str | None

    @property
    def display(self) -> str:
        return self.name or f"@{self.login}"

    @property
    def markdown(self) -> str:
        return f"[{self.display}](https://github.com/{self.login})" if self.login else self.display


@dataclass
class Entry:
    number: int
    title: str
    author: Person | None  # None for bots
    summary: str | None  # None: no summary given; "": summary says none
    group: str
    people: list[Person] = dataclasses.field(default_factory=list)  # author and commit co-authors


def in_changelog(e: Entry) -> bool:
    """Summaries go in; a missing summary falls back to the title, except for bots."""
    return bool(e.summary) or (e.summary is None and e.author is not None)


def parse_summary(body: str | None) -> str | None:
    """Text under the 'Changelog summary' heading: '' if it says none, None if missing or blank."""
    body = (body or "").replace("\r\n", "\n")
    m = SUMMARY.search(body)
    if not m:
        return None
    rest = body[m.end():]
    end = NEXT_HEADING.search(rest)
    text = re.sub(r"<!--.*?-->", "", rest[:end.start()] if end else rest, flags=re.S).strip()
    if not text:
        return None
    return "" if text.lower().rstrip(".") in NONE_WORDS else text


def group_for(paths: Iterable[str], owned: Callable[[str], bool], root: str = "docs") -> str:
    content = [p for p in paths if p.startswith(root + "/") and p.endswith(".md") and p != CHANGELOG]
    if any(owned(p) for p in content):
        return GROUPS[0]
    return GROUPS[1] if content else GROUPS[2]


def entries_from(prs: list[dict], shas: set[str], owned: Callable[[str], bool],
                 profile_name: Callable[[str], str | None] = lambda login: None) -> list[Entry]:
    """Pull requests merged in this release. People are named as on their GitHub profile, else @login."""
    out = []
    for pr in prs:
        merge = (pr.get("mergeCommit") or {}).get("oid")
        if merge not in shas or pr.get("headRefName") == RELEASE_BRANCH:
            continue
        raw = pr.get("author") or {}
        author = None if raw.get("is_bot") or not raw.get("login") else \
            Person(raw["login"], raw.get("name") or profile_name(raw["login"]))
        people = [author] if author else []
        for commit in pr.get("commits") or []:
            for a in commit.get("authors") or []:
                login = a.get("login") or None
                if login and login.endswith("[bot]"):
                    continue
                person = Person(login, profile_name(login)) if login else Person(None, a.get("name") or None)
                if (person.login or person.name) and all(
                        (p.login or p.name) != (person.login or person.name) for p in people):
                    people.append(person)
        out.append(Entry(pr["number"], pr["title"], author, parse_summary(pr.get("body")),
                         group_for((f["path"] for f in pr.get("files") or []), owned), people))
    return sorted(out, key=lambda e: e.number)


def contributors(entries: list[Entry]) -> list[Person]:
    found: dict[str, Person] = {}
    for e in entries:
        if in_changelog(e):
            for p in e.people:
                found.setdefault(p.login or p.name or "", p)
    return sorted(found.values(), key=lambda p: p.display.lstrip("@").casefold())


def add_contributors(text: str, people: list[Person]) -> tuple[str, list[Person]]:
    """Add people missing from the contributors page's list, keeping it sorted. Returns (text, added)."""
    lines = text.rstrip("\n").split("\n")
    bullets = [i for i, line in enumerate(lines) if line.startswith("- ")]
    listed = [lines[i] for i in bullets]
    logins = {m.lower() for line in listed for m in re.findall(r"https://github\.com/([\w-]+)\)", line)}
    names = {re.sub(r"\[(.*?)\]\(.*?\)", r"\1", line[2:]).strip().casefold() for line in listed}
    added = [p for p in people if (p.login or "").lower() not in logins and p.display.casefold() not in names]
    if not added:
        return text, []
    entries = sorted(listed + [f"- {p.markdown}" for p in added],
                     key=lambda line: re.sub(r"\[(.*?)\]\(.*?\)", r"\1", line[2:]).lstrip("@").casefold())
    start = bullets[0] if bullets else len(lines) + 1
    rest = [line for i, line in enumerate(lines) if i not in bullets]
    if not bullets:
        rest.append("")
    return "\n".join(rest[:start] + entries + rest[start:]) + "\n", added


# --- changelog -----------------------------------------------------------------------------------

def sections(text: str) -> list[tuple[str, str]]:
    """(heading, body) for each '## ' section."""
    found = list(HEADING.finditer(text))
    return [(m.group(1), text[m.end():found[i + 1].start() if i + 1 < len(found) else len(text)].strip())
            for i, m in enumerate(found)]


def heading_version(heading: str) -> Version | None:
    m = HEADING_PARTS.fullmatch(heading)
    return Version.parse(m.group(1)) if m else None


def changelog_problems(text: str, tags: list[Version]) -> list[str]:
    problems, versions = [], []
    for heading, _ in sections(text):
        v = heading_version(heading)
        if v is None:
            problems.append(f"'## {heading}' is not a version heading like '## v1.2.0 — 2026-10-20'")
        else:
            versions.append(v)
    for newer, older in zip(versions, versions[1:]):
        if newer.key() <= older.key():
            problems.append(f"{newer} is listed above {older} but is not newer")
    for v in versions[1:]:
        if v not in tags:
            problems.append(f"{v} has no tag; only the newest version can be waiting for release")
    if versions and versions[0] not in tags:
        problem = successor_problem(tags, versions[0])
        if problem:
            problems.append(problem)
    return problems


def pending(text: str, tags: list[Version]) -> Version | None:
    """The newest changelog version if it hasn't been tagged yet."""
    for heading, _ in sections(text):
        v = heading_version(heading)
        return v if v and v not in tags else None
    return None


def notes(text: str, version: str) -> str:
    for heading, body in sections(text):
        v = heading_version(heading)
        if v and str(v) == version:
            return body + "\n"
    raise ReleaseError(f"no changelog section for {version}")


def insert_section(text: str, section: str) -> str:
    m = HEADING.search(text)
    if m:
        return text[:m.start()] + section.rstrip() + "\n\n" + text[m.start():]
    return text.rstrip() + "\n\n" + section.rstrip() + "\n"


def render_section(version: Version, date: dt.date, entries: list[Entry], changes: list[Change],
                   stale: list[doctrace.Finding], repo: str) -> str:
    lines = [f"## {version} — {date.isoformat()}", ""]
    for group in GROUPS:
        rows = [e for e in entries if e.group == group and in_changelog(e)]
        if rows:
            lines += [f"### {group}", ""]
            for e in rows:
                credit = f"[#{e.number}](https://github.com/{repo}/pull/{e.number})"
                if e.author:
                    credit += ", " + e.author.markdown
                text = (e.summary or e.title).replace("\n", "\n  ")
                lines.append(f"- {text} ({credit})")
            lines.append("")
    meaning = sorted((c for c in changes if c.kind != "wording"), key=lambda c: (not c.doctrine, c.id))
    wording = [c.id for c in changes if c.kind == "wording"]
    if meaning or wording:
        lines += ["### Items", ""]
        for c in meaning:
            what = {"new": f"new, v{c.new}", "removed": "removed", "changed": f"v{c.old} → v{c.new}"}[c.kind]
            lines.append(f"- **{c.id}** {c.title}: {what}")
        if wording:
            lines.append(f"- Wording only, meaning unchanged: {', '.join(wording)}")
        lines.append("")
    if stale:
        lines += ["### Needs review", ""]
        lines += [f"- **{f.item_id}** {f.message}" for f in stale]
        lines.append("")
    people = contributors(entries)
    if people:
        lines += ["Contributors: " + ", ".join(p.markdown for p in people), ""]
    return "\n".join(lines)


def render_body(version: Version, level: str, auto: str, changes: list[Change], since: Version | None,
                entries: list[Entry], zero_major: bool, newcomers: Iterable[Person] = ()) -> str:
    doctrine = [c.id for c in changes if c.kind != "wording" and c.doctrine]
    other = [c.id for c in changes if c.kind != "wording" and not c.doctrine]
    why = (f"doctrine items changed ({', '.join(doctrine)})" if doctrine else
           f"guidance or form items changed ({', '.join(other)})" if other else
           "no item changed meaning")
    if zero_major:
        why += "; before 1.0.0 each level moves down one step"
    lines = [f"Merging this publishes **{version}**: it tags the merge commit, builds the site and PDF, "
             "and creates the GitHub release with this version's changelog section as its notes.", "",
             f"**Version:** {level}" + (f" (chosen; item changes alone give {auto})" if level != auto else "")
             + f". Since {since or 'the start'}: {why}.", "",
             f"Reword anything in `{CHANGELOG}` in this pull request. Running *Prepare release* again "
             "rebuilds the section and discards those edits."]
    if newcomers:
        lines += ["", f"**New contributors**, added to `{CONTRIBUTORS}`: "
                  + ", ".join(p.display for p in newcomers)]
    missing = [e for e in entries if e.summary is None and in_changelog(e)]
    left_out = [e for e in entries if not in_changelog(e)]
    if missing:
        lines += ["", "**No changelog summary, so the title was used:** "
                  + ", ".join(f"#{e.number} {e.title}" for e in missing)]
    if left_out:
        lines += ["", "**Left out (summary says none, or a bot):** "
                  + ", ".join(f"#{e.number} {e.title}" for e in left_out)]
    return "\n".join(lines) + "\n"


# --- git and GitHub ------------------------------------------------------------------------------

def _git(top: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=top, text=True, encoding="utf-8")


def repo_tags(top: Path) -> list[Version]:
    """Version tags reachable from HEAD; other tags are ignored."""
    names = _git(top, "tag", "--list", "v*", "--merged", "HEAD").split()
    return [v for v in map(Version.parse, names) if v]


def items_at(top: Path, ref: str | None, root: str) -> dict[str, doctrace.Item]:
    if ref is None:
        return {}
    items: dict[str, doctrace.Item] = {}
    for name in _git(top, "ls-tree", "-r", "-z", "--name-only", ref, "--", root).split("\0"):
        if name.endswith(".md") and "_build" not in name.split("/"):
            item, _ = doctrace.parse_item(Path(name), _git(top, "show", f"{ref}:{name}"))
            if item:
                items.setdefault(item.id, item)
    return items


def items_now(top: Path, root: str) -> dict[str, doctrace.Item]:
    items, _ = doctrace.load_items(top / root)
    return {i: dataclasses.replace(it, path=Path(os.path.relpath(it.path, top)))
            for i, it in items.items()}


def merged_shas(top: Path, since: Version | None) -> set[str]:
    return set(_git(top, "rev-list", f"{since}..HEAD" if since else "HEAD").split())


def github_prs(repo: str, base: str) -> list[dict]:
    out = subprocess.check_output(
        ["gh", "pr", "list", "-R", repo, "--state", "merged", "--base", base, "--limit", "1000",
         "--json", "number,title,body,author,commits,mergeCommit,files,headRefName"],
        text=True, encoding="utf-8")
    return json.loads(out)


_names: dict[str, str | None] = {}


def github_profile_name(login: str) -> str | None:
    """The name on a GitHub profile, or None if it has none."""
    if login not in _names:
        try:
            _names[login] = subprocess.check_output(
                ["gh", "api", f"users/{login}", "--jq", ".name // empty"], text=True, encoding="utf-8",
                stderr=subprocess.DEVNULL).strip() or None
        except (subprocess.CalledProcessError, FileNotFoundError):
            _names[login] = None
    return _names[login]


def prepare(top: Path, channel: str, bump_to: str, repo: str, today: dt.date,
            prs: Callable[[], list[dict]], profile_name: Callable[[str], str | None] = lambda login: None,
            root: str = "docs") -> tuple[Version, dict[str, str], str]:
    """Return (version, {path: new text} for each changed file, pull request description)."""
    tags = repo_tags(top)
    text = (top / CHANGELOG).read_text(encoding="utf-8")
    problems = changelog_problems(text, tags)
    if problems:
        raise ReleaseError("; ".join(problems))
    waiting = pending(text, tags)
    if waiting:
        raise ReleaseError(f"{waiting} is already waiting to be published: run the Release workflow, "
                           "or remove its section first")
    owned = owners((top / ".github" / "CODEOWNERS").read_text(encoding="utf-8"))
    now = items_now(top, root)
    base = anchor(tags)
    zero_major = (base.major if base else 0) == 0
    auto = level_for(item_changes(items_at(top, base and str(base), root), now, owned), zero_major)
    level = auto if bump_to == "auto" else bump_to
    if LEVELS.index(level) < LEVELS.index(auto):
        raise ReleaseError(f"item changes need at least a {auto} release, not {level}")
    version = next_version(tags, level, channel)
    since = latest(tags) if channel == "rc" else base
    changes = item_changes(items_at(top, since and str(since), root), now, owned)
    shas = merged_shas(top, since)
    if not shas:
        raise ReleaseError(f"nothing has changed since {since}")
    entries = entries_from(prs(), shas, owned, profile_name)
    stale = [f for f in doctrace.check(now, today) if f.level == "stale"]
    section = render_section(version, today, entries, changes, stale, repo)
    files = {CHANGELOG: insert_section(text, section)}
    newcomers: list[Person] = []
    if (top / CONTRIBUTORS).exists():
        page, newcomers = add_contributors((top / CONTRIBUTORS).read_text(encoding="utf-8"),
                                           contributors(entries))
        if newcomers:
            files[CONTRIBUTORS] = page
    body = render_body(version, level, auto, changes, since, entries, zero_major, newcomers)
    return version, files, body + "\n---\n\n" + section


# --- command line --------------------------------------------------------------------------------

def _output(name: str, value: str) -> None:
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")


def _fail(message: str, file: str | None = None) -> int:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::error{f' file={file}' if file else ''}::{message}")
    else:
        print(f"error: {message}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--top", type=Path, default=Path(__file__).resolve().parents[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare", help="write the next version's changelog section")
    p.add_argument("--channel", choices=CHANNELS, default="final")
    p.add_argument("--bump", choices=("auto", *LEVELS), default="auto")
    p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "schmidtnz/imt-doctrine"))
    p.add_argument("--base", default="main", help="branch pull requests merge into")
    p.add_argument("--body", type=Path, help="write the release pull request description here")
    p.add_argument("--dry-run", action="store_true", help="print instead of writing the changelog")
    sub.add_parser("pending", help="print the newest changelog version if it has no tag yet")
    n = sub.add_parser("notes", help="print one version's changelog section")
    n.add_argument("version")
    sub.add_parser("check", help="check changelog headings against tags")
    s = sub.add_parser("summary", help="check a pull request description (PR_BODY) has a changelog summary")
    s.add_argument("--body-env", default="PR_BODY")
    args = ap.parse_args(argv)
    top = args.top
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        if args.cmd == "summary":
            if parse_summary(os.environ.get(args.body_env)) is None:
                return _fail("Add a '## Changelog summary' section at the end of the pull request "
                             "description: one or two sentences for readers, or 'none'.")
            print("Changelog summary found.")
            return 0
        text = (top / CHANGELOG).read_text(encoding="utf-8")
        tags = repo_tags(top)
        if args.cmd == "notes":
            sys.stdout.write(notes(text, args.version))
            return 0
        problems = changelog_problems(text, tags)
        if args.cmd == "check":
            for problem in problems:
                _fail(problem, CHANGELOG)
            if not problems:
                print(f"{CHANGELOG} is consistent with {len(tags)} tags.")
            return 1 if problems else 0
        if args.cmd == "pending":
            if problems:
                return _fail("; ".join(problems), CHANGELOG)
            version = pending(text, tags)
            print(version or "Nothing to release: the newest changelog version is already tagged.")
            _output("version", str(version or ""))
            return 0
        version, files, body = prepare(top, args.channel, args.bump, args.repo, dt.date.today(),
                                       lambda: github_prs(args.repo, args.base), github_profile_name)
    except (ReleaseError, subprocess.CalledProcessError) as exc:
        return _fail(str(exc))
    if args.dry_run:
        print(body)
    else:
        for path, new_text in files.items():
            (top / path).write_text(new_text, encoding="utf-8", newline="\n")
        if args.body:
            args.body.write_text(body, encoding="utf-8")
    print(version)
    _output("version", str(version))
    return 0


if __name__ == "__main__":
    sys.exit(main())
