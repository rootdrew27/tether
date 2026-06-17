import pytest

from tether.errors import (
    AmbiguousLocatorError,
    LocatorUnresolvedError,
    UnsupportedLocatorError,
)
from tether.locators import extract_region
from tether.model import Locator

SRC = b'''import os


def alpha(x):
    """alpha docstring."""
    return x + 1


@decorator
def gamma():
    return inner()


class C:
    CONST = 1

    def method(self, y):
        def nested():
            return y
        return nested()
'''


def _loc(selector: str, lang: str = "python", kind: str = "symbol") -> Locator:
    return Locator(kind=kind, lang=lang, selector=selector)


def test_extract_module_function():
    out = extract_region(SRC, _loc("alpha")).decode()
    assert out.startswith("def alpha(x):")
    assert "return x + 1" in out
    assert "class C" not in out


def test_extract_includes_decorators():
    out = extract_region(SRC, _loc("gamma")).decode()
    assert out.startswith("@decorator")
    assert "def gamma():" in out


def test_extract_class():
    out = extract_region(SRC, _loc("C")).decode()
    assert out.startswith("class C:")
    assert "def method" in out


def test_extract_method_by_dotted_path():
    out = extract_region(SRC, _loc("C.method")).decode()
    assert out.startswith("def method(self, y):")
    assert "class C" not in out


def test_extract_nested_function():
    out = extract_region(SRC, _loc("C.method.nested")).decode()
    assert out.startswith("def nested():")
    assert "return y" in out


def test_unresolved_symbol_raises():
    with pytest.raises(LocatorUnresolvedError, match="no definition named 'missing'"):
        extract_region(SRC, _loc("missing"))


def test_unresolved_nested_segment_raises():
    with pytest.raises(LocatorUnresolvedError, match="no definition named 'ghost'"):
        extract_region(SRC, _loc("C.ghost"))


def test_ambiguous_symbol_raises():
    dup = b"def f():\n    return 1\n\n\ndef f():\n    return 2\n"
    with pytest.raises(AmbiguousLocatorError, match="2 definitions named 'f'"):
        extract_region(dup, _loc("f"))


def test_unsupported_lang_raises():
    # symbol resolution is real, but not registered for rust — a bad pairing.
    with pytest.raises(UnsupportedLocatorError, match="rust"):
        extract_region(SRC, _loc("alpha", lang="rust"))


def test_unsupported_kind_lang_combo_raises():
    # `heading` is valid for markdown and `symbol` for python, but the crossed
    # pairings are not supported and must fail loudly rather than mis-resolve.
    with pytest.raises(UnsupportedLocatorError, match="kind/lang"):
        extract_region(SRC, _loc("alpha", kind="heading"))  # lang defaults python
    with pytest.raises(UnsupportedLocatorError, match="kind/lang"):
        extract_region(SRC, _loc("alpha", kind="symbol", lang="markdown"))


def test_descend_into_constant_raises():
    # CONST is an assignment, not a definition we can descend into.
    with pytest.raises(LocatorUnresolvedError):
        extract_region(SRC, _loc("C.CONST"))


# --- markdown heading locators ---------------------------------------------

MD = b"""# tether

Intro line.

## Installation

Install steps here.

### Requirements

- python 3.11

## Usage

Run it.
"""


def _mdloc(selector: str) -> Locator:
    return Locator(kind="heading", lang="markdown", selector=selector)


def test_md_top_level_heading_is_whole_doc():
    # A sole top-level H1 wraps the entire document.
    assert extract_region(MD, _mdloc("tether")) == MD


def test_md_nested_section_includes_subsections():
    out = extract_region(MD, _mdloc("tether/Installation")).decode()
    assert out.startswith("## Installation")
    assert "### Requirements" in out  # nested subsection is part of the section
    assert "## Usage" not in out  # stops before the next equal-level heading


def test_md_deep_heading_path():
    out = extract_region(MD, _mdloc("tether/Installation/Requirements")).decode()
    assert out.startswith("### Requirements")
    assert "python 3.11" in out
    assert "## Usage" not in out


def test_md_heading_path_is_anchored():
    # 'Installation' is nested under 'tether', not a top-level section.
    with pytest.raises(
        LocatorUnresolvedError, match="no section titled 'Installation'"
    ):
        extract_region(MD, _mdloc("Installation"))


def test_md_top_level_h2_sections():
    src = b"## Alpha\n\na\n\n## Beta\n\nb\n"
    assert extract_region(src, _mdloc("Alpha")) == b"## Alpha\n\na\n\n"
    assert extract_region(src, _mdloc("Beta")) == b"## Beta\n\nb\n"


def test_md_setext_headings():
    src = b"Title\n=====\n\nbody\n\nSub\n---\n\nsubbody\n"
    assert extract_region(src, _mdloc("Title")) == src
    assert extract_region(src, _mdloc("Title/Sub")) == b"Sub\n---\n\nsubbody\n"


def test_md_mixed_atx_and_setext_nesting():
    # A setext H2 nests under an atx H1 even though tree-sitter does not wrap it
    # in a `section` node; nesting is derived from heading levels.
    src = b"# Top\n\nintro\n\nMid\n---\n\nmiddle\n"
    assert extract_region(src, _mdloc("Top/Mid")) == b"Mid\n---\n\nmiddle\n"


def test_md_unresolved_heading_raises():
    with pytest.raises(LocatorUnresolvedError, match="no section titled 'Ghost'"):
        extract_region(MD, _mdloc("tether/Ghost"))


def test_md_ambiguous_sibling_headings_raise():
    dup = b"# A\n\n## Dup\n\none\n\n## Dup\n\ntwo\n"
    with pytest.raises(AmbiguousLocatorError, match="2 sections titled 'Dup'"):
        extract_region(dup, _mdloc("A/Dup"))
