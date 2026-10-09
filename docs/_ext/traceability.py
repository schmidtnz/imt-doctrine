"""Sphinx extension: trace box on each doctrine item and a generated status page."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from sphinx.util import logging

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import doctrace  # noqa: E402

logger = logging.getLogger(__name__)
STATUS_FILE = Path("status") / "traceability.md"


def _docname(srcdir: Path, item: doctrace.Item) -> str:
    return item.path.resolve().relative_to(srcdir).with_suffix("").as_posix()


def _builder_inited(app) -> None:
    # Load items once, report errors as Sphinx warnings, regenerate the status page.
    src = Path(app.srcdir).resolve()
    today = dt.date.today()
    items, findings = doctrace.load_items(src)
    findings += doctrace.check(items, today)
    docs = {iid: _docname(src, it) for iid, it in items.items()}
    for f in findings:
        if f.level == "error":
            logger.warning("doctrace: %s %s (%s)", f.item_id or "", f.message, f.path or "")

    def link(it):
        return f"{{doc}}`{it.id} {it.title} </{docs[it.id]}>`"

    report = doctrace.render_report(items, findings, today, link)
    out = src / STATUS_FILE
    out.parent.mkdir(exist_ok=True)
    if not out.exists() or out.read_text(encoding="utf-8") != report:
        out.write_text(report, encoding="utf-8")
    app.doctrace = {"items": items, "findings": findings, "docs": docs,
                    "by_doc": {d: i for i, d in docs.items()}}


def _box(item, items, findings, docs) -> str:
    """MyST admonition summarising an item's links, version and review state."""
    def ref(i):
        return f"{{doc}}`{i} </{docs[i]}>`"

    stale = {f.parent for f in findings if f.level == "stale" and f.item_id == item.id}
    rows = []
    if item.derives_from:
        parts = []
        for pid, v in item.derives_from.items():
            text = f"{ref(pid)} v{v}" if pid in items else f"{pid} (missing)"
            if pid in stale:
                text += f" (**review needed:** {pid} is now v{items[pid].version})"
            parts.append(text)
        rows.append("**Derives from:** " + "; ".join(parts))
    kids = sorted(doctrace.children_of(items)[item.id])
    if kids:
        rows.append("**Supports:** " + ", ".join(ref(k) for k in kids))
    rows.append(f"**Owner:** {item.owner or 'none'} · **Last reviewed:** {item.last_reviewed or 'never'}")
    return "\n".join([
        f":::{{admonition}} {item.id} · {item.type.title()} · version {item.version}",
        f":class: doctrace{' stale' if stale else ''}", "",
        *(f"- {r}" for r in rows), ":::", ""])


def _source_read(app, docname, source) -> None:
    # Swap frontmatter for blank lines (keeps line numbers) and add the box under the H1.
    state = app.doctrace
    iid = state["by_doc"].get(docname)
    if iid is None:
        return
    text = source[0]
    m = doctrace.FRONTMATTER.match(text)
    if m:
        text = "\n" * m.group(0).count("\n") + text[m.end():]
    lines = text.split("\n")
    box = _box(state["items"][iid], state["items"], state["findings"], state["docs"])
    for n, line in enumerate(lines):
        if line.startswith("# "):
            lines[n + 1:n + 1] = ["", *box.split("\n")]
            break
    source[0] = "\n".join(lines)


def _always_reread(app, env, added, changed, removed):
    # A parent's version change alters its children's boxes, so re-read every item.
    return list(app.doctrace["by_doc"]) + [STATUS_FILE.with_suffix("").as_posix()]


def setup(app):
    app.connect("builder-inited", _builder_inited)
    app.connect("source-read", _source_read)
    app.connect("env-get-outdated", _always_reread)
    return {"version": "0.1", "parallel_read_safe": True, "parallel_write_safe": True}
