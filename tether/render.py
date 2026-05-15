from __future__ import annotations

from pathlib import Path

from .model import Tether
from .status import SEVERITY, ArtifactState, TetherCheck

Row = tuple[Tether, TetherCheck]

STATE_ORDER: tuple[str, ...] = ("HEALTHY", "WEAKENED", "DRIFTED", "BROKEN")


def arrow(t: Tether) -> str:
    return "↔" if t.bidirectional else "→"


def tether_line(t: Tether, check: TetherCheck) -> str:
    return (
        f"- `{t.id}`: {check.aggregate.value} — "
        f"`{t.src.path}` ({check.src.state.value}) {arrow(t)} "
        f"`{t.dst.path}` ({check.dst.state.value}) — `{t.type}`"
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
            lines.append(f"  Description: {t.description or '(none)'}")
        for label, art in (("src", check.src), ("dst", check.dst)):
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
