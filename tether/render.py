from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

from .coverage import Coverage
from .model import Artifact, Tether
from .status import (
    STATE_ORDER,
    SEVERITY,
    AggregateState,
    ArtifactState,
    RenameCandidate,
    TetherCheck,
    artifact_diff,
)

Row = tuple[Tether, TetherCheck]


def art_display(a: Artifact) -> str:
    """How an artifact is shown to a human: `path`, or `path::selector` for a
    region. Whole-file artifacts read exactly as before."""
    return f"{a.path}::{a.locator.selector}" if a.locator is not None else a.path


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
                joined = ", ".join(
                    f"`{c.path}` (R{c.similarity})" for c in art.rename_candidates
                )
                lines.append(f"  {label} best match: {joined}")
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


def _file_list_section(title: str, files: list[str]) -> list[str]:
    lines = ["", f"### {title}", ""]
    if files:
        lines.extend(f"- `{p}`" for p in files)
    else:
        lines.append("(none)")
    return lines


def coverage_md(
    cov: Coverage,
    root: Path,
    *,
    list_tethered: bool,
    list_untethered: bool,
) -> str:
    """Render `tether coverage` as a markdown summary with optional file lists."""
    lines = ["## Tether coverage", ""]
    if cov.tracked == 0:
        lines.append("No tracked files outside `.tether/`.")
    else:
        pct = f"{100 * len(cov.tethered) / cov.tracked:.0f}%"
        plural = "s" if cov.tracked != 1 else ""
        lines.append(
            f"{len(cov.tethered)} of {cov.tracked} tracked file{plural} "
            f"tethered ({pct}). {len(cov.untethered)} untethered."
        )
    if list_untethered:
        lines.extend(_file_list_section("Untethered files", cov.untethered))
    if list_tethered:
        lines.extend(_file_list_section("Tethered files", cov.tethered))
    if not (list_tethered or list_untethered) and cov.tracked:
        lines.extend(
            [
                "",
                "For file lists: `tether coverage --list-untethered-files` / "
                "`--list-tethered-files`",
            ]
        )
    lines.extend(errors_section(cov.errors, root))
    return "\n".join(lines)


def refs_md(
    rel_path: str,
    rows: list[Row],
    errors: list[tuple[Path, str]],
    root: Path,
) -> str:
    """Render `tether refs <path>` as a human-readable markdown block.

    Severity-ordered list of tethers referencing `rel_path`, with descriptions.
    """
    if not rows and not errors:
        return f"No tethers reference `{rel_path}`."

    lines: list[str] = []
    if rows:
        total = len(rows)
        plural = "s" if total != 1 else ""
        lines.append(f"{total} tether{plural} referencing `{rel_path}`.")
        lines.append("")
        lines.extend(item_lines(rows, with_description=True))
    lines.extend(errors_section(errors, root))
    return "\n".join(lines)


def _is_rescued(check: TetherCheck) -> bool:
    return check.a.normalization_rescued or check.b.normalization_rescued


def all_tethers_md(
    rows: list[Row],
    errors: list[tuple[Path, str]],
    root: Path,
) -> str:
    total = len(rows)
    if total == 0 and not errors:
        return "No tethers."

    c = counts(rows)
    if (
        c["HEALTHY"] == total
        and not errors
        and not any(_is_rescued(ck) for _, ck in rows)
    ):
        plural = "s" if total != 1 else ""
        return f"{total} tether{plural}, all HEALTHY."

    lines: list[str] = [summary_line(rows)]
    non_healthy = [r for r in rows if r[1].aggregate != AggregateState.HEALTHY]
    if non_healthy:
        lines.extend(["", "Needs attention:"])
        lines.extend(item_lines(non_healthy))

    rescued = [
        r
        for r in rows
        if r[1].aggregate == AggregateState.HEALTHY and _is_rescued(r[1])
    ]
    if rescued:
        lines.extend(
            ["", "Encoding-only drift (rescued by normalizer; no action required):"]
        )
        lines.extend(item_lines(rescued, with_description=False))

    lines.extend(errors_section(errors, root))
    return "\n".join(lines)


def _drift_block(
    label: str, artifact: Artifact, root: Path, *, rescued: bool
) -> list[str]:
    disp = art_display(artifact)
    header = (
        f"## Encoding-only drift on {label}: `{disp}`"
        if rescued
        else f"## Drift on {label}: `{disp}`"
    )
    body = [
        "",
        header,
    ]
    if rescued:
        body.append(
            "Bytes differ but normalize to the same value (line endings / trailing whitespace / "
            "BOM / leading-tab expansion). State is rescued to HEALTHY; `tether refresh <uuid>` "
            "would re-align the raw fingerprint."
        )
    body.extend(
        [
            "",
            "```diff",
            artifact_diff(artifact, root).rstrip("\n"),
            "```",
        ]
    )
    return body


def _broken_block(
    label: str, artifact: Artifact, candidates: tuple[RenameCandidate, ...]
) -> list[str]:
    lines = [
        "",
        f"## Broken {label}: `{art_display(artifact)}` "
        "(content not present at recorded path/locator)",
    ]
    if candidates:
        lines.append("")
        lines.append("Rename candidates (by content similarity):")
        for c in candidates:
            lines.append(f"- `{c.path}` (R{c.similarity})")
        lines.append("")
        lines.append(
            f"To follow a rename: `tether update --{label}-path <new>`, "
            "then `tether refresh <uuid>` once aligned."
        )
    return lines


def one_tether_md(
    t: Tether,
    check: TetherCheck,
    root: Path,
    show_diff: bool,
) -> str:
    lines = [
        f"# Tether `{t.id}`",
        "",
        f"- **State:** {check.aggregate.value}",
        f"- **a:** `{art_display(t.a)}` — {check.a.state.value}"
        + (" (encoding-only drift rescued)" if check.a.normalization_rescued else ""),
        f"- **b:** `{art_display(t.b)}` — {check.b.state.value}"
        + (" (encoding-only drift rescued)" if check.b.normalization_rescued else ""),
        f"- **Created:** {t.created_at}",
        f"- **Refreshed:** {t.refreshed_at}",
        f"- **Description:** {t.description}",
    ]
    if show_diff:
        for label, artifact, art in (
            ("a", t.a, check.a),
            ("b", t.b, check.b),
        ):
            if art.state == ArtifactState.DRIFTED:
                lines.extend(_drift_block(label, artifact, root, rescued=False))
            elif art.state == ArtifactState.HEALTHY and art.normalization_rescued:
                lines.extend(_drift_block(label, artifact, root, rescued=True))
            elif art.state == ArtifactState.BROKEN:
                lines.extend(_broken_block(label, artifact, art.rename_candidates))
    return "\n".join(lines)
