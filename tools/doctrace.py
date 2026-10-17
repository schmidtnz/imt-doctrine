"""Traceability checks for doctrine items declared in Markdown frontmatter."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import yaml

# type -> (ID prefix, allowed parent types)
TYPES: dict[str, tuple[str, tuple[str, ...]]] = {
    "principle": ("PRN", ()),
    "concept": ("CON", ("principle",)),
    "guideline": ("GDL", ("concept",)),
    "process": ("PRC", ("concept", "guideline")),
    "form": ("FRM", ("guideline", "process")),
}
DEFAULT_REVIEW_DAYS = 365
FRONTMATTER = re.compile(r"\A---[ \t]*\n(.*?\n)---[ \t]*\n", re.S)
LEVELS = ("error", "warning", "stale", "overdue")


@dataclass
class Item:
    id: str
    type: str
    title: str
    path: Path
    version: int = 1
    derives_from: dict[str, int] = field(default_factory=dict)
    requires_children: list[str] = field(default_factory=list)
    owner: str | None = None
    last_reviewed: dt.date | None = None
    review_days: int = DEFAULT_REVIEW_DAYS
    body: str = ""


@dataclass
class Finding:
    level: str
    message: str
    item_id: str | None = None
    path: Path | None = None
    parent: str | None = None


def split_frontmatter(text: str) -> tuple[dict | None, str]:
    """Return (frontmatter dict or None, body)."""
    m = FRONTMATTER.match(text)
    if not m:
        return None, text
    data = yaml.safe_load(m.group(1)) or {}
    return (data if isinstance(data, dict) else None), text[m.end():]


def parse_item(path: Path, text: str) -> tuple[Item | None, list[Finding]]:
    """Build an Item from one file; non-items return (None, [])."""
    try:
        meta, body = split_frontmatter(text)
    except yaml.YAMLError as exc:
        return None, [Finding("error", f"invalid frontmatter: {exc}", path=path)]
    if not meta or "id" not in meta:
        return None, []
    iid = str(meta["id"])
    problems = []
    for key in ("type", "title"):
        if key not in meta:
            problems.append(Finding("error", f"missing '{key}'", iid, path))
    if problems:
        return None, problems

    derives = meta.get("derives_from") or {}
    if not isinstance(derives, dict) or not all(isinstance(v, int) for v in derives.values()):
        problems.append(Finding(
            "error", "derives_from must map parent ID to the parent version it was written against", iid, path))
        derives = {}
    reviewed = meta.get("last_reviewed")
    if reviewed is not None and not isinstance(reviewed, dt.date):
        problems.append(Finding("error", "last_reviewed must be a YYYY-MM-DD date", iid, path))
        reviewed = None
    item = Item(
        id=iid, type=str(meta["type"]), title=str(meta["title"]), path=path,
        version=int(meta.get("version", 1)),
        derives_from={str(k): v for k, v in derives.items()},
        requires_children=list(meta.get("requires_children") or []),
        owner=meta.get("owner"), last_reviewed=reviewed,
        review_days=int(meta.get("review_days", DEFAULT_REVIEW_DAYS)),
        body=body,
    )
    return item, problems


def load_items(root: Path) -> tuple[dict[str, Item], list[Finding]]:
    """Read every Markdown item under root."""
    return _collect((p, p.read_text(encoding="utf-8"))
                    for p in sorted(root.rglob("*.md")) if "_build" not in p.parts)


def load_items_at(root: Path, ref: str) -> tuple[dict[str, Item], list[Finding]]:
    """Read every Markdown item under root as it was at a git ref; paths are relative to the repo."""
    top = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=root, text=True).strip()
    git = lambda *args: subprocess.check_output(["git", *args], cwd=top, text=True, encoding="utf-8")  # noqa: E731
    rel = Path(os.path.relpath(root.resolve(), top)).as_posix()
    names = git("ls-tree", "-r", "-z", "--name-only", ref, "--", rel).split("\0")
    return _collect((Path(name), git("show", f"{ref}:{name}"))
                    for name in sorted(names) if name.endswith(".md") and "_build" not in name.split("/"))


def _collect(files: Iterable[tuple[Path, str]]) -> tuple[dict[str, Item], list[Finding]]:
    items: dict[str, Item] = {}
    findings: list[Finding] = []
    for path, text in files:
        item, problems = parse_item(path, text)
        findings += problems
        if item is None:
            continue
        if item.id in items:
            findings.append(Finding("error", f"duplicate ID (also in {items[item.id].path})", item.id, path))
            continue
        items[item.id] = item
    return items, findings


def children_of(items: dict[str, Item]) -> dict[str, list[str]]:
    """Map each item ID to the IDs that derive from it."""
    kids: dict[str, list[str]] = {i: [] for i in items}
    for item in items.values():
        for parent in item.derives_from:
            if parent in kids:
                kids[parent].append(item.id)
    return kids


def _norm(text: str) -> str:
    return " ".join(text.split())


def check(items: dict[str, Item], today: dt.date,
          base: dict[str, tuple[int, str]] | None = None) -> list[Finding]:
    """Run all checks; base maps ID -> (version, body) at the comparison ref."""
    out: list[Finding] = []
    kids = children_of(items)
    for item in items.values():
        f = lambda level, msg: out.append(Finding(level, msg, item.id, item.path))  # noqa: E731
        if item.type not in TYPES:
            f("error", f"unknown type '{item.type}'")
            continue
        prefix, parent_types = TYPES[item.type]
        if not item.id.startswith(prefix + "-"):
            f("error", f"ID should start with {prefix}- for a {item.type}")
        if parent_types and not item.derives_from:
            f("error", f"a {item.type} must derive from a {' or '.join(parent_types)}")
        for pid, written_against in item.derives_from.items():
            parent = items.get(pid)
            if parent is None:
                f("error", f"derives from {pid}, which does not exist")
                continue
            if parent.type not in parent_types:
                f("error", f"a {item.type} cannot derive from a {parent.type} ({pid})")
            if written_against > parent.version:
                f("error", f"claims {pid} v{written_against}, but {pid} is only v{parent.version}")
            elif written_against < parent.version:
                out.append(Finding("stale", f"written against {pid} v{written_against}; "
                                   f"{pid} is now v{parent.version}", item.id, item.path, pid))
        for ctype in item.requires_children:
            if not any(items[k].type == ctype for k in kids[item.id]):
                f("warning", f"no {ctype} derives from this {item.type} yet")
        if not item.owner:
            f("warning", "no owner")
        if item.last_reviewed is None:
            f("overdue", "never reviewed")
        elif (today - item.last_reviewed).days > item.review_days:
            f("overdue", f"last reviewed {item.last_reviewed.isoformat()}")
        if base and item.id in base and kids[item.id]:
            old_version, old_body = base[item.id]
            if old_version == item.version and _norm(old_body) != _norm(item.body):
                f("warning", "text changed but version not bumped; bump it if the meaning changed")
    return out


def git_base(items: dict[str, Item], ref: str) -> dict[str, tuple[int, str]]:
    """Read each item's version and body as of a git ref."""
    base: dict[str, tuple[int, str]] = {}
    for item in items.values():
        rel = os.path.relpath(item.path.resolve(), _git_root(item.path))
        try:
            old = subprocess.check_output(
                ["git", "show", f"{ref}:{Path(rel).as_posix()}"],
                cwd=item.path.parent, text=True, encoding="utf-8", stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            continue
        old_item, _ = parse_item(item.path, old)
        if old_item and old_item.id == item.id:
            base[item.id] = (old_item.version, old_item.body)
    return base


def _git_root(path: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], cwd=path.parent, text=True).strip()


def render_report(items: dict[str, Item], findings: list[Finding], today: dt.date,
                  link: Callable[[Item], str] = lambda i: f"{i.id} {i.title}") -> str:
    """Markdown status report: counts, findings table, derivation tree."""
    counts = ", ".join(f"{sum(i.type == t for i in items.values())} {t}{'es' if t.endswith('s') else 's'}"
                       for t in TYPES)
    lines = ["# Traceability status", "",
             f"Generated {today.isoformat()} from {len(items)} items: {counts}.", "",
             "## Needs attention", ""]
    flagged = _flagged(findings)
    if flagged:
        lines += ["| Status | Item | Detail |", "|---|---|---|"]
        for f in flagged:
            who = link(items[f.item_id]) if f.item_id in items else (f.item_id or str(f.path))
            lines.append(f"| {f.level} | {who} | {f.message} |")
    else:
        lines.append("Nothing needs attention.")
    lines += ["", "## Derivation tree", ""]
    kids = children_of(items)
    stale = {(f.item_id, f.parent) for f in findings if f.level == "stale"}

    def walk(iid: str, depth: int, parent: str | None) -> None:
        item = items[iid]
        note = " (stale)" if (iid, parent) in stale else ""
        lines.append(f"{'  ' * depth}- {link(item)}, v{item.version}{note}")
        for kid in sorted(kids[iid]):
            walk(kid, depth + 1, iid)

    for root in sorted(i for i, it in items.items() if not it.derives_from):
        walk(root, 0, None)
    return "\n".join(lines) + "\n"


def overdue_report(items: dict[str, Item], findings: list[Finding]) -> str:
    """Markdown checklist of items due for review; empty when none."""
    due = [f for f in findings if f.level == "overdue"]
    if not due:
        return ""
    rows = [f"- [ ] **{f.item_id}** {items[f.item_id].title} ({f.message}; owner: "
            f"{items[f.item_id].owner or 'none'}) `{items[f.item_id].path}`" for f in due]
    return "Items past their review date:\n\n" + "\n".join(rows) + "\n"


def _flagged(findings: list[Finding]) -> list[Finding]:
    return sorted((f for f in findings if f.level in LEVELS),
                  key=lambda f: (LEVELS.index(f.level), f.item_id or "", f.message))


def count_summary(findings: list[Finding], skip_zero: bool = False) -> str:
    """Counts by level, such as "0 errors, 1 warning, 1 stale, 0 overdue"."""
    parts = []
    for level in LEVELS:
        n = sum(f.level == level for f in findings)
        if n or not skip_zero:
            parts.append(f"{n} {level}{'s' if n != 1 and level in ('error', 'warning') else ''}")
    return ", ".join(parts)


def comment_report(items: dict[str, Item], findings: list[Finding], base_items: dict[str, Item],
                   base_findings: list[Finding], base_ref: str) -> str:
    """Markdown pull request comment: findings this change adds or resolves, then all findings."""
    def who(f: Finding, pool: dict[str, Item]) -> str:
        item = pool.get(f.item_id or "")
        return f"{item.id} {item.title}" if item else (f.item_id or str(f.path))

    key = lambda f: (f.level, f.item_id, f.message)  # noqa: E731
    now, before = _flagged(findings), _flagged(base_findings)
    added = [f for f in now if key(f) not in {key(b) for b in before}]
    resolved = [f for f in before if key(f) not in {key(n) for n in now}]
    lines = ["## Traceability", ""]
    if added or resolved:
        lines += [f"Compared with `{base_ref}`: {len(added)} new, {len(resolved)} resolved.", "",
                  "| Change | Status | Item | Detail |", "|---|---|---|---|"]
        lines += [f"| new | {f.level} | {who(f, items)} | {f.message} |" for f in added]
        lines += [f"| resolved | {f.level} | {who(f, base_items)} | {f.message} |" for f in resolved]
    else:
        lines.append(f"No traceability changes compared with `{base_ref}`.")
    lines += ["", f"{len(items)} items: {count_summary(now)}. The Traceability status page has the full report."]
    if now:
        lines += ["", f"<details><summary>All findings ({len(now)})</summary>", "",
                  "| Status | Item | Detail |", "|---|---|---|"]
        lines += [f"| {f.level} | {who(f, items)} | {f.message} |" for f in now]
        lines += ["", "</details>"]
    return "\n".join(lines) + "\n"


def badge(findings: list[Finding]) -> str:
    """shields.io endpoint JSON summarising the findings."""
    flagged = _flagged(findings)
    color = ("red" if any(f.level == "error" for f in flagged)
             else "yellow" if flagged else "brightgreen")
    return json.dumps({"schemaVersion": 1, "label": "traceability",
                       "message": count_summary(flagged, skip_zero=True) or "all clear", "color": color})


def _annotate(f: Finding) -> str:
    kind = "error" if f.level == "error" else "warning" if f.level == "warning" else "notice"
    where = f" file={f.path}" if f.path else ""
    return f"::{kind}{where}::{f.item_id or ''} {f.message}".rstrip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path("docs"))
    ap.add_argument("--base", help="git ref to compare against for unbumped text changes")
    ap.add_argument("--report", type=Path, help="write Markdown status report here")
    ap.add_argument("--overdue", type=Path, help="write overdue-review checklist here")
    ap.add_argument("--comment", type=Path, help="write a pull request comment comparing with --base here")
    ap.add_argument("--badge", type=Path, help="write shields.io badge JSON here")
    ap.add_argument("--today", type=dt.date.fromisoformat, default=dt.date.today())
    args = ap.parse_args(argv)
    if args.comment and not args.base:
        ap.error("--comment needs --base")

    items, findings = load_items(args.root)
    base = git_base(items, args.base) if args.base else None
    findings += check(items, args.today, base)

    github = os.environ.get("GITHUB_ACTIONS") == "true"
    for f in findings:
        print(_annotate(f) if github else f"{f.level:8} {f.item_id or '-':8} {f.message}")
    if args.report:
        args.report.write_text(render_report(items, findings, args.today), encoding="utf-8")
    if args.overdue:
        args.overdue.write_text(overdue_report(items, findings), encoding="utf-8")
    if args.comment:
        base_items, base_findings = load_items_at(args.root, args.base)
        base_findings += check(base_items, args.today)
        args.comment.write_text(comment_report(items, findings, base_items, base_findings, args.base),
                                encoding="utf-8")
    if args.badge:
        args.badge.write_text(badge(findings) + "\n", encoding="utf-8")
    errors = sum(f.level == "error" for f in findings)
    print(f"{len(items)} items, {errors} errors, {len(findings) - errors} other findings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
