"""Rich-backed renderers for the human-facing TTY surface of tether.

This module is the *third* output surface, alongside `output.py` (JSON for
agents and the PreToolUse hook) and `render.py` (plain markdown for pipes and
the SessionStart/Stop hooks). It is imported only by `cli.py` and only when
stdout is a terminal, so its ANSI styling can never bleed into an agent's
context window. The data it consumes is exactly what the markdown renderers
consume — `Tether` records and `status.py` check results — so there is no new
plumbing between the state model and the screen.
"""

from __future__ import annotations

from pathlib import Path
from typing import IO

from rich import box
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .model import Artifact, Tether
from .render import Row, art_display, by_severity, counts
from .status import (
    STATE_ORDER,
    AggregateState,
    ArtifactCheck,
    ArtifactState,
    TetherCheck,
    artifact_diff,
)

# State → color. The three states drive every accent in this module; keep the
# mapping here so a palette change lands in one place.
_STATE_STYLE: dict[str, str] = {
    "HEALTHY": "green",
    "DRIFTED": "yellow",
    "BROKEN": "red",
}


def make_console(*, no_color: bool = False, file: IO[str] | None = None) -> Console:
    """Build the console the CLI renders human output through.

    `highlight=False` disables Rich's automatic number/string highlighting so
    only the styles set here apply. `no_color` honors `--no-color` (and Rich
    independently honors `NO_COLOR` / a non-terminal target).
    """
    return Console(no_color=no_color, highlight=False, file=file)


def _state_text(state: AggregateState | ArtifactState) -> Text:
    # No bold: terminals that draw bold as the bright palette (Solarized among
    # them) remap bold-yellow/red to off-palette tones — bold-yellow lands on
    # base00 (a teal), bold-red on orange — which would break the green/yellow/
    # red scheme. Emphasis comes from the color and the all-caps name, so a
    # state badge matches the same hue everywhere: the header counts, the
    # artifact cells, and the refs panel borders.
    return Text(state.value, style=_STATE_STYLE[state.value])


def _is_rescued(check: TetherCheck) -> bool:
    return check.a.normalization_rescued or check.b.normalization_rescued


# --- summary / counts ------------------------------------------------------


def _status_header(c: dict[str, int], total: int) -> list[Text]:
    """Two-line header: the tether count, then the per-state breakdown. Each
    state is colored only when its count is nonzero, so zero counts recede to
    gray and the live states stand out — color stays reserved for live state.
    """
    line1 = Text.assemble(("Tether Count: ", "bold"), (str(total), "bold"))
    line2 = Text()
    for i, k in enumerate(STATE_ORDER):
        if i:
            line2.append(" -- ", style="dim")
        line2.append(f"{k}: {c[k]}", style=_STATE_STYLE[k] if c[k] else "dim")
    return [line1, line2]


def _errors(console: Console, errors: list[tuple[Path, str]], root: Path) -> None:
    if not errors:
        return
    console.print()
    console.print(Text("Unreadable tether files (skipped):", style="bold red"))
    for path, msg in errors:
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = str(path)
        console.print(Text.assemble("  • ", (rel, "red"), (f": {msg}", "dim")))


# --- status (all) ----------------------------------------------------------


def _artifact_cell(artifact: Artifact, art: ArtifactCheck) -> Text:
    """One artifact in the attention table: path tinted by its own state
    (HEALTHY green / DRIFTED yellow / BROKEN red), with a rename candidate
    (BROKEN) or encoding note (rescued) underneath. Color — never dimming —
    carries state, so a HEALTHY peer reads as green rather than the gray a
    zero count uses; dim gray would falsely imply the artifact is absent when
    it is fine.
    """
    cell = Text(art_display(artifact), style=_STATE_STYLE[art.state.value])
    if art.state == ArtifactState.BROKEN:
        for cand in art.rename_candidates:
            cell.append(f"\n→ {cand.path} (R{cand.similarity})", style="dim")
    elif art.normalization_rescued:
        cell.append("\n(encoding-only)", style="dim")
    return cell


def _attention_table(rows: list[Row]) -> Table:
    table = Table(box=box.ROUNDED, header_style="bold", pad_edge=False, expand=False)
    table.add_column("State", no_wrap=True)
    # The id is neutral structural info (no state of its own), so it reads in
    # the module's gray — the same tone `show` uses — while State and the
    # artifact cells carry the green/yellow/red that color reserves for state.
    table.add_column("Tether", style="grey50", no_wrap=True)
    table.add_column("a", overflow="fold")
    table.add_column("b", overflow="fold")
    for t, ck in by_severity(rows):
        table.add_row(
            _state_text(ck.aggregate),
            t.id,
            _artifact_cell(t.a, ck.a),
            _artifact_cell(t.b, ck.b),
        )
    return table


def pretty_status_all(
    console: Console,
    rows: list[Row],
    errors: list[tuple[Path, str]],
    root: Path,
) -> None:
    if not rows and not errors:
        console.print("No tethers.")
        return

    c = counts(rows)
    total = len(rows)
    rescued = [r for r in rows if _is_rescued(r[1])]

    for line in _status_header(c, total):
        console.print(line)

    non_healthy = [r for r in rows if r[1].aggregate != AggregateState.HEALTHY]
    if non_healthy:
        console.print()
        console.print(_attention_table(non_healthy))

    if rescued:
        console.print()
        console.print(
            Text(
                "Encoding-only drift (rescued by normalizer; no action required):",
                style="dim",
            )
        )
        for t, _ in by_severity(rescued):
            console.print(
                Text.assemble(
                    ("  ", ""),
                    (t.id, "grey50"),
                    ("  ", ""),
                    (t.a.path, "dim"),
                    (" — ", "dim"),
                    (t.b.path, "dim"),
                )
            )

    _errors(console, errors, root)


# --- status (one) ----------------------------------------------------------


def _artifact_inline(artifact: Artifact, art: ArtifactCheck) -> Text:
    txt = Text.assemble((art_display(artifact), "cyan"), "  ")
    txt.append_text(_state_text(art.state))
    if art.normalization_rescued:
        txt.append(" (encoding-only drift rescued)", style="dim")
    return txt


def _diff_text(diff: str) -> Text:
    """Color a unified diff line-by-line (predictable; no pygments theming)."""
    out = Text()
    for line in diff.splitlines():
        if line.startswith(("+++", "---", "diff ", "index ")):
            style = "bold"
        elif line.startswith("@@"):
            style = "cyan"
        elif line.startswith("+"):
            style = "green"
        elif line.startswith("-"):
            style = "red"
        else:
            style = ""
        out.append(line + "\n", style=style)
    return out


def _diff_panel(label: str, artifact: Artifact, root: Path, *, rescued: bool) -> Panel:
    diff = artifact_diff(artifact, root).rstrip("\n")
    disp = art_display(artifact)
    if rescued:
        title = f"Encoding-only drift on {label}: {disp}"
        body: list[RenderableType] = [
            Text(
                "Bytes differ but normalize equal (line endings / trailing whitespace / "
                "BOM / leading-tab expansion); state rescued to HEALTHY. "
                "`tether refresh <id>` re-aligns the raw fingerprint.",
                style="dim",
            ),
            Text(),
            _diff_text(diff),
        ]
    else:
        title = f"Drift on {label}: {disp}"
        body = [_diff_text(diff)]
    return Panel(
        Group(*body),
        title=title,
        title_align="left",
        border_style=_STATE_STYLE["DRIFTED"],
        box=box.ROUNDED,
    )


def _broken_panel(label: str, artifact: Artifact, art: ArtifactCheck) -> Panel:
    body: list[RenderableType] = [
        Text(
            f"{art_display(artifact)} — content not present at recorded path/locator",
            style="red",
        )
    ]
    if art.rename_candidates:
        body.append(Text("\nRename candidates (by content similarity):", style="dim"))
        for cand in art.rename_candidates:
            body.append(Text(f"  • {cand.path} (R{cand.similarity})"))
        body.append(
            Text(
                f"\nFollow a rename: tether update --{label}-path <new>, "
                "then tether refresh <id>.",
                style="dim",
            )
        )
    return Panel(
        Group(*body),
        title=f"Broken {label}",
        title_align="left",
        border_style="red",
        box=box.ROUNDED,
    )


def pretty_status_one(
    console: Console,
    t: Tether,
    check: TetherCheck,
    root: Path,
    show_diff: bool,
) -> None:
    console.print(Text.assemble(("Tether ", "bold"), (t.id, "bold cyan")))

    meta = Table(box=None, show_header=False, pad_edge=False)
    meta.add_column(style="bold", justify="right", no_wrap=True)
    meta.add_column(overflow="fold")
    meta.add_row("State", _state_text(check.aggregate))
    meta.add_row("a", _artifact_inline(t.a, check.a))
    meta.add_row("b", _artifact_inline(t.b, check.b))
    meta.add_row("Created", Text(t.created_at, style="dim"))
    meta.add_row("Refreshed", Text(t.refreshed_at, style="dim"))
    meta.add_row("Description", Text(t.description))
    console.print(meta)

    if not show_diff:
        return
    for label, artifact, art in (("a", t.a, check.a), ("b", t.b, check.b)):
        if art.state == ArtifactState.DRIFTED:
            console.print(_diff_panel(label, artifact, root, rescued=False))
        elif art.state == ArtifactState.HEALTHY and art.normalization_rescued:
            console.print(_diff_panel(label, artifact, root, rescued=True))
        elif art.state == ArtifactState.BROKEN:
            console.print(_broken_panel(label, artifact, art))


# --- refs ------------------------------------------------------------------


def _state_key() -> Text:
    """A legend for the three states, each entry in the same full state color
    as the panel border it explains — and as the `tether status` header counts
    — so the legend, the borders below it, and the status counts all read as one
    shade per state. Only the "Key:" label itself is dim.
    """
    key = Text()
    key.append("Key:  ", style="dim")
    for i, state in enumerate(STATE_ORDER):
        if i:
            key.append("   ", style="dim")
        key.append(f"● {state}", style=_STATE_STYLE[state])
    return key


def pretty_refs(
    console: Console,
    queried: str,
    rows: list[Row],
    errors: list[tuple[Path, str]],
    root: Path,
) -> None:
    """Filtered catalog: every tether touching `queried`, in the same panel
    format as `show` so the two views read alike, with the queried path
    underlined in each title. Severity-ordered, most-drifted first. Unlike
    `show`, the panel border is tinted by aggregate state (see the key).
    """
    if not rows and not errors:
        console.print(Text.assemble("No tethers reference ", (queried, "cyan"), "."))
        return
    if rows:
        total = len(rows)
        plural = "s" if total != 1 else ""
        console.print(
            Text.assemble(
                f"{total} tether{plural} referencing ", (queried, "bold cyan")
            )
        )
        console.print(_state_key())
        for t, ck in by_severity(rows):
            console.print()
            console.print(
                _tether_panel(
                    t,
                    queried=queried,
                    border_style=_STATE_STYLE[ck.aggregate.value],
                )
            )
    _errors(console, errors, root)


# --- show ------------------------------------------------------------------


def _tether_panel(
    t: Tether,
    *,
    queried: str | None = None,
    path_style: str = "bold cyan",
    border_style: str = "cyan",
) -> Panel:
    """One catalog entry, shared by `show` and `refs`: the two paths as the
    title (what is tethered), the id as a dim subtitle, and the description —
    the point of both views — as plain readable body text.

    `refs` is drift-aware: it underlines the queried path and tints the border
    by aggregate state (green/yellow/red) so state is scannable. `show` is
    structural-only — it does not compute state — so it renders strictly
    neutral (gray border, no color), making it clear that no state is implied;
    a colored border would falsely read as a health signal.
    """

    def path_part(p: str) -> tuple[str, str]:
        return (p, f"{path_style} underline" if p == queried else path_style)

    title = Text.assemble(path_part(t.a.path), ("  —  ", "dim"), path_part(t.b.path))
    return Panel(
        Text(t.description),
        title=title,
        title_align="left",
        subtitle=Text(t.id, style="dim"),
        subtitle_align="left",
        border_style=border_style,
        box=box.ROUNDED,
        padding=(0, 1),
    )


def pretty_show(
    console: Console,
    tethers: list[Tether],
    errors: list[tuple[Path, str]],
    root: Path,
) -> None:
    if not tethers and not errors:
        console.print("No tethers.")
        return
    for i, t in enumerate(tethers):
        if i:
            console.print()
        # Strictly neutral: no state is computed here, so no state-coloring.
        console.print(_tether_panel(t, path_style="bold", border_style="grey50"))
    _errors(console, errors, root)
