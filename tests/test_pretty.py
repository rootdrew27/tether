from __future__ import annotations

import io
import re
from pathlib import Path

from click.testing import CliRunner
from rich.console import Console

from tether import pretty
from tether.cli import main
from tether.model import Artifact, Tether
from tether.status import (
    AggregateState,
    ArtifactCheck,
    ArtifactState,
    RenameCandidate,
    TetherCheck,
    check_all,
)
from tether.storage import load_all_tethers

Row = tuple[Tether, TetherCheck]

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(s: str) -> str:
    """Strip ANSI SGR codes so text content can be asserted across styled spans."""
    return _ANSI.sub("", s)


def _render(fn, *args, no_color: bool = False, width: int = 100) -> str:
    """Render a pretty function through a forced-terminal console so styling
    is exercised even though the test stdout is not a TTY."""
    buf = io.StringIO()
    console = Console(
        file=buf,
        force_terminal=True,
        color_system="truecolor",
        no_color=no_color,
        width=width,
        highlight=False,
    )
    fn(console, *args)
    return buf.getvalue()


def _mk(
    id_: str,
    a_path: str,
    b_path: str,
    a_state: ArtifactState,
    b_state: ArtifactState,
    aggregate: AggregateState,
    description: str = "why these are coupled",
    candidates: tuple[RenameCandidate, ...] = (),
) -> Row:
    t = Tether(
        id=id_,
        schema_version=1,
        a=Artifact(path=a_path, fingerprint="a" * 40),
        b=Artifact(path=b_path, fingerprint="b" * 40),
        description=description,
        created_at="2026-06-15T00:00:00Z",
        refreshed_at="2026-06-15T00:00:00Z",
    )
    check = TetherCheck(
        a=ArtifactCheck(state=a_state, rename_candidates=candidates),
        b=ArtifactCheck(state=b_state),
        aggregate=aggregate,
    )
    return t, check


_DRIFTED = _mk(
    "019ec7b9-f60c-76b3-bea3-42ca2f3c5640",
    "tether/render.py",
    "tether/status.py",
    ArtifactState.DRIFTED,
    ArtifactState.HEALTHY,
    AggregateState.DRIFTED,
)
_BROKEN = _mk(
    "019ec7ae-7af8-7f01-ba9d-a92d5d562b27",
    "README.md",
    "tether/cli.py",
    ArtifactState.BROKEN,
    ArtifactState.HEALTHY,
    AggregateState.BROKEN,
    candidates=(RenameCandidate(path="README.rst", similarity=96),),
)
_HEALTHY = _mk(
    "019ec7ae-393a-77b3-b2e6-8dae31cacfb0",
    "tests/test_cli.py",
    "tether/cli.py",
    ArtifactState.HEALTHY,
    ArtifactState.HEALTHY,
    AggregateState.HEALTHY,
)


def test_status_header_all_healthy() -> None:
    out = _render(pretty.pretty_status_all, [_HEALTHY], [], Path("."))
    plain = _plain(out)
    assert "Tether Count: 1" in plain
    assert "HEALTHY: 1 -- DRIFTED: 0 -- BROKEN: 0" in plain
    assert "\x1b[32m" in out  # the nonzero HEALTHY count is green
    # nothing needs attention → no table
    assert "─" not in plain


def test_status_header_breakdown_and_count() -> None:
    out = _render(
        pretty.pretty_status_all, [_DRIFTED, _BROKEN, _HEALTHY], [], Path(".")
    )
    plain = _plain(out)
    assert "Tether Count: 3" in plain
    assert "HEALTHY: 1 -- DRIFTED: 1 -- BROKEN: 1" in plain
    # each present state keeps its color
    assert "\x1b[32m" in out and "\x1b[33m" in out and "\x1b[31m" in out


def test_status_header_zero_counts_are_gray_not_state_color() -> None:
    # only DRIFTED present → DRIFTED is yellow, but HEALTHY/BROKEN counts are 0
    # and must render dim (gray), not green/red
    out = _render(pretty.pretty_status_all, [_DRIFTED], [], Path("."))
    assert "HEALTHY: 0 -- DRIFTED: 1 -- BROKEN: 0" in _plain(out)
    assert "\x1b[33m" in out  # DRIFTED count yellow
    # zero segments are dim, not state-colored
    assert "\x1b[2mHEALTHY: 0\x1b[0m" in out
    assert "\x1b[2mBROKEN: 0\x1b[0m" in out


def test_status_all_table_shows_states_and_ids() -> None:
    out = _render(
        pretty.pretty_status_all, [_DRIFTED, _BROKEN, _HEALTHY], [], Path(".")
    )
    assert "DRIFTED" in out and "BROKEN" in out
    # ids are present so the user can act on them
    assert _BROKEN[0].id in out
    # severity-ordered table: the BROKEN row precedes the DRIFTED row
    assert out.index(_BROKEN[0].id) < out.index(_DRIFTED[0].id)
    # rename candidate for the BROKEN side surfaces
    assert "README.rst" in out and "R96" in out
    # color was emitted
    assert "\x1b[" in out


def test_status_table_uses_state_colors_and_gray_ids() -> None:
    # the attention table follows the module's color scheme: State and the
    # artifact cells carry green/yellow/red by state, while the id is neutral
    # gray (grey50) — color stays reserved for live state, never the id.
    out = _render(pretty.pretty_status_all, [_DRIFTED, _BROKEN], [], Path("."))
    # State text: plain (non-bold) aggregate-state color
    assert "\x1b[33mDRIFTED" in out  # yellow
    assert "\x1b[31mBROKEN" in out  # red
    # never bold: terminals that draw bold as bright (e.g. Solarized) remap
    # bold-yellow to teal and bold-red to orange, breaking the state scheme
    assert "\x1b[1;33m" not in out
    assert "\x1b[1;31m" not in out
    # artifact cells: per-side state color — the drifted `a` is yellow, the
    # broken `a` is red, and a HEALTHY peer is green (not the gray a zero
    # count uses; gray would imply the artifact is absent when it is fine)
    assert "\x1b[33mtether/render.py" in out  # drifted a
    assert "\x1b[31mREADME.md" in out  # broken a
    assert "\x1b[32mtether/status.py" in out  # healthy peer of the drifted tether
    assert "\x1b[32mtether/cli.py" in out  # healthy peer of the broken tether
    # the id is gray, not the old cyan — no cyan anywhere in the table
    assert "\x1b[38;5;244m" in out  # grey50
    assert "36m" not in out


def test_status_all_no_color_drops_color_codes() -> None:
    out = _render(
        pretty.pretty_status_all, [_DRIFTED, _BROKEN], [], Path("."), no_color=True
    )
    # structure/content survives, but the state-color SGR codes do not
    assert "DRIFTED" in out and "BROKEN" in out
    for color in ("[32m", "[31m", "[33m"):  # green / red / yellow
        assert color not in out


def test_refs_marks_queried_path_and_lists_peers() -> None:
    out = _render(
        pretty.pretty_refs, "tether/cli.py", [_BROKEN, _HEALTHY], [], Path(".")
    )
    assert "2 tethers referencing" in out
    assert "tether/cli.py" in out
    assert "README.md" in out and "tests/test_cli.py" in out
    # descriptions are shown in the refs view
    assert "why these are coupled" in out


def test_refs_empty() -> None:
    out = _render(pretty.pretty_refs, "src/auth.py", [], [], Path("."))
    assert "No tethers reference" in out
    assert "src/auth.py" in out


def test_refs_includes_state_key() -> None:
    # the key says "Key:" and lists all three states even when only one is
    # present (the HEALTHY panel itself prints no state words)
    out = _render(pretty.pretty_refs, "x", [_HEALTHY], [], Path("."))
    plain = _plain(out)
    assert "Key:" in plain
    assert "HEALTHY" in plain and "DRIFTED" in plain and "BROKEN" in plain
    # each entry is the full state color — matching the panel borders it
    # explains and the `tether status` header counts (one shade per state)
    assert "\x1b[32m● HEALTHY" in out
    assert "\x1b[33m● DRIFTED" in out
    assert "\x1b[31m● BROKEN" in out


def test_refs_tints_border_by_aggregate_state() -> None:
    # full green/yellow/red appear from the key legend and the panel borders,
    # which are tinted by aggregate state
    out = _render(pretty.pretty_refs, "x", [_BROKEN, _DRIFTED, _HEALTHY], [], Path("."))
    assert "\x1b[31m" in out  # BROKEN red
    assert "\x1b[33m" in out  # DRIFTED yellow
    assert "\x1b[32m" in out  # HEALTHY green


def test_show_lists_every_tether_with_description() -> None:
    tethers = [_DRIFTED[0], _BROKEN[0], _HEALTHY[0]]
    out = _render(pretty.pretty_show, tethers, [], Path("."))
    for t in tethers:
        assert t.id in out
        assert t.a.path in out and t.b.path in out
    assert "why these are coupled" in out


def test_show_is_neutral_no_state_color() -> None:
    # show does not compute state, so it must not emit state-implying color:
    # no green/red/yellow (state) and no cyan (a colored accent).
    out = _render(
        pretty.pretty_show, [_DRIFTED[0], _BROKEN[0], _HEALTHY[0]], [], Path(".")
    )
    for code in ("\x1b[31m", "\x1b[32m", "\x1b[33m"):  # red / green / yellow
        assert code not in out
    assert "36m" not in out  # no cyan (catches `[36m` and `[1;36m`)


def test_status_one_renders_diff(in_project: Path) -> None:
    (in_project / "a.txt").write_text("alpha\n")
    (in_project / "b.txt").write_text("beta\n")
    runner = CliRunner()
    runner.invoke(main, ["add", "a.txt", "b.txt", "--description", "coupled"])
    # drift the a side
    (in_project / "a.txt").write_text("alpha changed\n")

    result = load_all_tethers(in_project)
    t = result.tethers[0]
    check = check_all([t], in_project)[0]
    out = _render(pretty.pretty_status_one, t, check, in_project, True)

    assert "Drift on a" in out
    assert "alpha changed" in out  # the new content shows in the diff
    assert "DRIFTED" in out


def test_status_one_broken_shows_rename_candidate(in_project: Path) -> None:
    (in_project / "a.txt").write_text("alpha\n")
    (in_project / "b.txt").write_text("beta\n")
    runner = CliRunner()
    runner.invoke(main, ["add", "a.txt", "b.txt", "--description", "coupled"])
    (in_project / "a.txt").rename(in_project / "renamed.txt")

    result = load_all_tethers(in_project)
    t = result.tethers[0]
    check = check_all([t], in_project)[0]
    out = _render(pretty.pretty_status_one, t, check, in_project, True)

    assert "Broken a" in out
    assert "renamed.txt" in out
