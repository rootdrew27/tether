from __future__ import annotations

import sys
from pathlib import Path

import msgspec

from ..errors import TetherError
from ..project import find_project_root
from ..render import (
    Row,
    counts,
    errors_section,
    item_lines,
    summary_line,
)
from ..status import AggregateState, check_tether
from ..storage import LoadResult, load_all


class HookInput(msgspec.Struct, kw_only=True):
    cwd: str


class StopBlock(msgspec.Struct, kw_only=True):
    decision: str
    reason: str


def _read_cwd() -> Path:
    raw = sys.stdin.buffer.read()
    if not raw.strip():
        print("tether hook: stdin is empty (expected hook JSON)", file=sys.stderr)
        sys.exit(2)
    try:
        data = msgspec.json.decode(raw, type=HookInput)
    except (msgspec.ValidationError, msgspec.DecodeError) as e:
        print(f"tether hook: invalid stdin JSON: {e}", file=sys.stderr)
        sys.exit(2)
    cwd = Path(data.cwd)
    if not cwd.exists():
        print(f"tether hook: cwd does not exist: {data.cwd}", file=sys.stderr)
        sys.exit(2)
    return cwd


def _evaluate(root: Path) -> tuple[LoadResult, list[Row]]:
    result = load_all(root)
    rows: list[Row] = [(t, check_tether(t, root)) for t in result.tethers]
    return result, rows


def session_start() -> None:
    cwd = _read_cwd()
    try:
        root = find_project_root(cwd)
    except TetherError:
        sys.exit(0)

    result, rows = _evaluate(root)
    if not rows and not result.errors:
        sys.exit(0)

    c = counts(rows)
    total = len(rows)
    if total > 0 and c["HEALTHY"] == total and not result.errors:
        plural = "s" if total != 1 else ""
        print(f"tether: {total} tether{plural}, all HEALTHY.")
        return

    lines = ["## Tether status", "", summary_line(rows)]
    non_healthy = [r for r in rows if r[1].aggregate != AggregateState.HEALTHY]
    if non_healthy:
        lines.extend(["", "Needs attention:"])
        lines.extend(item_lines(non_healthy))
        lines.extend(["", "For diffs: `tether status <uuid>`"])
    lines.extend(errors_section(result.errors, root))
    print("\n".join(lines))


def stop() -> None:
    cwd = _read_cwd()
    try:
        root = find_project_root(cwd)
    except TetherError:
        sys.exit(0)

    result, rows = _evaluate(root)
    non_healthy = [r for r in rows if r[1].aggregate != AggregateState.HEALTHY]
    if not non_healthy and not result.errors:
        sys.exit(0)

    lines = ["## Stop blocked: tethers need attention", ""]
    if non_healthy:
        lines.extend(item_lines(non_healthy))
    lines.extend(errors_section(result.errors, root))
    lines.extend(
        [
            "",
            "For each entry above, either:",
            "- resolve and `tether refresh <uuid>` once both artifacts reflect the intended state, OR",
            "- if the resolution is a judgment call, surface the choice to the user with the options as you see them and end the turn awaiting direction.",
            "",
            "Do not refresh until alignment is real — refresh erases the drift signal. "
            "For renames, use `tether update --a-path/--b-path <new>` before refresh.",
        ]
    )

    block = StopBlock(decision="block", reason="\n".join(lines))
    sys.stdout.write(msgspec.json.encode(block).decode("utf-8"))
    sys.stdout.write("\n")
