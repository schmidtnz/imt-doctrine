"""Sphinx extension: index items and glossary terms where they're used; list those pages in the HTML glossary."""
from __future__ import annotations

import re

from docutils import nodes
from sphinx import addnodes
from sphinx.transforms import SphinxTransform
from sphinx.util import logging

logger = logging.getLogger(__name__)


def _name(value: str) -> str:
    """Top-level name of an index entry ("POD; CON-08 Maths in SAR" gives "POD")."""
    return value.split(";")[0].strip()


def _in_title(node) -> bool:
    while node is not None:
        if isinstance(node, nodes.title):
            return True
        node = node.parent
    return False


class IndexEntries(SphinxTransform):
    """Index each item by ID, title and its `index` terms, and each glossary term at its first use on a page."""

    # Before SphinxDomains (850) collects index entries.
    default_priority = 800

    def apply(self) -> None:
        for toctree in self.document.findall(addnodes.toctree):
            # Keep the index as a menu entry only; the LaTeX build would try to include it as a page.
            toctree["includefiles"] = [f for f in toctree["includefiles"] if f != "genindex"]
        title = self.document.next_node(nodes.title)
        if title is None:
            return
        page = title.astext().replace(";", ",")
        state = getattr(self.app, "doctrace", None)
        iid = state["by_doc"].get(self.env.docname) if state else None
        if iid:
            item = state["items"][iid]
            bare = re.sub(r"^The (\w)", lambda m: m.group(1).upper(), item.title)
            entries = [f"{item.id} {item.title}", f"{bare}; {item.id}", *(f"{t}; {page}" for t in item.index)]
            title.parent.insert(title.parent.index(title) + 1, self._nodes(entries, inline=False))
        if next(self.document.findall(addnodes.glossary), None) is not None:
            return
        seen = set()
        for ref in list(self.document.findall(addnodes.pending_xref)):
            if (ref.get("refdomain"), ref.get("reftype")) != ("std", "term") or _in_title(ref):
                continue
            term = ref["reftarget"]
            if term.lower() not in seen:
                seen.add(term.lower())
                ref.parent.insert(ref.parent.index(ref), self._nodes([f"{term}; {page}"]))

    def _nodes(self, entries: list[str], inline: bool = True) -> list[nodes.Node]:
        tid = f"index-{self.env.new_serialno('index')}"
        target = nodes.target("", "", ids=[tid])
        self.document.note_explicit_target(target)
        index = addnodes.index(entries=[("single", e, tid, "", None) for e in entries], inline=inline)
        return [index, target]


def _glossary_docs(env) -> set[str]:
    return {doc for (typ, _), (doc, _) in env.get_domain("std").objects.items() if typ == "term"}


def _reread_glossary(app, env, added, changed, removed):
    # Its "Used in" lists depend on every other page.
    return list(_glossary_docs(env))


def _check_case(app, env) -> None:
    terms = {name.lower(): name for typ, name in env.get_domain("std").objects if typ == "term"}
    for docname, entries in env.get_domain("index").entries.items():
        for _type, value, *_ in entries:
            name = _name(value)
            if terms.get(name.lower(), name) != name:
                logger.warning("index entry %r should match the glossary: %r", name, terms[name.lower()],
                               location=docname)


def _reading_order(env) -> list[str]:
    order: dict[str, None] = {}

    def walk(doc):
        if doc not in order:
            order[doc] = None
            for child in env.toctree_includes.get(doc, ()):
                walk(child)

    walk(env.config.root_doc)
    return [*order, *sorted(set(env.all_docs) - set(order))]


def _used_in(app, doctree, docname) -> None:
    """Under each glossary definition, link the pages indexed under that term (HTML only)."""
    glossaries = list(doctree.findall(addnodes.glossary))
    if app.builder.format != "html" or not glossaries:
        return
    env = app.env
    pages: dict[str, dict[str, str]] = {}
    for doc in _reading_order(env):
        if doc != docname:
            for _type, value, tid, *_ in env.get_domain("index").entries.get(doc, ()):
                pages.setdefault(_name(value).lower(), {}).setdefault(doc, tid)
    for glossary in glossaries:
        for item in glossary.findall(nodes.definition_list_item):
            uses: dict[str, str] = {}
            for term in item.findall(nodes.term):
                for doc, tid in pages.get(term.astext().lower(), {}).items():
                    uses.setdefault(doc, tid)
            if not uses:
                continue
            para = nodes.paragraph("", "Used in: ", classes=["term-uses"])
            for n, (doc, tid) in enumerate(uses.items()):
                if n:
                    para += nodes.Text(", ")
                uri = f"{app.builder.get_relative_uri(docname, doc)}#{tid}"
                para += nodes.reference("", env.titles[doc].astext(), internal=True, refuri=uri)
            item.next_node(nodes.definition).append(para)


def setup(app):
    app.add_transform(IndexEntries)
    app.connect("env-get-outdated", _reread_glossary)
    app.connect("env-check-consistency", _check_case)
    app.connect("doctree-resolved", _used_in)
    return {"version": "0.1", "parallel_read_safe": True, "parallel_write_safe": True}
