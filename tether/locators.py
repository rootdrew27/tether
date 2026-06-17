"""Language-aware section locators: resolve a selector to a region of a file.

A locator names a *region* of an artifact — a Python function or class, or a
markdown section — rather than the whole file. Resolution is parser-based
(tree-sitter), so a selector addresses a region by what it is and survives edits
elsewhere in the file. This module is the only one that imports tree-sitter: it
owns the language registry, a parser cache, and the selector → node → bytes
resolution. Adding a language is local to here plus the extension map in
`cli.py`.

The byte span returned is exactly `node.start_byte .. node.end_byte`. For a
Python symbol that is the `def`/`class` keyword (decorators included when
present) through the last body byte; for a markdown section it is the heading
line through the byte before the next heading of equal-or-higher level, nested
subsections included. There is no dedent or re-rendering: re-indentation and
reflowing are real drift, per the design.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

import tree_sitter_markdown as tsmarkdown
import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from .errors import (
    AmbiguousLocatorError,
    LocatorUnresolvedError,
    UnsupportedLocatorError,
)
from .model import Locator

# Python definition node kinds: each carries a `name` field and a `body` block
# we descend into for a nested selector segment.
_PY_DEF_KINDS = frozenset({"function_definition", "class_definition"})

# Markdown heading node kinds. We locate these directly and derive section
# nesting from their levels (see `_resolve_heading`) rather than from the
# grammar's `section` nodes, which do not reliably wrap setext headings.
_MD_HEADING_KINDS = frozenset({"atx_heading", "setext_heading"})


@lru_cache(maxsize=None)
def _language(lang: str) -> Language:
    if lang == "python":
        return Language(tspython.language())
    if lang == "markdown":
        # tree-sitter-markdown is a split grammar; the block grammar alone yields
        # the heading nodes and the raw heading text we match against.
        return Language(tsmarkdown.language())
    raise UnsupportedLocatorError(f"no parser registered for locator lang {lang!r}")


@lru_cache(maxsize=None)
def _parser(lang: str) -> Parser:
    return Parser(_language(lang))


def extract_region(source: bytes, locator: Locator) -> bytes:
    """Return the exact bytes of the region `locator` names within `source`.

    Raises:
        UnsupportedLocatorError: the kind/lang pairing is not parseable here.
        LocatorUnresolvedError: no node matches the selector.
        AmbiguousLocatorError: more than one node matches a path segment.
    """
    kind, lang = locator.kind, locator.lang
    if kind == "symbol" and lang == "python":
        sep = "."
    elif kind == "heading" and lang == "markdown":
        sep = "/"
    else:
        raise UnsupportedLocatorError(
            f"unsupported locator kind/lang {kind!r}/{lang!r}"
        )

    tree = _parser(lang).parse(source)
    parts = [p for p in locator.selector.split(sep) if p.strip()]
    if not parts:
        raise LocatorUnresolvedError(f"empty selector {locator.selector!r}")
    if kind == "symbol":
        node = _resolve_symbol(tree.root_node, parts, locator.selector)
        start, end = node.start_byte, node.end_byte
    else:
        start, end = _resolve_heading(tree.root_node, parts, locator.selector)
    return source[start:end]


def _resolve_symbol(scope: Node, parts: list[str], selector: str) -> Node:
    name, rest = parts[0], parts[1:]
    matches = [d for d in _child_defs(scope) if _def_name(d) == name]
    if len(matches) > 1:
        raise AmbiguousLocatorError(
            f"selector {selector!r}: {len(matches)} definitions named {name!r} "
            "in the same scope"
        )
    if not matches:
        raise LocatorUnresolvedError(
            f"selector {selector!r}: no definition named {name!r}"
        )
    inner = matches[0]
    if not rest:
        return _outer(inner)
    body = inner.child_by_field_name("body")
    if body is None:
        raise LocatorUnresolvedError(
            f"selector {selector!r}: {name!r} has no body to descend into"
        )
    return _resolve_symbol(body, rest, selector)


def _child_defs(scope: Node) -> Iterator[Node]:
    """Yield the function/class definitions directly inside `scope`.

    `scope` is a `module` or a `block` body. A `decorated_definition` is
    unwrapped to its inner function/class so name matching ignores the
    decorators; `_outer` re-wraps it when computing the region span.
    """
    for child in scope.named_children:
        if child.type in _PY_DEF_KINDS:
            yield child
        elif child.type == "decorated_definition":
            inner = child.child_by_field_name("definition")
            if inner is not None and inner.type in _PY_DEF_KINDS:
                yield inner


def _def_name(node: Node) -> str | None:
    name = node.child_by_field_name("name")
    if name is None or name.text is None:
        return None
    return name.text.decode()


def _outer(node: Node) -> Node:
    """The region node for `node`: its `decorated_definition` wrapper if any.

    Decorators are part of the symbol's source, so a tethered function includes
    its `@decorator` lines in the fingerprinted region.
    """
    parent = node.parent
    if parent is not None and parent.type == "decorated_definition":
        return parent
    return node


def _resolve_heading(root: Node, parts: list[str], selector: str) -> tuple[int, int]:
    """Resolve a slash-separated heading path to a (start_byte, end_byte) span.

    Nesting is derived from heading *levels*, not from the grammar's `section`
    nodes: tree-sitter-markdown does not reliably wrap setext headings into
    nested sections, so building the hierarchy from levels handles atx and setext
    uniformly. The match is anchored — each segment names a heading whose parent
    (the nearest preceding heading of strictly lower level) is the previous
    match, the first segment a top-level heading. A sole document-title heading
    is therefore part of the path. The span runs from the matched heading through
    the byte before the next heading of equal-or-higher level (nested subsections
    included), or to end-of-document.
    """
    headings = list(_iter_headings(root))
    levels = [_heading_level(h) for h in headings]
    titles = [_heading_text(h) for h in headings]
    starts = [h.start_byte for h in headings]
    doc_end = root.end_byte
    n = len(headings)

    # Each heading's section ends where the next heading of equal-or-higher level
    # begins (lower or equal level number), else at end-of-document.
    ends = [doc_end] * n
    for i in range(n):
        for j in range(i + 1, n):
            if levels[j] <= levels[i]:
                ends[i] = starts[j]
                break

    # Parent of each heading: the nearest preceding heading of strictly lower
    # level (-1 = the document root). This is the anchoring relation.
    parent = [-1] * n
    for i in range(n):
        for j in range(i - 1, -1, -1):
            if levels[j] < levels[i]:
                parent[i] = j
                break

    scope = -1
    for name in parts:
        matches = [i for i in range(n) if parent[i] == scope and titles[i] == name]
        if len(matches) > 1:
            raise AmbiguousLocatorError(
                f"selector {selector!r}: {len(matches)} sections titled {name!r} "
                "in the same scope"
            )
        if not matches:
            raise LocatorUnresolvedError(
                f"selector {selector!r}: no section titled {name!r}"
            )
        scope = matches[0]
    return starts[scope], ends[scope]


def _iter_headings(node: Node) -> Iterator[Node]:
    """Yield atx/setext heading nodes in document order.

    Headings are treated as leaves (no heading nests inside another); everything
    else is descended into so headings buried in `section` nodes are still found.
    """
    for child in node.named_children:
        if child.type in _MD_HEADING_KINDS:
            yield child
        else:
            yield from _iter_headings(child)


def _heading_level(heading: Node) -> int:
    """The 1–6 level of an atx or setext heading, from its marker/underline."""
    for child in heading.named_children:
        t = child.type
        if t.startswith("atx_h") and t.endswith("_marker"):
            return int(t[len("atx_h")])
        if t.startswith("setext_h") and t.endswith("_underline"):
            return int(t[len("setext_h")])
    raise LocatorUnresolvedError("markdown heading has no recognizable level marker")


def _heading_text(heading: Node) -> str | None:
    """The stripped text of an atx or setext heading.

    An `atx_heading` carries a direct `inline` child; a `setext_heading` nests it
    under a `paragraph`. The first `inline` descendant is the heading text in
    both shapes.
    """
    inline = _first_descendant(heading, "inline")
    if inline is None or inline.text is None:
        return None
    return inline.text.decode().strip()


def _first_descendant(node: Node, kind: str) -> Node | None:
    for child in node.named_children:
        if child.type == kind:
            return child
        found = _first_descendant(child, kind)
        if found is not None:
            return found
    return None
