from __future__ import annotations

import shutil
import textwrap
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape
from xml.sax.saxutils import quoteattr as _xml_quoteattr

from .model import Artifact, Tether
from .status import SEVERITY, ArtifactCheck, ArtifactState, TetherCheck

Row = tuple[Tether, TetherCheck]

STATE_ORDER: tuple[str, ...] = ("HEALTHY", "WEAKENED", "DRIFTED", "BROKEN")


def tether_line(t: Tether, check: TetherCheck) -> str:
    return (
        f"- `{t.id}`: {check.aggregate.value} — "
        f"`{t.a.path}` ({check.a.state.value}) — "
        f"`{t.b.path}` ({check.b.state.value})"
    )


def by_severity(rows: list[Row]) -> list[Row]:
    return sorted(rows, key=lambda r: (SEVERITY[r[1].aggregate], r[0].id))


def counts(rows: list[Row]) -> dict[str, int]:
    c = {k: 0 for k in STATE_ORDER}
    for _, check in rows:
        c[check.aggregate.value] += 1
    return c


def summary_line(rows: list[Row]) -> str:
    c = counts(rows)
    total = len(rows)
    summary = ", ".join(f"{c[k]} {k}" for k in STATE_ORDER if c[k])
    plural = "s" if total != 1 else ""
    return f"{total} tether{plural} tracked. Counts: {summary}."


def item_lines(rows: list[Row], *, with_description: bool = True) -> list[str]:
    lines: list[str] = []
    for t, check in by_severity(rows):
        lines.append(tether_line(t, check))
        if with_description:
            lines.append(f"  Description: {t.description}")
        for label, art in (("a", check.a), ("b", check.b)):
            if art.state == ArtifactState.BROKEN and art.rename_candidates:
                joined = ", ".join(f"`{p}`" for p in art.rename_candidates)
                lines.append(f"  {label} rename candidates (by fingerprint): {joined}")
    return lines


def errors_section(errors: list[tuple[Path, str]], root: Path) -> list[str]:
    if not errors:
        return []
    lines = ["", "Unreadable tether files (skipped):"]
    for path, msg in errors:
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = str(path)
        lines.append(f"- `{rel}`: {msg}")
    return lines


def _wrap_description(description: str, width: int) -> list[str]:
    """Wrap a description to ``width`` with a 2-space hanging indent.

    The author's own line breaks are preserved (each segment is wrapped
    independently) so paragraph structure survives.
    """
    lines: list[str] = []
    for segment in description.splitlines():
        if not segment.strip():
            lines.append("")
            continue
        lines.extend(
            textwrap.wrap(
                segment,
                width=width,
                initial_indent="  ",
                subsequent_indent="  ",
            )
        )
    return lines


def _show_block(t: Tether, width: int) -> str:
    lines = [t.id]
    lines.extend(
        textwrap.wrap(
            f"{t.a.path} — {t.b.path}",
            width=width,
            initial_indent="  ",
            subsequent_indent="  ",
            break_on_hyphens=False,
            break_long_words=False,
        )
    )
    lines.extend(_wrap_description(t.description, width))
    return "\n".join(lines)


def show_text(
    tethers: list[Tether],
    errors: list[tuple[Path, str]],
    root: Path,
    *,
    width: int | None = None,
) -> str:
    """Render every tether as a structural-only catalog block.

    No drift state and no git access — this lists what is on disk so the
    relationships and their descriptions can be read at a glance. State and
    diffs are `tether status`'s job.
    """
    if not tethers and not errors:
        return "No tethers."
    if width is None:
        width = shutil.get_terminal_size().columns
    width = max(width, 20)

    parts: list[str] = []
    if tethers:
        parts.append("\n\n".join(_show_block(t, width) for t in tethers))
    error_lines = errors_section(errors, root)
    if error_lines:
        parts.append("\n".join(error_lines).lstrip("\n"))
    return "\n\n".join(parts)


def _classify_sides(
    t: Tether, check: TetherCheck, rel_path: str
) -> tuple[tuple[Artifact, ArtifactCheck], tuple[Artifact, ArtifactCheck]]:
    if t.a.path == rel_path:
        return (t.a, check.a), (t.b, check.b)
    return (t.b, check.b), (t.a, check.a)


def refs_xml(
    rel_path: str,
    rows: list[Row],
    errors: list[tuple[Path, str]],
    project_root: Path,
) -> str:
    """Render a `<tether-context>` block for one queried path.

    The wrapper element is always emitted, even when no tethers match — the
    empty wrapper is parser-friendly. Callers that want to suppress the
    `<errors>` child pass an empty `errors` list.
    """
    lines = ["<tether-context>"]
    for t, check in by_severity(rows):
        (self_art, self_check), (peer, peer_check) = _classify_sides(t, check, rel_path)
        lines.append(
            f"  <tether id={_xml_quoteattr(t.id)} "
            f"aggregate={_xml_quoteattr(check.aggregate.value)}>"
        )
        lines.append(
            f"    <self path={_xml_quoteattr(self_art.path)} "
            f"state={_xml_quoteattr(self_check.state.value)} />"
        )
        lines.append(
            f"    <peer path={_xml_quoteattr(peer.path)} "
            f"state={_xml_quoteattr(peer_check.state.value)} />"
        )
        lines.append(f"    <description>{_xml_escape(t.description)}</description>")
        lines.append("  </tether>")
    if errors:
        lines.append("  <errors>")
        for path, msg in errors:
            try:
                rel = path.relative_to(project_root).as_posix()
            except ValueError:
                rel = str(path)
            lines.append(
                f"    <error path={_xml_quoteattr(rel)}>{_xml_escape(msg)}</error>"
            )
        lines.append("  </errors>")
    lines.append("</tether-context>")
    return "\n".join(lines) + "\n"
